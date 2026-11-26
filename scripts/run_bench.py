#!/usr/bin/env python3
"""Time offline Reaper renders of each project in projects/.

Project naming (made by stamp.py): Synth__key=value__key=value..., e.g.
  Serum__notes=0.rpp   Serum__notes=8.rpp   Serum__mode=granular__unison=4__notes=8.rpp
Older names (Serum__poly__8, Serum__unison__8, Serum__stack__a-x+b-y) still run and still pool
with new ones; analyze.py works out the conditions from the name.
Baseline (required): _baseline__empty.rpp  (empty project, same length)

Usage (from synth-bench/):
  caffeinate -i python3 scripts/run_bench.py --runs 6 --length 60 --render-dir /tmp/bench_out
"""
import argparse, csv, random, resource, subprocess, time
from datetime import datetime
from pathlib import Path

REAPER = "/Applications/REAPER.app/Contents/MacOS/REAPER"


def cpu_children():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def clean(render_dir):
    if render_dir:
        for f in Path(render_dir).glob("*"):
            if f.is_file():
                f.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default="projects")
    ap.add_argument("--out", default="results")
    ap.add_argument("--runs", type=int, default=6, help="run 0 is warm-up, dropped later")
    ap.add_argument("--length", type=float, required=True, help="audio length in seconds")
    ap.add_argument("--render-dir", help="scratch folder your projects render into (wiped between runs)")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--only", help="substring filter on project name")
    a = ap.parse_args()

    projects = sorted(p for p in Path(a.projects).glob("*") if p.suffix.lower() == ".rpp")
    if a.only:
        projects = [p for p in projects if a.only in p.name or p.name.startswith("_baseline")]
    if not projects:
        raise SystemExit("No .rpp files found")

    Path(a.out).mkdir(exist_ok=True)
    out = Path(a.out) / f"run_{datetime.now():%Y%m%d_%H%M%S}.csv"
    fields = ["timestamp", "project", "synth", "run",
              "wall_s", "cpu_s", "length_s", "returncode"]

    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        # Interleave: each pass runs every project once in shuffled order,
        # so thermal drift / background noise is spread evenly across synths.
        for run in range(a.runs):
            order = projects[:]
            random.shuffle(order)
            for p in order:
                synth = p.stem.split("__")[0]
                clean(a.render_dir)
                c0, t0 = cpu_children(), time.perf_counter()
                try:
                    rc = subprocess.run([REAPER, "-nosplash", "-renderproject", str(p)],
                                        timeout=a.timeout, capture_output=True).returncode
                except subprocess.TimeoutExpired:
                    rc = -999
                wall = time.perf_counter() - t0
                cpu = cpu_children() - c0
                w.writerow(dict(timestamp=datetime.now().isoformat(timespec="seconds"),
                                project=p.stem, synth=synth,
                                run=run, wall_s=round(wall, 3), cpu_s=round(cpu, 3),
                                length_s=a.length, returncode=rc))
                fh.flush()
                print(f"run {run} {p.stem:40s} wall {wall:7.2f}s cpu {cpu:7.2f}s rc={rc}")
    clean(a.render_dir)
    print("Wrote", out)


if __name__ == "__main__":
    main()
