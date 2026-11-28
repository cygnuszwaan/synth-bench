#!/usr/bin/env python3
"""Turn an organised plugin folder into synth-bench inputs, and select subsets by folder.

  python3 scripts/plugins.py scan ~/Plugins/Organised            # writes plugins.tsv
  python3 scripts/plugins.py scan ~/Plugins/Organised --write-effects --write-tags
  python3 scripts/plugins.py list --folder Reverb --missing      # writes build_list.tsv
  python3 scripts/plugins.py list --folder Compressors --folder Limiters --names

The folder tree is the tag source. For  Audio Effects/Dynamics/Compressors/Foo.vst3 :
    kind     = effect                 (top-level folder listed in --fx-top)
    category = dynamics               (broad: the first folder below the top-level one)
    group    = compressors            (fine: the deepest folder, if the plugin is 2+ levels deep)
    tags     = audio-effects|dynamics|compressors  (every folder above the plugin)
Anything not under --fx-top is an instrument.

plugins.tsv is the catalog. build_masters.lua reads build_list.tsv (made by `list`), and
run_bench.py --folder reads plugins.tsv. Nothing here touches Reaper.
"""
import argparse, csv, json, os, plistlib, re, shutil, sys
from pathlib import Path

PLUGIN_EXTS = (".vst3", ".vst")
COLS = ["master", "kind", "format", "fx_name", "category", "group", "tags", "folders", "alt_formats"]
CATALOG = Path("plugins.tsv")
BUILD_LIST = Path("build_list.tsv")


def slug(s):
    """Folder name -> tag: lowercase, anything odd becomes a hyphen."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9.+]+", "-", s.lower())).strip("-")


def master_name(stem):
    """Plugin file stem -> a name synth-bench accepts (letters, digits, - . + ; never '__')."""
    s = re.sub(r"\s+", "-", stem.strip())
    s = s.replace("_", "-")
    s = re.sub(r"[^\w.+-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def read_aliases(path):
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    if rows and rows[0][0].strip().lower() in ("file_stem", "stem", "plugin"):
        rows = rows[1:]
    return {r[0].strip(): r[1].strip() for r in rows if len(r) > 1 and r[1].strip()}


LEGAL_SUFFIX = re.compile(r"[,\s]+(inc|llc|ltd|gmbh|ug|ab|bv|sl|srl|s\.?r\.?l|co|corp|corporation|limited|"
                          r"all rights reserved)\.?$", re.I)


def clean_vendor(raw):
    """'FabFilter GmbH' -> 'FabFilter'; 'Native Instruments' -> 'Native-Instruments' (same style as master names)."""
    v = re.sub(r"(?i)\(c\)|\u00a9|copyright|\b(19|20)\d\d(\s*[-,]\s*(19|20)?\d\d)*\b", " ", raw or "")
    v = v.strip(" .,;:-\t")
    for _ in range(3):
        v = LEGAL_SUFFIX.sub("", v).strip(" .,;:-")
    return master_name(v)


def read_vendor(bundle):
    """Best guess at who made a plugin, from the bundle itself (macOS). '' when nothing usable.
    1. VST3 moduleinfo.json  \"Vendor\"  (what the plugin itself reports to the host)
    2. Info.plist  NSHumanReadableCopyright  (\"(c) 2024 FabFilter\")
    3. Info.plist  CFBundleIdentifier  (com.fabfilter.Pro-Q -> fabfilter; lowercase, so last resort)"""
    b = Path(bundle)
    for rel in ("Contents/Resources/moduleinfo.json", "Contents/moduleinfo.json"):
        try:
            m = re.search(r'"Vendor"\s*:\s*"([^"]+)"', (b / rel).read_text(encoding="utf-8-sig", errors="ignore"))
            if m and clean_vendor(m.group(1)):
                return clean_vendor(m.group(1))
        except OSError:
            pass
    try:
        with open(b / "Contents/Info.plist", "rb") as fh:
            info = plistlib.load(fh)
    except Exception:
        return ""
    v = clean_vendor(str(info.get("NSHumanReadableCopyright", "")))
    if v and not re.fullmatch(r"[\d.\-]*", v):
        return v
    parts = str(info.get("CFBundleIdentifier", "")).split(".")
    return clean_vendor(parts[1]) if len(parts) >= 3 and parts[0].lower() in ("com", "net", "org", "io", "de", "audio") else ""


def read_vendor_map(path):
    """Optional vendors.csv: raw,vendor. Fixes spellings the plugins report ('Valhalla DSP' -> 'Valhalla')."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    if rows and rows[0][0].strip().lower() in ("raw", "found", "from"):
        rows = rows[1:]
    return {clean_vendor(r[0]).lower(): r[1].strip() for r in rows if len(r) > 1 and r[1].strip()}


def scan(root, fx_top, aliases, instr_top="Instruments", kind_all=None, vendor_map=None):
    root = Path(root).expanduser()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a folder")
    # Scanning from inside "Audio Effects" (or "Instruments") itself: count that folder as the top level
    root_is_top = slug(root.name) in (slug(fx_top), slug(instr_top)) and not kind_all
    found = []  # (stem, ext, rel_folders, path)
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root).parts
        if root_is_top:
            rel = (root.name,) + rel
        dirnames.sort()
        keep = []
        for d in dirnames:
            if d.lower().endswith(PLUGIN_EXTS):       # macOS bundle / symlink: a plugin, don't descend
                found.append((d[: d.rfind(".")], d[d.rfind(".") :].lower(), rel, Path(dirpath) / d))
            elif not d.startswith("."):
                keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            if f.lower().endswith(PLUGIN_EXTS):
                found.append((f[: f.rfind(".")], f[f.rfind(".") :].lower(), rel, Path(dirpath) / f))

    by_master, notes = {}, []
    for stem, ext, rel, path in found:
        if not rel:
            notes.append(f"skipped {stem}{ext}: sits in the root, no folder to tag it with")
            continue
        name = aliases.get(stem) or master_name(stem)
        if not name:
            notes.append(f"skipped {stem}{ext}: name is empty after cleaning")
            continue
        rec = by_master.get(name)
        if rec is None:
            by_master[name] = rec = dict(master=name, stems={}, folders=[], exts=set(), paths={})
        elif stem not in rec["stems"] and rec["stems"]:
            notes.append(f"'{stem}' and '{next(iter(rec['stems']))}' both clean to '{name}': "
                         f"kept the first; give one an alias in aliases.csv")
            continue
        rec["stems"].setdefault(stem, ext)
        rec["exts"].add(ext)
        rec["paths"].setdefault(ext, path)
        rec["folders"].append(rel)

    rows = []
    for name in sorted(by_master, key=str.lower):
        rec = by_master[name]
        stem = next(iter(rec["stems"]))
        exts = sorted(rec["exts"], key=lambda e: e != ".vst3")      # prefer VST3
        fmt = exts[0].lstrip(".")
        # the same plugin filed in several folders is one master; first folder decides the category
        folders = []
        for rel in rec["folders"]:
            if rel not in folders:
                folders.append(rel)
        first = folders[0]
        is_fx = (kind_all == "effect") if kind_all else slug(first[0]) == slug(fx_top)
        below = [slug(p) for p in (first if kind_all else first[1:])]
        category = below[0] if below else slug(first[0])          # broad
        group = below[-1] if len(below) >= 2 else ""             # fine
        tags = []
        for rel in folders:
            for p in rel:
                t = slug(p)
                if t and t not in tags:
                    tags.append(t)
        if len(folders) > 1:
            notes.append(f"{name} is in {len(folders)} folders ({' ; '.join('/'.join(f) for f in folders)}); "
                         f"category comes from the first")
        vendor = ""
        for e in exts:                                           # VST3 bundle first, then VST2
            if rec["paths"][e].is_dir():
                vendor = read_vendor(rec["paths"][e])
                if vendor:
                    break
        vendor = (vendor_map or {}).get(vendor.lower(), vendor)
        rows.append(dict(master=name, kind="effect" if is_fx else "instrument", format=fmt, vendor=vendor,
                         fx_name=stem, category=category, group=group,
                         tags="|".join(tags), folders=" ; ".join("/".join(f) for f in folders),
                         alt_formats=",".join(e.lstrip(".") for e in exts[1:])))
    return rows, notes


def write_tsv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def read_catalog(path=CATALOG):
    if not Path(path).exists():
        raise SystemExit(f"{path} not found: run  python3 scripts/plugins.py scan <folder>  first")
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def select(rows, folders=None, kind=None):
    """Rows filed under ANY of the --folder values. 'a/b' means folder a then folder b, contiguous."""
    out = []
    want = [[slug(x) for x in f.replace("\\", "/").split("/") if x] for f in (folders or [])]
    for r in rows:
        if kind and r["kind"] != kind:
            continue
        if want:
            hit = False
            for folder in r["folders"].split(" ; "):
                parts = [slug(p) for p in folder.split("/")]
                for w in want:
                    if any(parts[i:i + len(w)] == w for i in range(len(parts) - len(w) + 1)):
                        hit = True
            if not hit:
                continue
        out.append(r)
    return out


def backup(path):
    p = Path(path)
    if p.exists():
        shutil.copy(p, str(p) + ".bak")
        print(f"  (backed up {p} -> {p}.bak)")


def write_effects_csv(rows):
    old = {}
    if Path("effects.csv").exists():
        with open("effects.csv", encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("effect"):
                    old[r["effect"]] = r
    backup("effects.csv")
    fx = [r for r in rows if r["kind"] == "effect"]
    with open("effects.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["effect", "category", "group", "vendor"])
        for r in fx:
            w.writerow([r["master"], r["category"], r["group"],
                        old.get(r["master"], {}).get("vendor", "").strip() or r.get("vendor", "")])
    print(f"wrote effects.csv: {len(fx)} effects")
    missing = [n for n in old if n not in {r['master'] for r in fx}]
    if missing:
        print(f"  note: {len(missing)} names in the old effects.csv are not in the scan "
              f"(old names that don't match a file? add them to aliases.csv): {', '.join(missing[:8])}"
              f"{' ...' if len(missing) > 8 else ''}")


def write_tags_csv(rows, depth, keep_top=False):
    existing = []
    if Path("tags.csv").exists():
        with open("tags.csv", encoding="utf-8-sig", newline="") as fh:
            existing = [r for r in csv.reader(fh) if r and any(c.strip() for c in r)]
    header = ["synth", "tag", "project"]
    body = [r for r in existing if r[0].strip().lower() != "synth"] if existing else []
    have = {(r[0].strip(), r[1].strip()) for r in body if len(r) > 1}
    added = 0
    for r in rows:
        if r["kind"] != "instrument":
            continue
        tags = r["tags"].split("|")
        tags = tags if keep_top else tags[1:]                  # drop the top-level folder (Instruments)
        tags = tags[-1:] if depth == "leaf" else tags
        for t in tags:
            if (r["master"], t) not in have:
                body.append([r["master"], t, ""])
                have.add((r["master"], t))
                added += 1
    backup("tags.csv")
    with open("tags.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(body)
    print(f"wrote tags.csv: kept {len(body) - added} existing rows, added {added}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="walk the plugin folder and write plugins.tsv")
    s.add_argument("root")
    s.add_argument("--fx-top", default="Audio Effects", help="top-level folder that holds effects")
    s.add_argument("--instr-top", default="Instruments", help="top-level folder that holds instruments")
    s.add_argument("--kind-all", choices=["instrument", "effect"],
                   help="treat EVERYTHING under the scanned folder as this kind (e.g. you scanned a "
                        "folder of reverbs and it has no Audio Effects / Instruments level)")
    s.add_argument("--aliases", default="aliases.csv",
                   help="optional csv: file_stem,master_name (to match names already in your results)")
    s.add_argument("--vendors", default="vendors.csv",
                   help="optional csv: raw,vendor (to tidy the vendor names the plugins report)")
    s.add_argument("--write-effects", action="store_true", help="(over)write effects.csv; vendor values already in it are kept, blanks are filled from the plugins")
    s.add_argument("--write-tags", action="store_true", help="add instrument rows to tags.csv, keeping existing rows")
    s.add_argument("--tag-depth", choices=["leaf", "all"], default="leaf",
                   help="tags.csv: one tag per instrument (deepest folder) or one per folder level")

    l = sub.add_parser("list", help="pick plugins by folder; writes build_list.tsv")
    l.add_argument("--folder", action="append", help="folder name (or a/b path); repeat for several (OR)")
    l.add_argument("--kind", choices=["instrument", "effect"])
    l.add_argument("--missing", action="store_true", help="only plugins with no masters/<name>.rpp yet")
    l.add_argument("--names", action="store_true", help="just print the master names")
    l.add_argument("--out", default=str(BUILD_LIST))

    a = ap.parse_args()
    if a.cmd == "scan":
        rows, notes = scan(a.root, a.fx_top, read_aliases(a.aliases), a.instr_top, a.kind_all,
                           read_vendor_map(a.vendors))
        write_tsv(CATALOG, rows, COLS)
        ne = sum(r["kind"] == "effect" for r in rows)
        print(f"wrote {CATALOG}: {len(rows)} plugins ({len(rows) - ne} instruments, {ne} effects)")
        for n in notes:
            print("  note:", n)
        fx = [r for r in rows if r["kind"] == "effect"]
        got = [r for r in fx if r.get("vendor")]
        if fx:
            from collections import Counter
            print(f"  vendor read from the plugin bundle for {len(got)} of {len(fx)} effects "
                  f"(those left blank keep any vendor already in effects.csv)")
            print("  vendors found: " + ", ".join(f"{v} ({n})" for v, n in Counter(r["vendor"] for r in got).most_common(12))
                  + (" ..." if len({r["vendor"] for r in got}) > 12 else ""))
        tops = sorted({r["folders"].split(" ; ")[0].split("/")[0] for r in rows})
        if rows and ne == 0 and not a.kind_all:
            print(f"  WARNING: 0 effects. A plugin counts as an effect only when it sits under a folder "
                  f"named '{a.fx_top}'. Top-level folders found: {', '.join(tops[:8])}. "
                  f"Use --fx-top NAME, or --kind-all effect if you scanned a folder of effects.")
        elif rows and ne == len(rows) and not a.kind_all and slug(Path(a.root).name) != slug(a.fx_top):
            print("  WARNING: every plugin was classed as an effect; check --fx-top.")
        if a.write_effects:
            write_effects_csv(rows)
        if a.write_tags:
            write_tags_csv(rows, a.tag_depth, bool(a.kind_all))
        return

    rows = select(read_catalog(), a.folder, a.kind)
    if a.missing:
        have = {p.stem.split("__")[0] for p in Path("masters").glob("*") if p.suffix.lower() == ".rpp"}
        rows = [r for r in rows if r["master"] not in have]
    if a.names:
        print("\n".join(r["master"] for r in rows))
        return
    write_tsv(a.out, rows, COLS)
    print(f"wrote {a.out}: {len(rows)} plugins")
    for r in rows[:15]:
        print(f"  {r['kind']:10s} {r['master']:40s} {r['folders']}")
    if len(rows) > 15:
        print(f"  ... and {len(rows) - 15} more")


if __name__ == "__main__":
    main()
