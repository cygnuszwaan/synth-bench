#!/usr/bin/env python3
"""Summarise benchmark CSVs into per-synth metrics, tiers and charts.

"load" = net CPU seconds per second of audio, baseline-subtracted.
         0.10 ~= 10% of one core at realtime.

Optional files in the synth-bench folder:
  monos.txt    one synth name per line; tiered as a separate "mono" class
  effects.txt  one effect-plugin name per line; tiered as class "fx" against the
               audio baseline (_baseline__audio) instead of the empty one
  tags.csv   columns synth,tag[,project]; a synth can have several rows (one per engine /
             synthesis type). project names the test representing that tag for that synth
             (e.g. mode__granular); blank = its reference load. Writes results/by_tag.csv

Test names:  idle, poly (ladder), typical, and anything else you like
  <test>__<number>  -> numeric ladder (cost per step is fitted, ladder chart drawn)
  <test>__<text>    -> one-off configuration (shown in the heatmap)
  stack__<a>+<b>    -> stacked configs, e.g. stack__mode-granular+unison-8, where each
                       part is <test>-<level> of a project you also tested alone.
                       Reports an interaction ratio (1 = additive, >1 = worse than additive).
Usage (from synth-bench/):  python3 scripts/analyze.py
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba

REF_POLY = 8            # base polyphony level for poly synths; keep equal to stamp.py --config-notes
WARMUP_RUNS = 0         # leading runs per project to discard (run 0 wasn't slower in your data)
# (workhorse max, acceptable max) of the reference load, per class. Placeholders: tune them.
THRESHOLDS = {"poly": (0.05, 0.15), "mono": (0.02, 0.06), "fx": (0.01, 0.04)}
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


def col(x):
    return x.test if x.level == "" else f"{x.test}:{x.level}"


def tier(v, cls):
    if pd.isna(v):
        return None
    lo, hi = THRESHOLDS[cls]
    return "workhorse" if v <= lo else "acceptable" if v <= hi else "avoid?"


def rank_tags(g, out):
    """Rank synths within each (tag, class). tags.csv has one row per synth+tag and an
    optional project column naming the test that represents that tag for that synth
    (e.g. mode__granular, or typical). Blank = the synth's reference load."""
    tags = pd.read_csv("tags.csv", dtype=str).fillna("")
    if "project" not in tags:
        tags["project"] = ""
    tags = tags.drop_duplicates(["synth", "tag"])
    cls = dict(zip(out.synth, out["class"]))
    ref = {r.synth: (r.ref_load, r.ref_lo, r.ref_hi) for r in out.itertuples()}
    keyed = g.assign(key=np.where(g.level == "", g.test, g.test + "__" + g.level))
    look = {(r.synth, r.key): (r.load, r.load_lo, r.load_hi) for r in keyed.itertuples()}
    rows, problems = [], []
    for t in tags.itertuples():
        val = look.get((t.synth, t.project)) if t.project else ref.get(t.synth)
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


def make_charts(g, out):
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

    # 2. One ladder chart per test that has numeric levels
    num = g[g.lvl.notna()]
    for t, s in num.groupby("test"):
        if s.groupby("synth").lvl.nunique().max() < 2:
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        pts = []  # (spread fraction, x, y, colour) for every point of every synth
        for synth, x in s.groupby("synth"):
            x = x.sort_values("lvl")
            (line,) = ax.plot(x.lvl, x.load, lw=1.2, label=synth)
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

    # 3. Heatmap of every test except idle and the polyphony ladder
    extra = g[~g.test.isin(["idle", "poly"])].copy()
    extra["col"] = extra.apply(col, axis=1)
    pv = extra.pivot_table(index="synth", columns="col", values="load")
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


def main():
    files = sorted(glob.glob("results/run_*.csv"))
    if not files:
        raise SystemExit("No results/run_*.csv found")
    df = pd.concat([pd.read_csv(f, dtype={"level": str}).assign(src=Path(f).name) for f in files],
                   ignore_index=True)
    if df.length_s.nunique() > 1:
        per_file = df.groupby("src").length_s.agg(lambda x: sorted(set(x))).to_string()
        raise SystemExit("results/ mixes runs with different --length values, which would give "
                         "meaningless medians. Move the older CSVs to results/old/ and rerun.\n"
                         + per_file)
    df = df[(df.returncode == 0) & (df.run >= WARMUP_RUNS)]
    df["level"] = df["level"].fillna("").astype(str)

    g = df.groupby(["project", "synth", "test", "level"], as_index=False).agg(
        wall_med=("wall_s", "median"), wall_max=("wall_s", "max"),
        cpu_med=("cpu_s", "median"), cpu_min=("cpu_s", "min"), cpu_max=("cpu_s", "max"),
        length=("length_s", "first"), n=("run", "count"))

    base = g[g.synth == "_baseline"]
    monos, effects = read_list("monos.txt"), read_list("effects.txt")

    def baseline(test):
        b = base[base.test == test]
        return (b.cpu_med.iloc[0], b.wall_med.iloc[0]) if len(b) else None

    b_empty, b_audio = baseline("empty"), baseline("audio")
    if b_empty is None:
        raise SystemExit("Missing _baseline__empty.rpp results")
    g = g[g.synth != "_baseline"].copy()
    if g.empty:
        raise SystemExit("Only baseline results so far. Add masters, run stamp.py and run_bench.py first.")
    g["cls"] = np.where(g.synth.isin(effects), "fx", np.where(g.synth.isin(monos), "mono", "poly"))
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
    g["lvl"] = pd.to_numeric(g.level, errors="coerce")

    rows = []
    for synth, s in g.groupby("synth"):
        cls = s.cls.iloc[0]
        r = {"synth": synth, "class": cls}
        idle = s[s.test == "idle"]
        r["idle"] = idle.load.iloc[0] if len(idle) else np.nan

        # cost per step for every numeric ladder with >= 2 levels (poly, unison, ...)
        for t, d in s[s.lvl.notna()].groupby("test"):
            if d.lvl.nunique() >= 2:
                d = d.sort_values("lvl")
                r[f"{t}_cost_per_step"] = np.polyfit(d.lvl, d.load, 1)[0]

        # one column per other test/level (poly and idle have their own handling)
        for _, x in s[~s.test.isin(["idle", "poly"])].iterrows():
            r[col(x)] = x.load

        # base config at the standard note count, used as reference and for interactions
        typ = s[s.test == "typical"]
        b = s[(s.test == "poly") & (s.lvl == (1 if cls == "mono" else REF_POLY))]
        typ_row = typ.loc[typ.load.idxmax()] if len(typ) else None
        # effects have no polyphony ladder; "typical" is their base
        base_row = typ_row if cls == "fx" else (b.iloc[0] if len(b) else None)
        base_load = base_row.load if base_row is not None else np.nan
        ref_row = typ_row if typ_row is not None else base_row
        r["ref_load"] = ref_row.load if ref_row is not None else np.nan
        r["ref_lo"] = ref_row.load_lo if ref_row is not None else np.nan
        r["ref_hi"] = ref_row.load_hi if ref_row is not None else np.nan

        # stacking: how much worse than the sum of the parts?
        lookup = {f"{x.test}-{x.level}": x.load for _, x in s.iterrows()}
        for _, x in s[s.test == "stack"].iterrows():
            parts = x.level.split("+")
            if pd.notna(base_load) and all(p in lookup for p in parts):
                inc_sum = sum(lookup[p] - base_load for p in parts)
                if inc_sum > MIN_INCREMENT:
                    r[f"interaction:{x.level}"] = (x.load - base_load) / inc_sum

        r["heaviest"] = s.load.max()
        r["max_spike"] = s.spike.max()
        rows.append(r)

    out = pd.DataFrame(rows)
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
    make_charts(g, out)

    pd.set_option("display.width", 200, "display.max_columns", 20)
    show = [c for c in ["synth", "class", "idle", "poly_cost_per_step", "unison_cost_per_step",
                        "ref_load", "heaviest", "max_spike", "tier", "tier_stable"] if c in out]
    print(out[show].round(4).to_string(index=False))
    inter = [c for c in out if c.startswith("interaction:")]
    if inter:
        print("\nStacking interaction (1.0 = additive, >1 = worse than the parts suggest):")
        print(out[["synth"] + inter].dropna(how="all", subset=inter).round(2).to_string(index=False))
    if by_tag is not None:
        tag_chart(by_tag)
        for (tag, c), gr in by_tag.groupby(["tag", "cls"]):
            print(f"\n[{tag}] ({c}), cheapest first")
            print(gr[["rank", "synth", "project", "load", "x_cheapest", "redundant"]]
                  .round(3).to_string(index=False))
    for p in tag_problems:
        print("tags.csv:", p)
    print("\nFull table: results/summary.csv   Tag ranking: results/by_tag.csv   Charts: results/charts/")


if __name__ == "__main__":
    main()
