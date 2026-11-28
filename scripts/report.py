"""Interactive HTML report for analyze.py  ->  results/report.html

One self-contained page: the analysis data is embedded as JSON and the charts are drawn in the
browser with Plotly.js, so a single set of filters (synths, class, conditions) drives every
chart and table. In the charts: click a legend entry to hide a line, double-click it to show
only that one, drag to zoom, scroll to zoom, double-click the plot to reset, hover a line (not
just its points) to see which one it is.

Offline use: if the `plotly` Python package is installed (pip install plotly) its bundled
plotly.js is inlined (about 4.5 MB). Without it the page loads plotly.js from a CDN, so it
needs an internet connection when opened.
"""
import datetime
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

CDN_URL = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def plotly_script():
    """Returns (script tag html, True if inlined so the page works offline)."""
    try:
        import plotly
        js = (Path(plotly.__file__).parent / "package_data" / "plotly.min.js").read_text(encoding="utf-8")
        return "<script>" + js + "</script>", True
    except Exception:
        return f'<script src="{CDN_URL}"></script>', False


def recs(df, cols):
    """DataFrame -> list of dicts, NaN -> None (valid JSON)."""
    cols = [c for c in cols if c in df.columns]
    return json.loads(df[cols].to_json(orient="records"))


def write_html(path, out, g, lad, inter, by_tag, factors, thresholds, tier_colors,
               filter_factors=(), fx_cols=(), whiskers="range"):
    """out: summary table; g: per-project table; lad: ladder points; inter: stack interactions;
    by_tag: tag ranking or None; factors: [(factor, [(level, n_projects), ...]), ...]."""
    script, offline = plotly_script()

    inter = inter.copy()
    if len(inter):
        dev = np.abs(np.log(inter.mult_ratio.where(inter.mult_ratio > 0)))
        inter = inter.assign(dev=dev).sort_values(["dev", "add_ratio"], ascending=False,
                                                  na_position="last")
    proj = g.assign(conditions=g.pname.str.split("__", n=1).str[1])
    fx = out[out["class"] == "fx"]
    fx_rows = [dict(col=col, key=key,
                    levels=sorted({str(v) for v in fx[key] if str(v).strip()}),
                    hasNone=bool(any(not str(v).strip() or str(v) == "nan" for v in fx[key])))
               for col, key in fx_cols if key in out.columns]
    cost_cols = [c for c in out.columns if c.endswith("_cost_per_step") and "@" not in c]
    data = dict(
        summary=recs(out, ["synth", "class", "tier", "tier_stable", "ref_load", "ref_lo", "ref_hi", "ref_wlo", "ref_whi", "ref_sd",
                           "idle", "heaviest", "max_spike", "redundant_in"] + [k for _, k in fx_cols] + cost_cols),
        fx=dict(cols=fx_rows),
        costCols=cost_cols,
        ladders=recs(lad, ["synth", "factor", "line", "lvl", "load", "load_lo", "load_hi", "wlo", "whi", "rel_range",
                           "pname", "conds"])
        if len(lad) else [],
        heat=recs(g[g.is_cfg], ["synth", "col", "load", "load_lo", "load_hi", "wlo", "whi", "pname", "conds", "base_load",
                                "over_base", "over_lo", "over_hi", "x_base"]),
        inter=recs(inter, ["synth", "conditions", "load", "base_load", "additive_pred", "add_ratio",
                           "mult_pred", "mult_ratio", "conds"]),
        tags=recs(by_tag, ["tag", "cls", "synth", "project", "load", "lo", "hi", "wlo", "whi", "rank",
                           "x_cheapest", "redundant", "conds"]) if by_tag is not None else [],
        projects=recs(proj, ["synth", "conditions", "load", "load_lo", "load_hi", "wlo", "whi", "sd", "rel_range", "n",
                             "spike", "conds", "over_base", "x_base"]),
        thresholds={k: list(v) for k, v in thresholds.items()},
        tierColors=tier_colors,
        factors=[dict(factor=k, levels=[list(x) for x in v]) for k, v in factors],
        filterFactors=[dict(factor=k, levels=[x[0] for x in v],
                            hasNone=bool(any(k not in c for c in g.conds)))
                       for k, v in factors if k in filter_factors],
        meta=dict(generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                  length=float(g.length.iloc[0]) if len(g) else None,
                  projects=int(len(g)), offline=offline, whiskers=whiskers),
    )
    blob = json.dumps(data).replace("</", "<\\/")
    vals = {"PLOTLY": script, "DATA": blob, "JS": APP_JS}
    wh = ("show plus/minus 1 standard deviation of the runs, centred on the median" if whiskers == "std"
          else "span the fastest to slowest run")
    html = re.sub(r"__(PLOTLY|DATA|JS)__", lambda m: vals[m.group(1)],
                  TEMPLATE.replace("{{WHTXT}}", wh))  # one pass
    Path(path).write_text(html, encoding="utf-8")
    return offline


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Synth bench report</title>
<style>
:root{--bg:#fff;--fg:#1d2026;--muted:#667085;--grid:#e4e7ec;--card:#f6f7f9;--line:#d0d5dd;--accent:#2f6fed}
@media (prefers-color-scheme: dark){:root{--bg:#14171c;--fg:#e6e8eb;--muted:#9aa4b2;--grid:#2c323b;--card:#1b1f26;--line:#39404b;--accent:#6b9bff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:14px 20px 4px}
h1{font-size:20px;margin:0}
.meta{color:var(--muted);font-size:12px}
.bar{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 20px;display:flex;flex-direction:column;gap:6px;max-height:40vh;overflow:auto}
.row{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.rowlabel{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em;min-width:48px}
.chip.f{background:var(--bg)}
button.sm{padding:1px 7px;font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:4px 6px}
.chip{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border:1px solid var(--line);border-radius:12px;background:var(--card);cursor:pointer;user-select:none;font-size:13px}
.chip.off{opacity:.35}
.chip input{margin:0}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
button,select,input[type=text]{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 9px}
button{cursor:pointer}
button:hover{border-color:var(--accent)}
main{padding:0 20px 40px;max-width:1400px}
section{margin-top:26px}
h2{font-size:16px;margin:0 0 4px}
.hint{color:var(--muted);font-size:12px;margin:0 0 8px}
.ctl{display:flex;gap:10px;align-items:center;margin:6px 0;flex-wrap:wrap}
.empty{color:var(--muted);padding:12px;border:1px dashed var(--line);border-radius:6px}
table{border-collapse:collapse;font-size:13px;width:100%}
th,td{padding:4px 10px;border-bottom:1px solid var(--grid);text-align:left;white-space:nowrap}
th{cursor:pointer;position:sticky;top:0;background:var(--card);user-select:none}
th.asc::after{content:" \25B2";font-size:9px}th.desc::after{content:" \25BC";font-size:9px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.scroll{max-height:60vh;overflow:auto;border:1px solid var(--line);border-radius:6px}
.badge{color:#fff;border-radius:4px;padding:1px 7px;font-size:12px}
.err{background:#fde7e7;color:#8a1c1c;padding:8px 20px;display:none;white-space:pre-wrap}
.tabs{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.tabs button{border:0;border-radius:0;padding:5px 16px;background:var(--card);font-weight:600}
.tabs button.active{background:var(--accent);color:#fff}
.tabs .n{opacity:.7;font-weight:400;margin-left:4px}
.layer{display:flex;flex-direction:column;gap:6px}
.layer:empty{display:none}
#layer3{border-top:1px dashed var(--line);padding-top:6px}
h3.sub{font-size:14px;margin:18px 0 2px}
.key{display:inline-flex;gap:12px;font-size:12px;color:var(--muted)}
details{margin-top:26px}
</style></head><body>
<div class="err" id="err"></div>
<header><h1>Synth bench report</h1><div class="meta" id="meta"></div></header>
<div class="bar" id="bar">
  <div class="row" id="toprow">
    <div class="tabs" id="tabs"></div>
    <label id="clswrap">Class <select id="cls"></select></label>
    <button id="b-reset" title="Reset zoom on every chart">Reset zoom</button>
    <span class="meta" id="barcount"></span>
  </div>
  <div id="layer2" class="layer"></div>
  <div id="layer3" class="layer"></div>
</div>
<main>
<section><h2>Summary</h2><p class="hint">Click a column heading to sort.</p>
  <div class="scroll"><div id="tbl-summary"></div></div></section>
<section id="s-tiers"><h2>Reference load by synth</h2>
  <p class="hint">Bars are the preset=typical load (or the base config); whiskers {{WHTXT}}; dashed lines are the tier thresholds.
  <span class="key" id="tierkey"></span></p><div id="tiers"></div></section>
<section id="s-ladder"><h2>Ladders</h2>
  <p class="hint">Load against one numeric factor with every other condition held fixed. Dashed lines are the same synth with other conditions applied (named in the legend). Whiskers {{WHTXT}}; larger markers mean more run-to-run spread (fastest to slowest run, whatever the whisker setting). Click a legend entry to hide a line, double-click to isolate it.</p>
  <div class="ctl"><label>Factor <select id="factor"></select></label>
  <label><input type="checkbox" id="logy"> log scale</label></div><div id="ladder"></div></section>
<section id="s-heat"><h2>Configuration tests</h2>
  <p class="hint">Every project that has conditions, other than idle and the polyphony ladder. <b>Cost over base</b> is the project's load minus the base project at the same note count (effects: minus preset=typical); <b>&times; base</b> is the ratio. The ranking below follows the same filters and metric.</p>
  <div class="ctl"><label>Filter conditions <input type="text" id="cond" placeholder="e.g. granular -unison" size="28"
      title="Words that must appear in the column name. Put - in front of a word to exclude it."></label>
    <label>Show <select id="heatmetric"><option value="load">load</option><option value="over_base">cost over base</option><option value="x_base">&times; base</option></select></label>
    <label>Rank top <select id="overtop"><option value="15">15</option><option value="30" selected>30</option><option value="60">60</option><option value="0">all</option></select></label>
    <span id="ladderhide" title="Hides the projects that are steps on a ladder of that factor: the same other conditions measured at two or more levels (by any synth). Stacks that only happen to include it stay. For notes, one level is kept (see keep notes=)."></span></div>
  <div id="heat"></div>
  <h3 class="sub" id="overtitle">Ranked</h3><p class="hint" id="overhint"></p><div id="overchart"></div></section>
<section id="s-inter"><h2>Stacking interactions</h2>
  <p class="hint">Measured load divided by the prediction made from the parts alone. <b>1.0 = no interaction.</b>
  Multiplicative (diamonds): costs multiply, so unison &times; notes style scaling counts as normal. Additive (circles): costs add. Biggest multiplicative surprise first.</p>
  <div id="inter"></div></section>
<section id="s-tags"><h2>Tag ranking</h2>
  <p class="hint">Synths with the same tag ranked cheapest first. Red = more than 2&times; the cheapest.</p>
  <div class="ctl"><label>Tag <select id="tagsel"></select></label></div><div id="tagchart"></div></section>
<section><h2>All projects</h2><div class="scroll"><div id="tbl-proj"></div></div></section>
<details><summary>Conditions found</summary><div id="factors" class="hint"></div></details>
</main>
__PLOTLY__
<script type="application/json" id="data">__DATA__</script>
<script>__JS__</script>
</body></html>
"""

APP_JS = r"""
(() => {
const D = JSON.parse(document.getElementById("data").textContent);
const WHLAB = D.meta.whiskers === "std" ? "\u00b11 std dev" : "fastest\u2013slowest run";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (v, d = 4) => (v == null || Number.isNaN(v)) ? "\u2013" : Number(v).toFixed(d);
const PALETTE = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac",
  "#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"];
const CONFIG = {responsive: true, displaylogo: false, scrollZoom: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d"], toImageButtonOptions: {scale: 2}};

const synths = D.summary.map(r => r.synth);
const NONE = "__none__", UNTYPED = "__untyped__";   // sentinels; levels never contain a double underscore
const color = Object.fromEntries(synths.map((s, i) => [s, PALETTE[i % PALETTE.length]]));
const klass = Object.fromEntries(D.summary.map(r => [r.synth, r.class]));
const isFx = s => klass[s] === "fx";
const hasInst = synths.some(s => !isFx(s)), hasFx = synths.some(isFx);
const instClasses = [...new Set(D.summary.filter(r => r.class !== "fx").map(r => r.class))];
const FXC = (D.fx && D.fx.cols) || [];
const FF = (D.filterFactors || []).map(f => f.factor);     // conditions that get a chip row (e.g. mode)
const fxrec = Object.fromEntries(D.summary.map(r => [r.synth, r]));

// Everything unticked is stored (not what is ticked), so levels that show up later start ticked.
const state = {view: hasInst ? "instruments" : "effects", on: new Set(synths), cls: "all", metric: "load", overTop: 30,
               factor: null, logy: false, cond: "", tag: null, rev: 0, hideLadders: new Set(), keepNotes: "1",
               off: {type: new Set(), fx: {}, cond: {}}};
for (const c of FXC) state.off.fx[c.key] = new Set();
for (const f of FF) state.off.cond[f] = new Set();

// Types are the tags in tags.csv, and they belong to PROJECTS, not just instruments:
//  - a project with a mode takes that mode's type: the tag of the exact mode=X row in tags.csv
//    (mode=va -> analog), else the mode value itself. mode=granular__unison=4 is granular.
//  - a project with no mode takes the instrument's baseline types (tag rows with a blank project).
//  - a tag with its own conditions (e.g. combo = mode=granular__unison=4) also applies to every project
//    that has those conditions (notes are ignored unless the tag names them).
//  - a project left with no type is "untyped".
// An instrument has every type any of its projects has. Unticking a Type hides the projects that only
// have that type, and the instruments that have no ticked type left.
const baseTags = {}, condTags = {}, modeTags = {}, modeAny = {};
for (const r of D.tags) {
  if (r.cls === "fx") continue;
  const c = r.conds || {}, ks = Object.keys(c);
  if (!ks.length) (baseTags[r.synth] ||= new Set()).add(r.tag);
  else (condTags[r.synth] ||= []).push({tag: r.tag, conds: c});
  if (ks.length === 1 && c.mode != null) {
    modeTags[r.synth + "\u0001" + c.mode] = r.tag;
    (modeAny[c.mode] ||= new Set()).add(r.tag);
  }
}
const modeType = (s, m) => modeTags[s + "\u0001" + m] ?? (modeAny[m]?.size === 1 ? [...modeAny[m]][0] : String(m));
const matches = (tc, pc) => Object.entries(tc).every(([k, v]) => pc[k] != null && String(pc[k]) === String(v));
const typeCache = {};
function projTypes(s, c) {
  const k = s + "\u0001" + JSON.stringify(Object.entries(c).sort());
  if (typeCache[k]) return typeCache[k];
  const out = new Set();
  if (c.mode != null) out.add(modeType(s, c.mode)); else for (const t of baseTags[s] || []) out.add(t);
  for (const t of condTags[s] || []) if (matches(t.conds, c)) out.add(t.tag);
  if (!out.size) out.add(UNTYPED);
  return typeCache[k] = out;
}
const typesOf = {};
for (const p of D.projects) { const t = (typesOf[p.synth] ||= new Set()); for (const x of projTypes(p.synth, p.conds)) t.add(x); }
for (const s of synths) if (!isFx(s)) { const t = (typesOf[s] ||= new Set()); for (const x of baseTags[s] || []) t.add(x); if (!t.size) t.add(UNTYPED); }
const typeKeys = s => typesOf[s] ? [...typesOf[s]] : [UNTYPED];

// Layers: view -> class -> type / category -> (what survives) -> ticked chips
const inView = s => (state.view === "effects") === isFx(s);
const clsOK = s => isFx(s) || state.cls === "all" || klass[s] === state.cls;
const typeOK = s => isFx(s) || typeKeys(s).some(t => !state.off.type.has(t));
const fxOK = s => !isFx(s) || FXC.every(c => !state.off.fx[c.key].has(String(fxrec[s][c.key] || "").trim() || NONE));
const survivor = s => inView(s) && clsOK(s) && typeOK(s) && fxOK(s);
const visible = s => survivor(s) && state.on.has(s);
// a project passes a condition row when its level of every filtered factor is ticked
const condOK = c => Object.entries(state.off.cond).every(([f, off]) => !off.has(c && c[f] != null ? String(c[f]) : NONE));
// a project row (anything with .synth and .conds) passes when it has a ticked Type and its condition chips are ticked
const projOK = r => condOK(r.conds) && (isFx(r.synth) || [...projTypes(r.synth, r.conds || {})].some(t => !state.off.type.has(t)));

// A ladder is run across synths, so a project counts as a ladder step for factor f when ANY synth in
// the current view measured f at 2+ levels with the same other conditions.
const ctxKey = (c, f) => JSON.stringify(Object.keys(c).filter(k => k !== f).sort().map(k => [k, c[k]]));
const ladderCache = {};
function ladderInfo() {
  const v = state.view;
  if (ladderCache[v]) return ladderCache[v];
  const by = {}, ctx = {}, nl = new Set();
  for (const r of D.ladders) {
    if (isFx(r.synth) !== (v === "effects")) continue;
    (by[r.factor + "\u0001" + r.line] ||= {f: r.factor, pts: []}).pts.push(r);
    if (r.factor === "notes") nl.add(r.lvl);
  }
  for (const {f, pts} of Object.values(by))
    if (new Set(pts.map(p => p.lvl)).size >= 2) (ctx[f] ||= new Set()).add(ctxKey(pts[0].conds, f));
  return ladderCache[v] = {ctx, noteLevels: [...nl].sort((a, b) => a - b)};
}
const isLadderStep = (c, f) => { const L = ladderInfo().ctx[f]; return c[f] != null && !!L && L.has(ctxKey(c, f)); };

function theme() {
  const cs = getComputedStyle(document.documentElement);
  return {fg: cs.getPropertyValue("--fg").trim(), grid: cs.getPropertyValue("--grid").trim()};
}
function merge(a, b) {
  for (const k of Object.keys(b)) {
    if (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a[k] && typeof a[k] === "object") merge(a[k], b[k]);
    else a[k] = b[k];
  }
  return a;
}
function layout(extra, key) {
  const t = theme();
  const ax = () => ({gridcolor: t.grid, zerolinecolor: t.grid, linecolor: t.grid});
  return merge({paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: {color: t.fg, size: 12}, margin: {l: 70, r: 20, t: 24, b: 55}, hovermode: "closest",
    uirevision: state.rev + ":" + key, xaxis: ax(), yaxis: ax(), hoverlabel: {namelength: -1}}, extra || {});
}
function prep(div) { if (div.querySelector(".empty")) div.innerHTML = ""; }
function empty(div, msg) { try { Plotly.purge(div); } catch (e) {} div.innerHTML = '<p class="empty">' + esc(msg) + "</p>"; }
function draw(div, traces, lay) {
  prep(div);
  div.querySelectorAll(":scope > p.hint").forEach(e => e.remove());   // footnotes added by the previous render
  return Plotly.react(div, traces, lay, CONFIG);
}

// Hovering a line dims the rest. Lines are keyed by legendgroup so a line's helper traces move together.
function dimOnHover(div) {
  if (div.removeAllListeners) { div.removeAllListeners("plotly_hover"); div.removeAllListeners("plotly_unhover"); }
  div.on("plotly_hover", e => {
    const g = div.data[e.points[0].curveNumber].legendgroup;
    if (!g) return;
    Plotly.restyle(div, {opacity: div.data.map(t => t.legendgroup === g ? 1 : 0.18)});
  });
  div.on("plotly_unhover", () => Plotly.restyle(div, {opacity: div.data.map(() => 1)}));
}

// ---------- tables ----------
const sorts = {};
function table(id, cols, rows) {
  const host = $(id);
  const s = sorts[id] || (sorts[id] = {key: null, dir: 1});
  const data = rows.slice();
  if (s.key) data.sort((a, b) => {
    const x = a[s.key], y = b[s.key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "number" && typeof y === "number" ? x - y
            : String(x).localeCompare(String(y), undefined, {numeric: true})) * s.dir;
  });
  host.innerHTML = "<table><thead><tr>" + cols.map(c =>
      `<th data-k="${esc(c.key)}" class="${c.num ? "num" : ""} ${s.key === c.key ? (s.dir > 0 ? "asc" : "desc") : ""}">${esc(c.label)}</th>`).join("")
    + "</tr></thead><tbody>" + data.map(r => "<tr>" + cols.map(c =>
      `<td class="${c.num ? "num" : ""}">${c.html ? c.html(r) : esc(c.fmt ? c.fmt(r[c.key], r) : r[c.key])}</td>`).join("") + "</tr>").join("")
    + "</tbody></table>";
  host.querySelectorAll("th").forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (s.key === k) s.dir *= -1; else { s.key = k; s.dir = 1; }
    table(id, cols, rows);
  });
}
const dot = s => `<span class="dot" style="background:${color[s]}"></span> ${esc(s)}`;
const badge = t => t ? `<span class="badge" style="background:${D.tierColors[t] || "gray"}">${esc(t)}</span>` : "\u2013";

function renderTables() {
  const viewRows = D.summary.filter(r => inView(r.synth));
  const has = k => viewRows.some(r => r[k] != null && r[k] !== "");
  const typeText = s => typeKeys(s).filter(t => t !== UNTYPED).sort().join(", ");
  const cols = [
    {key: "synth", label: state.view === "effects" ? "effect" : "instrument", html: r => dot(r.synth)},
    ...(state.view === "effects" ? [] : [{key: "class", label: "class"}, {key: "types", label: "type", fmt: v => v || "\u2013"}]),
    ...(state.view === "effects" ? FXC.map(c => ({key: c.key, label: c.col, fmt: v => v || "\u2013"})) : []),
    {key: "tier", label: "tier", html: r => badge(r.tier)},
    {key: "tier_stable", label: "tier stable?", fmt: v => v == null ? "\u2013" : v ? "yes" : "no"},
    {key: "ref_load", label: "ref load", num: true, fmt: v => fmt(v)},
    {key: "idle", label: "idle", num: true, fmt: v => fmt(v)},
    {key: "heaviest", label: "heaviest", num: true, fmt: v => fmt(v)},
    {key: "max_spike", label: "max spike", num: true, fmt: v => fmt(v, 2)},
    ...D.costCols.map(c => ({key: c, label: c.replace("_cost_per_step", " /step"), num: true, fmt: v => fmt(v)})),
  ].filter(c => !c.num || has(c.key));
  if (viewRows.some(r => r.redundant_in)) cols.push({key: "redundant_in", label: "redundant in"});
  table("#tbl-summary", cols, D.summary.filter(r => visible(r.synth)).map(r => ({...r, types: typeText(r.synth)})));
  table("#tbl-proj", [
    {key: "synth", label: "synth", html: r => dot(r.synth)},
    {key: "conditions", label: "conditions"},
    {key: "load", label: "load", num: true, fmt: v => fmt(v)},
    {key: "over_base", label: "over base", num: true, fmt: v => v == null ? "\u2013" : METRICS.over_base.fmt(v)},
    {key: "x_base", label: "\u00d7 base", num: true, fmt: v => v == null ? "\u2013" : fmt(v, 2)},
    {key: "load_lo", label: "fastest", num: true, fmt: v => fmt(v)},
    {key: "load_hi", label: "slowest", num: true, fmt: v => fmt(v)},
    {key: "sd", label: "std dev", num: true, fmt: v => v == null ? "\u2013" : fmt(v)},
    {key: "rel_range", label: "spread", num: true, fmt: v => v == null ? "\u2013" : (v * 100).toFixed(0) + "%"},
    {key: "n", label: "runs", num: true},
    {key: "spike", label: "spike", num: true, fmt: v => fmt(v, 2)},
  ], D.projects.filter(r => visible(r.synth) && projOK(r)));
}

// ---------- tiers ----------
function renderTiers() {
  const host = $("#tiers"); host.innerHTML = "";
  const rows = D.summary.filter(r => r.ref_load != null && visible(r.synth));
  if (!rows.length) return empty(host, "No reference loads for the selected synths.");
  const fg = theme().fg;
  for (const c of [...new Set(rows.map(r => r.class))]) {
    const o = rows.filter(r => r.class === c).sort((a, b) => a.ref_load - b.ref_load);
    const div = document.createElement("div"); host.appendChild(div);
    const [lo, hi] = D.thresholds[c];
    const mx = Math.max(hi, ...o.map(r => r.ref_whi ?? r.ref_load)) * 1.08;
    draw(div, [{type: "bar", orientation: "h", y: o.map(r => r.synth), x: o.map(r => r.ref_load),
      marker: {color: o.map(r => D.tierColors[r.tier] || "gray")},
      error_x: {type: "data", symmetric: false, array: o.map(r => (r.ref_whi ?? r.ref_load) - r.ref_load),
                arrayminus: o.map(r => r.ref_load - (r.ref_wlo ?? r.ref_load)), thickness: 1.5, color: fg},
      customdata: o.map(r => [r.tier, r.ref_wlo, r.ref_whi]),
      hovertemplate: "<b>%{y}</b><br>load %{x:.4f}<br>" + WHLAB + " %{customdata[1]:.4f} \u2013 %{customdata[2]:.4f}<br>tier: %{customdata[0]}<extra></extra>"}],
      layout({title: {text: "Class: " + c, font: {size: 13}, x: 0.01}, height: 110 + 28 * o.length,
        margin: {t: 34}, xaxis: {title: {text: "load (net CPU s per audio s)"}, range: [0, mx]},
        yaxis: {type: "category", automargin: true},
        shapes: [lo, hi].map(v => ({type: "line", x0: v, x1: v, y0: 0, y1: 1, yref: "paper", line: {dash: "dash", color: "gray"}}))}, "tiers" + c));
  }
}

// ---------- ladders ----------
const DASHES = ["solid", "dash", "dot", "dashdot", "longdash"];
function renderLadder() {
  const host = $("#ladder");
  const rows = D.ladders.filter(r => r.factor === state.factor && visible(r.synth) && projOK(r));
  if (!rows.length) return empty(host, "No ladder points for the selected synths.");
  const lines = new Map();
  for (const r of rows) { if (!lines.has(r.line)) lines.set(r.line, {synth: r.synth, pts: []}); lines.get(r.line).pts.push(r); }
  const traces = [], perSynth = {};
  for (const [name, {synth, pts}] of lines) {
    pts.sort((a, b) => a.lvl - b.lvl);
    const n = perSynth[synth] = (perSynth[synth] ?? -1) + 1;
    const col = color[synth], dash = DASHES[n % DASHES.length];
    traces.push({type: "scatter", mode: pts.length > 1 ? "lines+markers" : "markers", name, legendgroup: name,
      x: pts.map(p => p.lvl), y: pts.map(p => p.load), line: {color: col, dash, width: 2},
      marker: {color: col, size: pts.map(p => 6 + Math.min(p.rel_range || 0, 0.3) / 0.3 * 10)},
      error_y: {type: "data", symmetric: false, array: pts.map(p => p.whi - p.load),
                arrayminus: pts.map(p => p.load - p.wlo), thickness: 1, width: 3, color: col},
      customdata: pts.map(p => [p.wlo, p.whi]),
      hovertemplate: "<b>%{fullData.name}</b><br>" + esc(state.factor) + " = %{x}<br>load %{y:.4f}<br>" + WHLAB + " %{customdata[0]:.4f} \u2013 %{customdata[1]:.4f}<extra></extra>"});
    if (pts.length > 1) {
      // invisible points along each segment so hovering anywhere on the line names it
      const hx = [], hy = [], K = 24;
      for (let i = 0; i < pts.length - 1; i++) for (let k = 1; k < K; k++) {
        const t = k / K, a = pts[i], b = pts[i + 1];
        hx.push(a.lvl + (b.lvl - a.lvl) * t);
        hy.push(state.logy && a.load > 0 && b.load > 0 ? Math.exp(Math.log(a.load) + (Math.log(b.load) - Math.log(a.load)) * t)
                                                       : a.load + (b.load - a.load) * t);
      }
      traces.push({type: "scatter", mode: "markers", name, legendgroup: name, showlegend: false, x: hx, y: hy,
        marker: {size: 14, color: col, opacity: 0}, hoverlabel: {bgcolor: col},
        hovertemplate: "<b>%{fullData.name}</b><extra></extra>"});
    }
  }
  const levels = [...new Set(rows.map(r => r.lvl))].sort((a, b) => a - b);
  draw(host, traces, layout({height: 460, margin: {r: 10},
    xaxis: {title: {text: state.factor}, tickmode: levels.length <= 14 ? "array" : "auto", tickvals: levels},
    yaxis: {title: {text: "load (net CPU s per audio s)"}, type: state.logy ? "log" : "linear", rangemode: state.logy ? "normal" : "tozero"},
    legend: {font: {size: 11}}}, "ladder:" + state.factor + state.logy));
  dimOnHover(host);
}

// ---------- heatmap ----------
const METRICS = {
  load: {label: "load", fmt: v => fmt(v)},
  over_base: {label: "cost over base", fmt: v => (v >= 0 ? "+" : "") + fmt(v)},
  x_base: {label: "\u00d7 base", fmt: v => fmt(v, 2) + "\u00d7"},
};
function heatRows() {
  const pos = [], neg = [];
  for (const t of state.cond.toLowerCase().split(/\s+/).filter(Boolean)) (t.length > 1 && t[0] === "-" ? neg : pos).push(t[0] === "-" && t.length > 1 ? t.slice(1) : t);
  const hid = [...state.hideLadders];
  return D.heat.filter(r => visible(r.synth) && projOK(r)
    && !hid.some(f => isLadderStep(r.conds, f) && !(f === "notes" && String(r.conds.notes) === state.keepNotes))
    && pos.every(t => r.col.toLowerCase().includes(t)) && !neg.some(t => r.col.toLowerCase().includes(t)));
}
const cellTip = r => `<b>${esc(r.synth)}</b><br>${esc(r.col)}<br>load ${fmt(r.load)}`
  + (r.base_load != null ? `<br>base ${fmt(r.base_load)}<br>cost over base ${METRICS.over_base.fmt(r.over_base)}` + (r.x_base != null ? ` (${fmt(r.x_base, 2)}\u00d7)` : "") : "<br>(no base to compare with)");

function renderHeat() {
  const host = $("#heat"), M = state.metric;
  const rows = heatRows();
  if (!rows.length) return empty(host, D.heat.length ? "Nothing matches the current filters." : "No configuration tests in the results.");
  if (!rows.some(r => r[M] != null)) return empty(host, "None of these projects has a base to compare with, so there is no " + METRICS[M].label + " to show.");
  const ys = synths.filter(s => rows.some(r => r.synth === s));
  const xs = [...new Set(rows.map(r => r.col))].sort();
  const m = new Map(rows.map(r => [r.synth + "\u0001" + r.col, r]));
  const cell = (s, c) => m.get(s + "\u0001" + c);
  draw(host, [{type: "heatmap", x: xs, y: ys,
    z: ys.map(s => xs.map(c => cell(s, c)?.[M] ?? null)),
    text: ys.map(s => xs.map(c => { const r = cell(s, c); return r ? cellTip(r) : ""; })),
    colorscale: "YlOrRd", reversescale: true, hoverongaps: false, colorbar: {title: {text: METRICS[M].label}},
    hovertemplate: "%{text}<extra></extra>"}],
    layout({height: 170 + 26 * ys.length + Math.min(300, 4.5 * Math.max(...xs.map(x => x.length))), margin: {l: 110, b: 20},
      xaxis: {type: "category", tickangle: -45, automargin: true},
      yaxis: {type: "category", autorange: "reversed", automargin: true}}, "heat" + M));
}

// ranked bars for the chosen metric, same rows as the heatmap
function renderOver() {
  const host = $("#overchart"), M = state.metric;
  $("#overtitle").textContent = "Ranked by " + METRICS[M].label;
  $("#overhint").textContent = M === "over_base"
    ? "Whiskers are the conservative range (fastest run minus the base's slowest, to slowest minus the base's fastest). Faded bars: the range includes zero, so the difference is within run-to-run spread."
    : M === "load" ? (D.meta.whiskers === "std" ? "Whiskers are \u00b11 standard deviation of the runs." : "Whiskers span the fastest to slowest run.")
    : "Load divided by the base's load (blank where the base is almost zero).";
  let rows = heatRows().filter(r => r[M] != null).sort((a, b) => b[M] - a[M]);
  if (!rows.length) return empty(host, "Nothing to rank with the current filters.");
  const total = rows.length;
  if (state.overTop > 0) rows = rows.slice(0, state.overTop);
  const lab = rows.map(r => r.synth + "  " + r.col);
  const bars = M === "load" ? {lo: r => r.wlo, hi: r => r.whi}
             : M === "over_base" ? {lo: r => r.over_lo, hi: r => r.over_hi} : null;
  const faded = r => M === "over_base" && r.over_lo != null && r.over_lo <= 0 && r.over_hi >= 0;
  draw(host, [{type: "bar", orientation: "h", y: lab, x: rows.map(r => r[M]),
    marker: {color: rows.map(r => color[r.synth]), opacity: rows.map(r => faded(r) ? 0.35 : 1)},
    error_x: bars ? {type: "data", symmetric: false, array: rows.map(r => bars.hi(r) - r[M]),
                     arrayminus: rows.map(r => r[M] - bars.lo(r)), thickness: 1.2, color: theme().fg} : {visible: false},
    text: rows.map(r => cellTip(r) + (faded(r) ? "<br>within run-to-run spread" : "")), textposition: "none", hovertemplate: "%{text}<extra></extra>"}],
    layout({height: 90 + 24 * rows.length, margin: {l: 120, t: 10},
      xaxis: {title: {text: METRICS[M].label}, type: M === "x_base" ? "log" : "linear", zeroline: true},
      yaxis: {type: "category", autorange: "reversed", automargin: true}}, "over" + M));
  if (total > rows.length) host.insertAdjacentHTML("beforeend", `<p class="hint">Showing the top ${rows.length} of ${total}; change "Rank top" to see more.</p>`);
}

// ---------- interactions ----------
function renderInter() {
  const host = $("#inter");
  const all = D.inter.filter(r => visible(r.synth) && projOK(r));
  const rows = all.filter(r => r.mult_ratio != null || r.add_ratio != null);
  if (!rows.length) return empty(host, D.inter.length ? "No stacks with a ratio for the selected synths." : "No stacked projects in the results.");
  const lab = rows.map(r => r.synth + "  " + r.conditions);
  const cd = rows.map(r => [r.load, r.base_load, r.additive_pred, r.mult_pred]);
  const tip = (nm) => "<b>%{y}</b><br>" + nm + " ratio %{x:.2f}<br>measured %{customdata[0]:.4f}<br>base %{customdata[1]:.4f}<br>additive prediction %{customdata[2]:.4f}<br>multiplicative prediction %{customdata[3]:.4f}<extra></extra>";
  const skipped = all.length - rows.length;
  draw(host, [
    {type: "scatter", mode: "markers", name: "multiplicative", x: rows.map(r => r.mult_ratio), y: lab, customdata: cd,
      marker: {symbol: "diamond", size: 10, color: "#e15759"}, hovertemplate: tip("multiplicative")},
    {type: "scatter", mode: "markers", name: "additive", x: rows.map(r => r.add_ratio), y: lab, customdata: cd,
      marker: {symbol: "circle", size: 8, color: "#4e79a7"}, hovertemplate: tip("additive")}],
    layout({height: 150 + 26 * rows.length, margin: {l: 120, t: 50}, legend: {orientation: "h", y: 1.0, yanchor: "bottom"},
      xaxis: {type: "log", title: {text: "measured / predicted (log scale)"}, tickvals: [0.5, 0.7, 1, 1.5, 2, 3, 5], ticktext: ["0.5", "0.7", "1", "1.5", "2", "3", "5"]},
      yaxis: {type: "category", autorange: "reversed", automargin: true},
      shapes: [{type: "line", x0: 1, x1: 1, y0: 0, y1: 1, yref: "paper", line: {color: "gray", dash: "dash"}}]}, "inter"));
  if (skipped) host.insertAdjacentHTML("beforeend", `<p class="hint">${skipped} stack(s) have no ratio because their parts add less than the minimum load increment.</p>`);
}

// ---------- tags ----------
function renderTags() {
  const host = $("#tagchart");
  const rows = D.tags.filter(r => (r.tag + "|" + r.cls) === state.tag && visible(r.synth)).sort((a, b) => a.rank - b.rank);
  if (!rows.length) return empty(host, "No synths for this tag with the current filters.");
  const mk = (flag, name, col) => {
    const o = rows.filter(r => !!r.redundant === flag);
    return {type: "bar", orientation: "h", name, y: o.map(r => r.synth), x: o.map(r => r.load), marker: {color: col},
      error_x: {type: "data", symmetric: false, array: o.map(r => r.whi - r.load), arrayminus: o.map(r => r.load - r.wlo), thickness: 1.5, color: theme().fg},
      customdata: o.map(r => [r.project, r.rank, r.x_cheapest, r.wlo, r.whi]),
      hovertemplate: "<b>%{y}</b> (rank %{customdata[1]})<br>project: %{customdata[0]}<br>load %{x:.4f}<br>" + WHLAB + " %{customdata[3]:.4f} \u2013 %{customdata[4]:.4f}<br>%{customdata[2]:.2f}\u00d7 the cheapest<extra></extra>"};
  };
  draw(host, [mk(false, "within 2\u00d7 of cheapest", "#4e79a7"), mk(true, "redundant (>2\u00d7 cheapest)", "#c94040")],
    layout({height: 150 + 30 * rows.length, margin: {l: 110, t: 50}, legend: {orientation: "h", y: 1.0, yanchor: "bottom"},
      xaxis: {title: {text: "load (net CPU s per audio s)"}, rangemode: "tozero"},
      yaxis: {type: "category", automargin: true, categoryorder: "array", categoryarray: rows.map(r => r.synth).reverse()}}, "tags" + state.tag));
}

// ---------- controls ----------
const offSet = (kind, key) => kind === "type" ? state.off.type : kind === "fx" ? state.off.fx[key] : state.off.cond[key];
const isOn = (kind, key, id) => kind === "synth" ? state.on.has(id) : !offSet(kind, key).has(id);
function setOn(kind, key, id, on) {
  if (kind === "synth") on ? state.on.add(id) : state.on.delete(id);
  else offSet(kind, key)[on ? "delete" : "add"](id);
}
const byName = (a, b) => String(a).localeCompare(String(b), undefined, {numeric: true, sensitivity: "base"});
let SPECS = {};

// layer 2: Type (instruments) or the effects.csv categories (effects)
function layer2Specs() {
  if (state.view === "instruments") {
    const t = [...new Set(synths.filter(s => !isFx(s) && clsOK(s)).flatMap(typeKeys))]
      .sort((a, b) => (a === UNTYPED) - (b === UNTYPED) || byName(a, b));
    if (!t.some(x => x !== UNTYPED)) return [];
    return [{kind: "type", key: "type", label: "Type", hint: "filters instruments, and the ladders, heatmap, interactions and project table by each project's type",
             items: t.map(x => ({id: x, text: x === UNTYPED ? "untyped" : x}))}];
  }
  // Each effects.csv column is a finer level than the ones before it (category > group > vendor): a row only
  // offers values of effects that pass the ticks in every row above it.
  const val = (s, c) => String(fxrec[s][c.key] || "").trim();
  const passes = (s, c) => !state.off.fx[c.key].has(val(s, c) || NONE);
  return FXC.map((c, i) => {
    const pool = synths.filter(isFx).filter(s => FXC.slice(0, i).every(p => passes(s, p)));
    const vals = pool.map(s => val(s, c));
    const lv = [...new Set(vals.filter(Boolean))].sort(byName);
    const items = lv.map(x => ({id: x, text: x})).concat(vals.some(v => !v) ? [{id: NONE, text: "uncategorised"}] : []);
    return items.length ? {kind: "fx", key: c.key, label: c.col, hint: "", items} : null;
  }).filter(Boolean);
}
// layer 3: only what survives the layers above
function layer3Specs() {
  const surv = synths.filter(survivor).sort(byName);
  const out = [{kind: "synth", key: "synth", label: state.view === "effects" ? "Effect" : "Instrument",
    hint: `${surv.filter(s => state.on.has(s)).length} of ${surv.length} selected`,
    items: surv.map(s => ({id: s, text: s, color: color[s]}))}];
  const ok = new Set(surv);
  for (const f of FF) {
    const lv = new Set(); let none = false;
    for (const p of D.projects) { if (!ok.has(p.synth)) continue; const v = p.conds[f]; v == null ? (none = true) : lv.add(String(v)); }
    if (!lv.size) continue;
    out.push({kind: "cond", key: f, label: f, hint: "filters ladders, heatmap, interactions and the project table",
      items: [...lv].sort(byName).map(x => ({id: x, text: x})).concat(none ? [{id: NONE, text: "no " + f}] : [])});
  }
  return out;
}
function rowHtml(r) {
  SPECS[r.kind + ":" + r.key] = r;
  const at = `data-kind="${r.kind}" data-key="${esc(r.key)}"`;
  return `<div class="row" data-row="${r.kind}:${esc(r.key)}"><span class="rowlabel">${esc(r.label)}</span><div class="chips">`
    + r.items.map(it => `<label class="chip${r.kind === "synth" ? "" : " f"}" title="Double-click to show only this"><input type="checkbox" ${at} data-id="${esc(it.id)}"${isOn(r.kind, r.key, it.id) ? " checked" : ""}>`
      + (it.color ? `<span class="dot" style="background:${it.color}"></span>` : "") + esc(it.text) + "</label>").join("")
    + `</div><button class="sm" ${at} data-act="all">All</button><button class="sm" ${at} data-act="none">None</button>`
    + (r.hint ? `<span class="meta">${esc(r.hint)}</span>` : "") + "</div>";
}
function renderTop() {
  const tabs = [];
  if (hasInst) tabs.push({id: "instruments", label: "Instruments", n: synths.filter(s => !isFx(s)).length});
  if (hasFx) tabs.push({id: "effects", label: "Effects", n: synths.filter(isFx).length});
  $("#tabs").innerHTML = tabs.map(t => `<button data-view="${t.id}" class="${t.id === state.view ? "active" : ""}">${t.label}<span class="n">${t.n}</span></button>`).join("");
  $("#tabs").style.display = tabs.length > 1 ? "" : "none";
  const showCls = state.view === "instruments" && instClasses.length > 1;
  $("#clswrap").style.display = showCls ? "" : "none";
  $("#cls").innerHTML = '<option value="all">all</option>' + instClasses.map(c => `<option>${esc(c)}</option>`).join("");
  $("#cls").value = state.cls;
}
// keepKey: the row the person just clicked in. It is left in place, because replacing the chip under the
// cursor between the two clicks of a double-click stops the double-click ("show only this") from firing.
function renderLayer2(keepKey) {
  const sp = layer2Specs(), box = $("#layer2");
  const rows = [...box.children].map(e => e.dataset.row);
  const ids = sp.map(r => r.kind + ":" + r.key);
  if (keepKey == null || rows.length !== ids.length || rows.some((x, i) => x !== ids[i]) || !ids.includes(keepKey)) {
    box.innerHTML = sp.map(rowHtml).join(""); return;
  }
  sp.forEach((r, i) => {
    if (ids[i] === keepKey) { SPECS[ids[i]] = r; return; }
    const t = document.createElement("div"); t.innerHTML = rowHtml(r);
    box.children[i].replaceWith(t.firstElementChild);
  });
}
function renderLayer3() {
  const sp = layer3Specs();
  $("#layer3").innerHTML = sp[0].items.length ? sp.map(rowHtml).join("")
    : '<div class="row"><span class="empty">Nothing matches the filters above.</span></div>';
}
function syncChecks() {
  document.querySelectorAll("#bar input[data-kind]").forEach(i => { i.checked = isOn(i.dataset.kind, i.dataset.key, i.dataset.id); });
  $("#barcount").textContent = `${synths.filter(visible).length} of ${synths.filter(inView).length} shown`;
}
// what has to be rebuilt: the whole bar (view/class), the checkbox layer (type/category), or just tick marks
function changed(level = "sync", keepKey) {
  state.rev++;
  if (level === "all") renderTop();
  if (level === "all" || level === "layer2") renderLayer2(level === "all" ? null : keepKey);
  if (level === "all" || level === "layer2" || level === "layer3") renderLayer3();
  syncChecks(); renderAll();
}

// things whose options depend on the view
function syncSelectors() {
  const show = (id, on) => { $(id).style.display = on ? "" : "none"; };
  const facs = [...new Set(D.ladders.filter(r => inView(r.synth)).map(r => r.factor))]
    .sort((a, b) => (b === "notes") - (a === "notes") || byName(a, b));
  if (!facs.includes(state.factor)) state.factor = facs[0] ?? null;
  $("#factor").innerHTML = facs.map(f => `<option>${esc(f)}</option>`).join(""); $("#factor").value = state.factor ?? "";
  const tags = [...new Set(D.tags.filter(r => inView(r.synth)).map(r => r.tag + "|" + r.cls))];
  if (!tags.includes(state.tag)) state.tag = tags[0] ?? null;
  $("#tagsel").innerHTML = tags.map(t => { const [x, y] = t.split("|"); return `<option value="${esc(t)}">${esc(x)} (${esc(y)})</option>`; }).join("");
  $("#tagsel").value = state.tag ?? "";
  const L = ladderInfo(), lf = Object.keys(L.ctx).sort((a, b) => (b === "notes") - (a === "notes") || byName(a, b));
  const nls = L.noteLevels.filter(v => v > 0);
  if (!nls.map(String).includes(state.keepNotes)) state.keepNotes = String(nls.includes(1) ? 1 : (nls[0] ?? 1));
  const keepSel = `<span title="Notes steps are hidden except this level. Configs whose ladder has no such level disappear; pick another level to keep them."> keep notes=<select id="keepnotes"${state.hideLadders.has("notes") ? "" : " disabled"}>${nls.map(v => `<option${String(v) === state.keepNotes ? " selected" : ""}>${v}</option>`).join("")}</select></span>`;
  $("#ladderhide").innerHTML = lf.length ? "Hide ladder steps: " + lf.map(f => `<label style="margin-right:8px"><input type="checkbox" data-f="${esc(f)}"${state.hideLadders.has(f) ? " checked" : ""}> ${esc(f)}</label>` + (f === "notes" ? keepSel : "")).join("") : "";
  show("#s-ladder", facs.length > 0);
  show("#s-heat", D.heat.some(r => inView(r.synth)));
  show("#s-inter", D.inter.some(r => inView(r.synth)));
  show("#s-tags", tags.length > 0);
}
const shown = id => $(id).style.display !== "none";
function renderAll() {
  try {
    syncSelectors(); renderTables(); renderTiers();
    if (shown("#s-ladder")) renderLadder();
    if (shown("#s-heat")) { renderHeat(); renderOver(); }
    if (shown("#s-inter")) renderInter();
    if (shown("#s-tags")) renderTags();
  } catch (e) { showErr(e); }
}
function showErr(e) { const b = $("#err"); b.style.display = "block"; b.textContent = "Report error: " + (e && e.stack || e); }
window.addEventListener("error", e => showErr(e.error || e.message));

function init() {
  const m = D.meta;
  $("#meta").textContent = `Generated ${m.generated} \u00b7 ${m.projects} projects` + (m.length ? ` \u00b7 ${m.length}s signal` : "")
    + (m.offline ? "" : " \u00b7 charts load plotly.js from the internet (pip install plotly to make this file work offline)");
  $("#tierkey").innerHTML = Object.entries(D.tierColors).map(([t, c]) => `<span><span class="dot" style="background:${c}"></span> ${esc(t)}</span>`).join("");

  const bar = $("#bar");
  // an effects row changes what the rows below it offer, so it rebuilds the others (never itself, see renderLayer2)
  const lvl = kind => kind === "fx" ? "layer2" : kind === "type" ? "layer3" : "sync";
  const rk = (kind, key) => kind + ":" + key;
  bar.addEventListener("change", e => { const i = e.target; if (!i.dataset.kind) return; setOn(i.dataset.kind, i.dataset.key, i.dataset.id, i.checked); changed(lvl(i.dataset.kind, i.dataset.key), rk(i.dataset.kind, i.dataset.key)); });
  bar.addEventListener("dblclick", e => {            // show only this chip
    const l = e.target.closest(".chip"); if (!l) return;
    const i = l.querySelector("input"), sp = SPECS[i.dataset.kind + ":" + i.dataset.key];
    sp.items.forEach(it => setOn(sp.kind, sp.key, it.id, it.id === i.dataset.id)); changed(lvl(sp.kind, sp.key), rk(sp.kind, sp.key));
  });
  bar.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.view) { state.view = b.dataset.view; return changed("all"); }
    if (b.id === "b-reset") return changed();
    const sp = SPECS[b.dataset.kind + ":" + b.dataset.key]; if (!sp) return;
    sp.items.forEach(it => setOn(sp.kind, sp.key, it.id, b.dataset.act === "all")); changed(lvl(sp.kind, sp.key), rk(sp.kind, sp.key));
  });
  $("#cls").onchange = e => { state.cls = e.target.value; changed("all"); };
  $("#ladderhide").addEventListener("change", e => {
    if (e.target.id === "keepnotes") { state.keepNotes = e.target.value; return changed(); }
    const f = e.target.dataset.f; if (!f) return;
    e.target.checked ? state.hideLadders.add(f) : state.hideLadders.delete(f); changed();
  });
  $("#factor").onchange = e => { state.factor = e.target.value; changed(); };
  $("#tagsel").onchange = e => { state.tag = e.target.value; changed(); };
  $("#heatmetric").onchange = e => { state.metric = e.target.value; changed(); };
  $("#overtop").onchange = e => { state.overTop = +e.target.value; changed(); };
  $("#logy").onchange = e => { state.logy = e.target.checked; changed(); };
  let tm; $("#cond").oninput = e => { clearTimeout(tm); tm = setTimeout(() => { state.cond = e.target.value; changed(); }, 150); };
  $("#factors").innerHTML = D.factors.map(f => "<b>" + esc(f.factor) + "</b>: " + f.levels.map(l => esc(l[0]) + " (" + l[1] + ")").join(", ")).join("<br>");
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  renderTop(); renderLayer2(); renderLayer3(); syncChecks(); renderAll();
}
if (typeof Plotly === "undefined") showErr("plotly.js did not load. If this file was made without the plotly package it needs an internet connection; run pip install plotly and re-run analyze.py for an offline report.");
else init();
})();
"""
