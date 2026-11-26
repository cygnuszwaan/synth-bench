"""Project-name conditions, shared by stamp.py and analyze.py.

A project name is a synth followed by conditions:

    Serum-2__mode=granular__unison=4__notes=8

Any keys, any order, any number. `notes` is the number of held notes (0 = idle) and is
filled in with a default when a name leaves it out. Conditions that mean the same thing
give the same project (key order doesn't matter).

Old-style names are still understood and map onto the same conditions, so earlier results
keep pooling with new ones:

    Synth__idle                 -> notes=0
    Synth__poly__8              -> notes=8
    Synth__typical              -> preset=typical
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
    if bare == ["typical"]:
        return {"preset": "typical"}
    if len(bare) == 2 and bare[0] == "poly":
        return {"notes": bare[1]}
    if len(bare) == 2 and bare[0] == "stack":
        out = {}
        for part in bare[1].split("+"):
            k, sep, v = part.partition("-")
            if not (k and sep and v):
                raise ValueError(f"stack part '{part}' should look like test-level")
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
            conds[k] = v
        else:
            bare.append(s)
    if bare:
        for k, v in _legacy(bare).items():
            conds.setdefault(k, v)
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
    """Short readable form; the default notes value is left out, empty means the base config."""
    items = [(k, v) for k, v in sorted(conds.items())
             if not (k == "notes" and default_notes is not None and v == str(default_notes))]
    return "__".join(f"{k}={v}" for k, v in items) or "base"


def project_name(synth, conds):
    segs = [f"{k}={v}" for k, v in sorted(conds.items()) if k != "notes"]
    if "notes" in conds:
        segs.append(f"notes={conds['notes']}")
    return "__".join([synth] + segs)
