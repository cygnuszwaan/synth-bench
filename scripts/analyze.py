#!/usr/bin/env python3
"""Summarise benchmark CSVs into per-synth metrics, tiers and charts.

"load" = net CPU seconds per second of audio, baseline-subtracted.
         0.10 ~= 10% of one core at realtime.

Optional files in the synth-bench folder:
  monos.txt    one synth name per line; tiered as a separate "mono" class
  effects.csv  effect plugins and their categories: a header row, the effect name in the
               first column and any other columns (category, vendor, ...) as categories that
               report.html can filter by, e.g.  effect,category  /  Hall,reverb.
  effects.txt  (used if there is no effects.csv) one effect-plugin name per line; tiered as class "fx" against the
               audio baseline (_baseline__audio) instead of the empty one
  tags.csv   columns synth,tag[,project]; a synth can have several rows (one per engine /
             synthesis type). project names the conditions representing that tag for that
             synth (e.g. mode=granular, or mode=granular__unison=4); blank = its reference
             load. Writes results/by_tag.csv

Project names are a synth plus conditions (see naming.py):
  Serum-2__mode=granular__unison=4__notes=8      any keys, any order, any number
  Old names (Serum__poly__8, Serum__unison__4, Serum__stack__mode-fm+unison-4, Serum__typical)
  are translated to the same conditions, so old and new results pool.
What the analysis does with conditions:
  numeric factor   a ladder: cost per step is fitted wherever one factor varies with the rest
                   held fixed (notes, unison, grains, ...), and a ladder chart is drawn
  any condition    a heatmap column and a summary.csv column
  2+ conditions    a stack: reports an additive interaction ratio (1 = costs just add,
                   >1 = worse than the parts suggest) and a multiplicative one (1 = costs
                   multiply, the natural null for things like unison x notes)
Usage (from synth-bench/):  python3 scripts/analyze.py
"""
import glob, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naming
import report

REF_POLY = 8            # base polyphony level for poly synths; keep equal to stamp.py --config-notes
WARMUP_RUNS = 0         # leading runs per project to discard (run 0 wasn't slower in your data)
# (workhorse max, acceptable max) of the reference load, per class. Placeholders: tune them.
THRESHOLDS = {"poly": (0.05, 0.15), "mono": (0.02, 0.06), "fx": (0.01, 0.04)}
HTML_REPORT = True       # also write results/report.html (interactive charts and tables)
FILTER_FACTORS = ("mode",)  # report.html gets a row of filter chips for each of these conditions
REDUNDANT_FACTOR = 2.0  # flagged if > 2x the cheapest synth with the same tag
MIN_INCREMENT = 0.002   # interaction ratio is skipped if the parts add less load than this
# How run-to-run spread is drawn on the ladder charts:
#   "size" = marker area grows with (max-min)/median of the runs   "bars" = min-max whiskers
#   "both" = both                                                  "off"  = small plain markers
SPREAD_STYLE = "size"
MARKER_MIN, MARKER_MAX = 6, 140   # marker area range (points^2)
SPREAD_CAP = 0.30                 # relative spread at which the marker reaches MARKER_MAX
SPREAD_FADE = True                # noisier points are also more transparent (size styles only)
ALPHA_MAX, ALPHA_MIN = 1.0, 0.30  # opacity of the steadiest / noisiest (>= SPREAD_CAP) points
TIER_COLORS = {"workhorse": "#2e9e5b", "acceptable": "#e0a020", "avoid?": "#c94040"}


def read_list(path):
    p = Path(path)
    if not p.exists():
        return set()
    return {l.strip() for l in p.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")}


_NUM = re.compile(r"^\d+(\.\d+)?$")


def is_num(v):
    return bool(_NUM.match(str(v)))


def default_notes(cls):
    """Notes a name without notes= means, by class (legacy names; stamp.py writes notes=)."""
    return None if cls == "fx" else (naming.MONO_NOTES if cls == "mono" else REF_POLY)


def level_sort(v):
    return (not is_num(v), float(v) if is_num(v) else 0.0, str(v))


def tier(v, cls):
    if pd.isna(v):
        return None
    lo, hi = THRESHOLDS[cls]
    return "workhorse" if v <= lo else "acceptable" if v <= hi else "avoid?"


def rank_tags(g, out):
    """Rank synths within each (tag, class). tags.csv has one row per synth+tag and an
    optional project column naming the conditions that represent that tag for that synth
    (e.g. mode=granular, mode__granular, mode=granular__unison=4, or typical). Blank = the
    synth's reference load."""
    tags = pd.read_csv("tags.csv", dtype=str).fillna("")
    if "project" not in tags:
        tags["project"] = ""
    tags = tags.drop_duplicates(["synth", "tag"])
    cls = dict(zip(out.synth, out["class"]))
    ref = {r.synth: (r.ref_load, r.ref_lo, r.ref_hi) for r in out.itertuples()}
    look = {(r.synth, r.pname): (r.load, r.load_lo, r.load_hi) for r in g.itertuples()}
    rows, problems = [], []
    for t in tags.itertuples():
        val = None
        if t.synth in cls:
            if t.project:
                try:
                    conds = naming.parse_cond_string(t.project, default_notes(cls[t.synth]))
                except ValueError as e:
                    problems.append(f"{t.synth} / {t.tag}: project '{t.project}': {e}")
                    continue
                val = look.get((t.synth, naming.project_name(t.synth, conds)))
            else:
                val = ref.get(t.synth)
        if t.synth not in cls or val is None or pd.isna(val[0]):
            problems.append(f"{t.synth} / {t.tag}: no results" + (f" for {t.project}" if t.project else ""))
            continue
        rows.append(dict(tag=t.tag, cls=cls[t.synth], synth=t.synth,
                         project=t.project or "reference", load=val[0], lo=val[1], hi=val[2]))
    if not rows:
        return None, problems
    df = pd.DataFrame(rows)
    grp = df.groupby(["tag", "cls"]).load
    df["rank"] = grp.rank(method="min").astype(int)
    cheapest = grp.transform("min")
    df["x_cheapest"] = np.where(cheapest > 0, df.load / cheapest, np.nan)
    floor = df.cls.map(lambda c: THRESHOLDS[c][0])  # cheap in absolute terms = never redundant
    df["redundant"] = (df.x_cheapest > REDUNDANT_FACTOR) & (df.load > floor)
    return df.sort_values(["tag", "cls", "rank"]), problems


def tag_chart(df):
    groups = list(df.groupby(["tag", "cls"]))
    heights = [max(1.3, 0.4 * len(gr) + 0.9) for _, gr in groups]
    fig, axes = plt.subplots(len(groups), 1, figsize=(8, sum(heights)), squeeze=False,
                             gridspec_kw={"height_ratios": heights})
    for ax, ((tag, c), gr) in zip(axes[:, 0], groups):
        gr = gr.sort_values("load", ascending=False)  # cheapest ends up on top
        err = [(gr.load - gr.lo).clip(lower=0), (gr.hi - gr.load).clip(lower=0)]
        ax.barh(gr.synth, gr.load, xerr=err, error_kw=dict(lw=1, capsize=2),
                color=["#c94040" if r else "#4a7fb5" for r in gr.redundant])
        ax.set_title(f"{tag} ({c})", fontsize=9, loc="left")
        ax.set_xlabel("load (bars: fastest-slowest run; red = redundant vs cheapest)", fontsize=7)
    fig.tight_layout()
    fig.savefig(Path("results/charts") / "tags.png", dpi=150)
    plt.close(fig)


def make_charts(g, out, lad):
    d = Path("results/charts")
    d.mkdir(parents=True, exist_ok=True)

    # 1. Reference load per synth, coloured by tier, one chart per class
    for cls, o in out.dropna(subset=["ref_load"]).groupby("class"):
        o = o.sort_values("ref_load")
        fig, ax = plt.subplots(figsize=(8, max(3, 0.35 * len(o) + 1)))
        ax.barh(o.synth, o.ref_load, color=[TIER_COLORS.get(str(t), "gray") for t in o.tier])
        for v in THRESHOLDS[cls]:
            ax.axvline(v, ls="--", c="gray")
        ax.set_xlabel("load (net CPU s per audio s)")
        ax.set_title(f"Reference load by synth ({cls})")
        fig.tight_layout()
        fig.savefig(d / f"tiers_{cls}.png", dpi=150)
        plt.close(fig)

    # 2. One ladder chart per numeric factor. Each line is one synth with the other conditions
    #    held fixed; lines at a non-base setting are labelled "synth @ other conditions".
    for t, s in (lad.groupby("factor") if len(lad) else []):
        if s.groupby("line").lvl.nunique().max() < 2:  # needs one line with two levels
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        pts = []  # (spread fraction, x, y, colour) for every point of every synth
        for lab, x in s.groupby("line"):
            x = x.sort_values("lvl")
            (line,) = ax.plot(x.lvl, x.load, lw=1.2, label=lab)
            c = line.get_color()
            if SPREAD_STYLE in ("bars", "both"):
                ax.vlines(x.lvl, x.load_lo, x.load_hi, color=c, lw=1, alpha=0.8)
            if SPREAD_STYLE in ("size", "both"):
                fr = (x.rel_range.fillna(0).clip(upper=SPREAD_CAP) / SPREAD_CAP).to_numpy()
            else:
                fr = np.zeros(len(x))
            pts += list(zip(fr, x.lvl, x.load, [c] * len(x)))
        # Draw the noisiest (largest, faintest) points first so steadier ones sit on top
        pts.sort(key=lambda p: -p[0])
        if pts:
            fr = np.array([p[0] for p in pts])
            sizes = MARKER_MIN + (MARKER_MAX - MARKER_MIN) * fr
            alpha = ALPHA_MAX - (ALPHA_MAX - ALPHA_MIN) * fr if SPREAD_FADE else np.full(len(fr), ALPHA_MAX)
            face = [to_rgba(p[3], al) for p, al in zip(pts, alpha)]
            edge = [to_rgba(p[3], 1.0) for p in pts]
            ax.scatter([p[1] for p in pts], [p[2] for p in pts], s=sizes, facecolors=face,
                       edgecolors=edge, linewidths=0.8, zorder=3)
        ax.set_xlabel(t)
        ax.set_ylabel("load")
        ax.set_title(f"Load vs {t}")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=2)
        sz = f"larger, fainter marker = more run-to-run spread (range / median, max at {SPREAD_CAP:.0%}+)"
        notes = {"size": sz if SPREAD_FADE else sz.replace(", fainter", ""),
                 "bars": "whiskers = fastest to slowest run",
                 "both": "whiskers = fastest to slowest run; " + sz,
                 "off": ""}[SPREAD_STYLE]
        if notes:
            fig.text(0.5, 0.008, notes, ha="center", fontsize=7, color="gray")
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(d / f"{t}_ladder.png", dpi=150)
        plt.close(fig)

    # 3. Heatmap of every condition set except bare notes (idle and the polyphony ladder)
    cfg = g[g.is_cfg]
    pv = cfg.pivot_table(index="synth", columns="col", values="load")
    if not pv.empty:
        fig, ax = plt.subplots(figsize=(max(6, 0.9 * pv.shape[1] + 2),
                                        max(3, 0.4 * len(pv) + 1.5)))
        im = ax.imshow(pv.values, aspect="auto", cmap="YlOrRd")
        ax.set_xticks(range(pv.shape[1]))
        ax.set_xticklabels(pv.columns, rotation=60, ha="right", fontsize=7)
        ax.set_yticks(range(len(pv)))
        ax.set_yticklabels(pv.index)
        fig.colorbar(im, label="load")
        ax.set_title("Configuration tests")
        fig.tight_layout()
        fig.savefig(d / "config_heatmap.png", dpi=150)
        plt.close(fig)


def parse_projects(df, monos, effects):
    """Work out each project's synth, class and conditions from its name.
    Returns (df with synth/cls/pname columns, {pname: conds}, {bad name: reason}, n_aliases).
    pname is the canonical project name, so old and new spellings of one test share it."""
    df = df.copy()
    df["synth"] = df.project.str.split("__").str[0]
    df["cls"] = np.where(df.synth.isin(effects), "fx", np.where(df.synth.isin(monos), "mono", "poly"))
    pname, conds_of, bad = {}, {}, {}
    for proj, synth, cls in df[["project", "synth", "cls"]].drop_duplicates().itertuples(index=False):
        if synth == "_baseline":
            pname[proj], conds_of[proj] = proj, {}
            continue
        try:
            c = naming.parse_segments(proj.split("__")[1:], default_notes(cls))
        except ValueError as e:
            bad[proj] = str(e)
            continue
        pname[proj] = naming.project_name(synth, c)
        conds_of[pname[proj]] = c
    df["pname"] = df.project.map(pname)
    df = df[df.pname.notna()]
    aliases = df.groupby("pname").project.nunique()
    return df, conds_of, bad, int((aliases > 1).sum())


def stack_interactions(synth, cls, rows, typ_row, dn):
    """One record per project with 2+ non-notes conditions. Base = the same-notes project with
    no conditions (effects: the 'typical' project); singles = base + one condition each."""
    recs, problems = [], []
    for r in rows.values():
        parts = sorted((k, v) for k, v in r.conds.items() if k != "notes")
        if len(parts) < 2:
            continue
        n = r.conds.get("notes")
        ctx = {"notes": n} if n is not None else {}
        base = typ_row if cls == "fx" else rows.get(naming.key(ctx))
        name = "+".join(f"{k}={v}" for k, v in parts)
        if n is not None and int(n) != dn:
            name += f"@notes={n}"
        singles = [rows.get(naming.key({**ctx, k: v})) for k, v in parts]
        missing = [f"{k}={v}" for (k, v), x in zip(parts, singles) if x is None]
        if base is None or missing:
            problems.append(f"{synth} {name}: no "
                            + ("base project" if base is None else "single-condition project for "
                                                                   + ", ".join(missing))
                            + ", so no interaction ratio")
            continue
        bl = base.load
        inc_sum = sum(x.load - bl for x in singles)
        rec = dict(synth=synth, name=name, load=r.load, base_load=bl, conds=dict(r.conds),
                   additive_pred=bl + inc_sum, ratio=np.nan, mult_pred=np.nan, mult_ratio=np.nan)
        if inc_sum > MIN_INCREMENT:
            rec["ratio"] = (r.load - bl) / inc_sum
            if bl > 0:
                rec["mult_pred"] = bl * np.prod([x.load / bl for x in singles])
                rec["mult_ratio"] = r.load / rec["mult_pred"]
        recs.append(rec)
    return recs, problems


def main():
    files = sorted(glob.glob("results/run_*.csv"))
    if not files:
        raise SystemExit("No results/run_*.csv found")
    df = pd.concat([pd.read_csv(f).assign(src=Path(f).name) for f in files], ignore_index=True)
    if df.length_s.nunique() > 1:
        per_file = df.groupby("src").length_s.agg(lambda x: sorted(set(x))).to_string()
        raise SystemExit("results/ mixes runs with different --length values, which would give "
                         "meaningless medians. Move the older CSVs to results/old/ and rerun.\n"
                         + per_file)
    df = df[(df.returncode == 0) & (df.run >= WARMUP_RUNS)]
    monos = read_list("monos.txt")
    try:
        effects, fx_meta, fx_cols, fx_src = naming.read_effects()
    except ValueError as e:
        raise SystemExit(str(e))
    if "ignored" in fx_src:
        print("note: using effects.csv; effects.txt is ignored (delete it to silence this).")
    df, conds_of, bad, n_alias = parse_projects(df, monos, effects)

    g = df.groupby(["pname", "synth", "cls"], as_index=False).agg(
        wall_med=("wall_s", "median"), wall_max=("wall_s", "max"),
        cpu_med=("cpu_s", "median"), cpu_min=("cpu_s", "min"), cpu_max=("cpu_s", "max"),
        length=("length_s", "first"), n=("run", "count"))
    g["conds"] = g.pname.map(conds_of)

    base = g[g.synth == "_baseline"]

    def baseline(name):
        b = base[base.pname == f"_baseline__{name}"]
        return (b.cpu_med.iloc[0], b.wall_med.iloc[0]) if len(b) else None

    b_empty, b_audio = baseline("empty"), baseline("audio")
    if b_empty is None:
        raise SystemExit("Missing _baseline__empty.rpp results")
    g = g[g.synth != "_baseline"].copy()
    if g.empty:
        raise SystemExit("Only baseline results so far. Add masters, run stamp.py and run_bench.py first.")
    is_fx = (g.cls == "fx").to_numpy()
    if is_fx.any() and b_audio is None:
        raise SystemExit("Effects found but no _baseline__audio results: stamp and run it too.")
    ba = b_audio or (0.0, 0.0)
    b_cpu = np.where(is_fx, ba[0], b_empty[0])
    b_wall = np.where(is_fx, ba[1], b_empty[1])

    g["load"] = (g.cpu_med - b_cpu).clip(lower=0) / g.length
    g["load_lo"] = (g.cpu_min - b_cpu).clip(lower=0) / g.length   # fastest run
    g["load_hi"] = (g.cpu_max - b_cpu).clip(lower=0) / g.length   # slowest run
    g["rel_range"] = (g.load_hi - g.load_lo) / g.load.where(g.load > 0)
    g["wall_load"] = (g.wall_med - b_wall).clip(lower=0) / g.length
    g["spike"] = g.wall_max / g.wall_med  # worst run vs median (wall-clock; includes stalls)
    g["is_cfg"] = g.conds.map(lambda c: bool(set(c) - {"notes"}))
    g["col"] = [naming.label(c) for c in g.conds]  # notes always shown: mode=fm__notes=8

    rows, ladders, inter_all, inter_problems, over_rows = [], [], [], [], []
    for synth, s in g.groupby("synth"):
        cls = s.cls.iloc[0]
        dn = default_notes(cls)
        ref_n = naming.MONO_NOTES if cls == "mono" else REF_POLY
        r = {"synth": synth, "class": cls}
        by = {naming.key(x.conds): x for x in s.itertuples()}
        idle = by.get(naming.key({"notes": "0"}))
        r["idle"] = idle.load if idle else np.nan

        # Ladders: a numeric factor varying while every other condition stays fixed.
        groups = {}
        for x in s.itertuples():
            for f, v in x.conds.items():
                if not is_num(v) or (f == "notes" and float(v) == 0):
                    continue
                ctx = {k: w for k, w in x.conds.items() if k != f}
                groups.setdefault((f, naming.key(ctx)), (ctx, []))[1].append((float(v), x))
        for (f, _), (ctx, pts) in sorted(groups.items(), key=lambda kv: kv[0][0]):
            is_base = not (set(ctx) - {"notes"}) and (f == "notes" or ctx.get("notes") in (None, str(ref_n)))
            lvls = sorted({v for v, _ in pts})
            if len(lvls) >= 2:
                d = sorted(pts, key=lambda p: p[0])
                slope = np.polyfit([v for v, _ in d], [x.load for _, x in d], 1)[0]
                r[f"{f}_cost_per_step" + ("" if is_base else f"@{naming.label(ctx, dn)}")] = slope
            if len(lvls) >= 2 or is_base:
                line = synth if is_base else f"{synth} @ {naming.label(ctx, dn)}"
                ladders += [dict(synth=synth, factor=f, line=line, lvl=v, load=x.load,
                                 load_lo=x.load_lo, load_hi=x.load_hi, rel_range=x.rel_range,
                                 pname=x.pname, conds=x.conds)
                            for v, x in pts]

        # one column per condition set (bare notes = idle and the polyphony ladder are separate)
        for x in s[s.is_cfg].itertuples():
            r[x.col] = x.load

        # base config at the standard note count, used as reference and for interactions
        typs = [x for x in s.itertuples()
                if {k: v for k, v in x.conds.items() if k != "notes"} == {"preset": "typical"}]
        typ_row = next((x for x in typs if x.conds.get("notes") in (None, str(ref_n))), None)
        if typ_row is None and typs:
            typ_row = max(typs, key=lambda x: x.load)
        b = by.get(naming.key({"notes": str(ref_n)})) if cls != "fx" else None
        # effects have no polyphony ladder; "typical" is their base
        base_row = typ_row if cls == "fx" else b
        base_load = base_row.load if base_row is not None else np.nan
        ref_row = typ_row if typ_row is not None else base_row
        r["ref_load"] = ref_row.load if ref_row is not None else np.nan
        r["ref_lo"] = ref_row.load_lo if ref_row is not None else np.nan
        r["ref_hi"] = ref_row.load_hi if ref_row is not None else np.nan

        # stacking: how much worse than the sum (or product) of the parts?
        recs, probs = stack_interactions(synth, cls, by, base_row if cls == "fx" else None, dn)
        inter_problems += probs
        for rec in recs:
            inter_all.append(rec)
            if pd.notna(rec["ratio"]):
                r[f"interaction:{rec['name']}"] = rec["ratio"]

        # cost over base: each project with conditions minus the base project at the same notes
        # (effects: minus their preset=typical project). The interval pairs the fastest run of one
        # with the slowest of the other, so "resolved" means the difference is bigger than run noise.
        for x in s[s.is_cfg].itertuples():
            if cls == "fx":
                b_row = typ_row if typ_row is not None and x.pname != typ_row.pname else None
            else:
                nn = x.conds.get("notes")
                b_row = by.get(naming.key({"notes": nn})) if nn is not None else None
            if b_row is None:
                continue
            lo, hi = x.load_lo - b_row.load_hi, x.load_hi - b_row.load_lo
            over_rows.append(dict(
                pname=x.pname, synth=synth, conditions=x.col, load=x.load, base_load=b_row.load,
                over_base=x.load - b_row.load, over_lo=lo, over_hi=hi,
                x_base=x.load / b_row.load if b_row.load >= MIN_INCREMENT else np.nan,
                resolved=bool(lo > 0 or hi < 0)))

        r["heaviest"] = s.load.max()
        r["max_spike"] = s.spike.max()
        rows.append(r)

    over = pd.DataFrame(over_rows, columns=["pname", "synth", "conditions", "load", "base_load",
                                            "over_base", "over_lo", "over_hi", "x_base", "resolved"])
    g = g.merge(over[["pname", "base_load", "over_base", "over_lo", "over_hi", "x_base"]],
                on="pname", how="left")
    over.drop(columns="pname").to_csv("results/cost_over_base.csv", index=False)

    out = pd.DataFrame(rows)
    fx_keys = []  # effect categories become summary columns (named fx_<col> if that name is taken)
    for col in fx_cols:
        key = col if col not in out.columns else f"fx_{col}"
        out.insert(2 + len(fx_keys), key, [fx_meta.get(s_, {}).get(col, "") for s_ in out.synth])
        fx_keys.append((col, key))
    out["tier"] = [tier(v, c) for v, c in zip(out.ref_load, out["class"])]
    # does the fastest-to-slowest run range of the reference test stay in the same tier?
    out["tier_stable"] = [None if t is None else (tier(lo, c) == t and tier(hi, c) == t)
                          for t, lo, hi, c in zip(out.tier, out.ref_lo, out.ref_hi, out["class"])]
    out = out.sort_values(["class", "ref_load"], ascending=[False, True])  # poly, mono, fx

    by_tag, tag_problems = (rank_tags(g, out) if Path("tags.csv").exists() else (None, []))
    if by_tag is not None:
        flagged = by_tag[by_tag.redundant].groupby("synth").tag.agg(", ".join)
        out["redundant_in"] = out.synth.map(flagged).fillna("")
        by_tag.to_csv("results/by_tag.csv", index=False)

    out.to_csv("results/summary.csv", index=False)
    inter = pd.DataFrame(inter_all, columns=["synth", "name", "load", "base_load", "additive_pred",
                                             "ratio", "mult_pred", "mult_ratio", "conds"])
    inter = inter.rename(columns={"name": "conditions", "ratio": "add_ratio"})
    inter.drop(columns="conds").to_csv("results/interactions.csv", index=False)
    lad = pd.DataFrame(ladders)
    make_charts(g, out, lad)

    pd.set_option("display.width", 200, "display.max_columns", 20)
    show = [c for c in ["synth", "class", *[k for _, k in fx_keys], "idle", "notes_cost_per_step", "unison_cost_per_step",
                        "ref_load", "heaviest", "max_spike", "tier", "tier_stable"] if c in out]
    print(out[show].round(4).to_string(index=False))

    # what the names were read as: catches typos like "unision" or "mode=Granular"
    facs = {}
    for c in g.conds:
        for k, v in c.items():
            facs.setdefault(k, {}).setdefault(v, 0)
            facs[k][v] += 1
    fac_list = [(k, sorted(facs[k].items(), key=lambda kv: level_sort(kv[0])))
                for k in sorted(facs, key=lambda k: (k != "notes", k))]
    print("\nConditions found (factor: levels, with number of projects):")
    for k, lv in fac_list:
        print(f"  {k}: " + ", ".join(f"{v} ({n})" for v, n in lv))

    if len(inter):
        shown = inter.assign(dev=np.abs(np.log(inter.mult_ratio.where(inter.mult_ratio > 0))))
        shown = shown.sort_values(["dev", "add_ratio"], ascending=False, na_position="last")
        print("\nStacking interactions, biggest surprise first.\n"
              "  add_ratio  = measured increment / sum of the single increments (1.0 = costs add)\n"
              "  mult_ratio = measured load / (base x product of each condition's multiplier)\n"
              "               (1.0 = costs multiply; unison x notes style scaling counts as normal)")
        print(shown[["synth", "conditions", "load", "add_ratio", "mult_ratio"]]
              .round(3).to_string(index=False))
    if len(over):
        top = over.sort_values("over_base", ascending=False).head(15)
        print(f"\nCost over base: each project minus the base project at the same notes (effects: minus\n"
              f"preset=typical). Biggest first, top {len(top)} of {len(over)}; '~' = within run-to-run spread.\n"
              f"x_base is left blank when the base is under {MIN_INCREMENT}.")
        print(top.assign(over_base=[f"{v:.4f}" + ("" if ok else " ~") for v, ok in zip(top.over_base, top.resolved)])
              [["synth", "conditions", "load", "base_load", "over_base", "x_base"]].round(3).to_string(index=False))
    for p in inter_problems:
        print("interactions:", p)
    if by_tag is not None:
        tag_chart(by_tag)
        for (tag, c), gr in by_tag.groupby(["tag", "cls"]):
            print(f"\n[{tag}] ({c}), cheapest first")
            print(gr[["rank", "synth", "project", "load", "x_cheapest", "redundant"]]
                  .round(3).to_string(index=False))
    for p in tag_problems:
        print("tags.csv:", p)
    if n_alias:
        print(f"\nNote: {n_alias} project(s) were recorded under more than one name spelling "
              "(old and new style) and have been pooled.")
    if bad:
        print(f"\nWARNING: {len(bad)} project name(s) in the results could not be read and were "
              "skipped:")
        for k, why in sorted(bad.items()):
            print(f"  {k}: {why}")
    if HTML_REPORT:
        try:
            offline = report.write_html("results/report.html", out, g, lad, inter, by_tag, fac_list,
                                        THRESHOLDS, TIER_COLORS, FILTER_FACTORS, fx_keys)
            print("\nInteractive report: results/report.html"
                  + ("" if offline else "  (needs internet to open; pip install plotly makes it "
                                        "self-contained)"))
        except Exception as e:  # never lose the CSV/PNG outputs over the report
            print(f"\nWARNING: could not write results/report.html: {e!r}")
    print("\nFull table: results/summary.csv   Interactions: results/interactions.csv   "
          "Tag ranking: results/by_tag.csv   Cost over base: results/cost_over_base.csv   "
          "Charts: results/charts/")


if __name__ == "__main__":
    main()
