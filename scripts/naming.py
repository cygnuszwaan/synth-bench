"""Project-name conditions and the effects list, shared by stamp.py and analyze.py.

A project name is a synth followed by conditions:

    Serum-2__mode=granular__unison=4__notes=8

Any keys, any order, any number. `notes` is the number of held notes (0 = idle) and is
filled in with a default when a name leaves it out. Conditions that mean the same thing
give the same project (key order doesn't matter).

Old-style names are still understood and map onto the same conditions, so earlier results
keep pooling with new ones:

    Synth__idle                 -> notes=0
    Synth__poly__8              -> notes=8
    Synth__typical              -> preset=typical  (any single word: Hall__heavy -> preset=heavy)
    Synth__unison__4            -> unison=4        (any Synth__<test>__<level>)
    Synth__stack__mode-fm+unison-4 -> mode=fm, unison=4
"""
import re

DEFAULT_NOTES = 8   # notes in a config test when a name doesn't say; also the reference level
MONO_NOTES = 1      # same, for synths listed in monos.txt

_TOKEN = re.compile(r"^[\w.+-]+$")


def _legacy(bare):
    if bare == ["idle"]:
        return {"notes": "0"}
    if len(bare) == 1:
        return {"preset": bare[0]}
    if len(bare) == 2 and bare[0] == "poly":
        return {"notes": bare[1]}
    if len(bare) == 2 and bare[0] == "stack":
        out = {}
        for part in bare[1].split("+"):
            k, sep, v = part.partition("-")
            if not (k and sep and v):
                # Not test-level parts (e.g. an old "stack__fx"). Keep it as one opaque
                # condition so old results still load; callers can spot the "stack" key.
                return {"stack": bare[1]}
            out[k] = v
        return out
    if len(bare) == 2:
        return {bare[0]: bare[1]}
    raise ValueError(f"cannot interpret old-style segments {bare}; "
                     "use key=value segments, e.g. mode=granular__unison=4")


def parse_segments(segs, default_notes=None):
    """segs = the parts of a name after the synth. Returns {key: value} (strings)."""
    conds, bare = {}, []
    for s in segs:
        if "=" in s:
            k, v = s.split("=", 1)
            k, v = k.strip(), v.strip()
            if not (_TOKEN.match(k) and _TOKEN.match(v)):
                raise ValueError(f"bad condition '{s}' (use letters, digits, - . + _)")
            if k in conds:
                raise ValueError(f"condition '{k}' appears twice")
            conds[k] = v
        else:
            bare.append(s)
    if bare:
        for k, v in _legacy(bare).items():
            if k in conds:
                raise ValueError(f"condition '{k}' is given both as key=value and old-style")
            conds[k] = v
    if default_notes is not None:
        conds.setdefault("notes", str(default_notes))
    if "notes" in conds:
        if not conds["notes"].isdigit():
            raise ValueError(f"notes must be a whole number, got '{conds['notes']}'")
        conds["notes"] = str(int(conds["notes"]))
    return conds


def parse_cond_string(s, default_notes=None):
    """'mode=granular,unison=4' or 'mode=granular__unison=4' or legacy 'mode__granular'."""
    segs = [x for x in s.replace(",", "__").split("__") if x.strip()]
    return parse_segments(segs, default_notes)


def key(conds):
    return tuple(sorted(conds.items()))


def label(conds, default_notes=None):
    """Short readable form, keys sorted with notes last (as in project names). A notes value equal
    to default_notes is left out; with default_notes=None notes is always shown. Empty = base."""
    items = [(k, v) for k, v in sorted(conds.items()) if k != "notes"]
    if "notes" in conds and not (default_notes is not None and conds["notes"] == str(default_notes)):
        items.append(("notes", conds["notes"]))
    return "__".join(f"{k}={v}" for k, v in items) or "base"


def project_name(synth, conds):
    segs = [f"{k}={v}" for k, v in sorted(conds.items()) if k != "notes"]
    if "notes" in conds:
        segs.append(f"notes={conds['notes']}")
    return "__".join([synth] + segs)


def read_effects(folder="."):
    """Effect plugins and their categories -> (names, meta, cols, source).
    effects.csv wins if it exists: first row is a header, first column the effect name, and every
    other column a category the report can filter by (effect,category[,vendor,...]). Otherwise
    effects.txt: one name per line, no categories. meta = {effect: {column: value}}."""
    import csv
    from pathlib import Path
    d = Path(folder)
    cp, tp = d / "effects.csv", d / "effects.txt"
    if cp.exists():
        with open(cp, encoding="utf-8-sig", newline="") as fh:
            rows = [r for r in csv.reader(fh)
                    if r and any(c.strip() for c in r) and not r[0].lstrip().startswith("#")]
        if not rows:
            return set(), {}, [], "effects.csv"
        header, body = rows[0], rows[1:]
        if header[0].strip().lower() not in ("effect", "effects", "name", "plugin"):
            raise ValueError("effects.csv: the first row must be a header such as effect,category "
                             f"(found '{header[0].strip()}', which would be skipped as a header)")
        cols = [(i, h.strip()) for i, h in enumerate(header) if i and h.strip()]
        names = [h for _, h in cols]
        if len(set(names)) != len(names):
            raise ValueError("effects.csv: duplicate column names in the header")
        meta = {}
        for r in body:
            name = r[0].strip()
            if not name:
                continue
            if name in meta:
                raise ValueError(f"effects.csv: '{name}' is listed twice")
            meta[name] = {h: (r[i].strip() if i < len(r) else "") for i, h in cols}
        return set(meta), meta, names, "effects.csv" + (" (effects.txt ignored)" if tp.exists() else "")
    if tp.exists():
        names = {l.strip() for l in tp.read_text().splitlines()
                 if l.strip() and not l.strip().startswith("#")}
        return names, {n: {} for n in names}, [], "effects.txt"
    return set(), {}, [], ""
