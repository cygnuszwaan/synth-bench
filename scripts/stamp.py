#!/usr/bin/env python3
"""Generate templates / test signal, and stamp benchmark projects from masters.

  python3 scripts/stamp.py template --length 30         plugin-free synth template
  python3 scripts/stamp.py signal --length 30           effects test signal (signals/fx_test.wav)
  python3 scripts/stamp.py template-fx                  effects template (needs the signal first)
  python3 scripts/stamp.py stamp --render-dir /tmp/bench_out --length 30

NAMING (see naming.py): a master is a synth plus any number of conditions, in any order
  masters/Serum-2.rpp                          base: idle + notes=1,2,4,8 (monos: idle + 1)
  masters/Serum-2__mode=granular.rpp           one config, held chord of --config-notes
  masters/Serum-2__mode=granular__unison=4.rpp several conditions at once (a "stack")
  masters/Serum-2__unison=4__notes=4.rpp       notes= sets the chord size (0 = idle)
  masters/Serum-2__mode=granular__notes=ladder.rpp   idle + notes=1,2,4,8 in that config
  Old names still work: Synth__unison__4, Synth__stack__mode-fm+unison-4, Synth__typical.
  Projects are written under one canonical name (keys sorted, notes last), e.g.
  projects/Serum-2__mode=granular__unison=4__notes=8.rpp
  Monos (monos.txt) get 1-note config tests.
EFFECTS (list the plugin names in effects.csv, or effects.txt; masters hold an audio item, no notes)
  masters/<Plugin>.rpp                         -> <Plugin>__preset=typical
  masters/<Plugin>__instances=4.rpp            -> same name (conditions as for synths)
BASELINES
  templates/template.rpp               -> _baseline__empty
  templates/template_fx.rpp            -> _baseline__audio   (only if effects exist)

Changed in every master: item LENGTH, the RENDER_FILE line and, unless
--keep-reaper-tail is given, Reaper's render tail (set to 0 ms). Synth masters also
get new MIDI; effect masters get their audio file path pointed at the test signal.
Plugin state is never touched.
"""
import argparse, array, math, random, re, sys, uuid, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naming

PPQ = 960
BPM = 120
SIGNAL = Path("signals/fx_test.wav")


def rpp_files(folder):
    """All .rpp files in a folder, ignoring extension case (Reaper writes .RPP)."""
    f = Path(folder)
    return sorted(p for p in f.iterdir() if p.suffix.lower() == ".rpp") if f.is_dir() else []


def read_list(path):
    p = Path(path)
    if not p.exists():
        return set()
    return {l.strip() for l in p.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")}


def ticks(sec):
    return round(sec * BPM / 60 * PPQ)


def guid():
    return "{" + str(uuid.uuid4()).upper() + "}"


def midi_lines(n_notes, length, tail):
    """Sustained chord: n_notes held from t=0 until (length - tail)."""
    out = [f"HASDATA 1 {PPQ} QN"]
    pitches = [] if n_notes == 0 else ([48] if n_notes == 1
                                       else [36 + (i * 60) // n_notes for i in range(n_notes)])
    end = ticks(length - tail)
    out += [f"E 0 90 {p:02x} 64" for p in pitches]
    out += [f"E {end if i == 0 else 0} 80 {p:02x} 00" for i, p in enumerate(pitches)]
    last = ticks(length) - 1 - (end if pitches else 0)
    out.append(f"E {last} b0 7b 00")  # all-notes-off just before the item ends
    return out


def project_text(length, render_dir, source_lines):
    src = "\n".join("      " + l for l in source_lines)
    return f'''<REAPER_PROJECT 0.1 "7.0/macOS-arm64" 1700000000
  SAMPLERATE 44100 0 0
  TEMPO {BPM} 4 4
  PLAYRATE 1 0 0.25 4
  RENDER_FILE "{render_dir}"
  RENDER_PATTERN "$project"
  RENDER_FMT 0 2 0
  RENDER_1X 0
  RENDER_RANGE 1 0 0 18 1000
  RENDER_RESAMPLE 3 0 1
  RENDER_ADDTOPROJ 0
  RENDER_STEMS 0
  RENDER_DITHER 0
  <RENDER_CFG
    ZXZhdxgAAQ==
  >
  <TRACK {guid()}
    NAME "bench"
    VOLPAN 1 0 -1 -1 1
    MUTESOLO 0 0 0
    NCHAN 2
    FX 1
    TRACKID {guid()}
    MAINSEND 1 0
    <ITEM
      POSITION 0
      LENGTH {length}
      LOOP 0
      NAME "bench"
      IGUID {guid()}
      GUID {guid()}
{src}
    >
  >
>
'''


def template_text(length, tail, render_dir):
    src = ["<SOURCE MIDI"] + ["  " + l for l in midi_lines(0, length, tail)] + [">"]
    return project_text(length, render_dir, src)


def template_fx_text(length, render_dir, signal):
    return project_text(length, render_dir, ["<SOURCE WAVE", f'  FILE "{signal}"', ">"])


def make_signal(path, seconds, sr=44100, seed=7):
    """Continuous stereo test signal: detuned saw chord with tremolo + pink noise
    + a kick every 0.5 s. Never silent, so no plugin can idle or hit denormals."""
    rnd = random.Random(seed)
    n = int(seconds * sr)
    chord = (110.0, 138.59, 164.81, 220.0)
    beat_len, kick_len = sr // 2, int(0.35 * sr)
    chans = []
    for ch in range(2):
        det = 1.0 + 0.003 * ch
        inc = [f * det / sr for f in chord]
        ph = [0.0, 0.0, 0.0, 0.0]
        b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
        kp = 0.0
        buf = array.array("d", [0.0]) * n
        for i in range(n):
            pad = 0.0
            for k in range(4):
                ph[k] = (ph[k] + inc[k]) % 1.0
                pad += 2.0 * ph[k] - 1.0
            pad *= 0.06 * (0.75 + 0.25 * math.sin(6.283185 * 0.2 * i / sr))
            w = rnd.uniform(-1.0, 1.0)
            b0 = 0.99886 * b0 + w * 0.0555179
            b1 = 0.99332 * b1 + w * 0.0750759
            b2 = 0.96900 * b2 + w * 0.1538520
            b3 = 0.86650 * b3 + w * 0.3104856
            b4 = 0.55000 * b4 + w * 0.5329522
            b5 = -0.7616 * b5 - w * 0.0168980
            pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.05
            b6 = w * 0.115926
            beat = i % beat_len
            kick = 0.0
            if beat < kick_len:
                t = beat / sr
                if beat == 0:
                    kp = 0.0
                kp += (45.0 + 160.0 * math.exp(-t * 35.0)) / sr
                kick = 0.5 * math.sin(6.283185 * kp) * math.exp(-t * 18.0)
            buf[i] = pad + pink + kick
        chans.append(buf)
    peak = max(max(map(abs, c)) for c in chans) or 1.0
    scale = 0.5 / peak * 32767
    pcm = array.array("h", [0]) * (2 * n)
    pcm[0::2] = array.array("h", (int(x * scale) for x in chans[0]))
    pcm[1::2] = array.array("h", (int(x * scale) for x in chans[1]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def stamp_text(text, n_notes, length, tail, render_dir, kind="midi", signal=None,
               keep_tail=False):
    """Returns (new_text, render_tail_was_patched)."""
    lines = text.splitlines()
    out, i = [], 0
    in_item = replaced = len_done = file_done = wave_open = False
    tail_done = keep_tail
    new_mid = midi_lines(n_notes, length, tail) if kind == "midi" else None
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        indent = ln[: len(ln) - len(ln.lstrip())]
        if s.startswith("<ITEM") and not replaced:
            in_item = True
        if in_item and not len_done and re.match(r"LENGTH\s", s):
            out.append(f"{indent}LENGTH {length}")
            len_done = True
            i += 1
            continue
        if kind == "midi" and not replaced and s.startswith("<SOURCE MIDI"):
            j = i + 1
            while not (lines[j].strip() == ">" and
                       lines[j][: len(lines[j]) - len(lines[j].lstrip())] == indent):
                j += 1
            out.append(indent + "<SOURCE MIDI")
            out += [indent + "  " + l for l in new_mid]
            out.append(indent + ">")
            replaced = True
            i = j + 1
            continue
        if kind == "audio":
            if s.startswith("<SOURCE WAVE"):
                wave_open = True
            elif wave_open and s.startswith("FILE"):
                out.append(f'{indent}FILE "{signal}"')
                replaced = True
                i += 1
                continue
            elif wave_open and s == ">":
                wave_open = False
        if s.startswith("RENDER_FILE"):
            out.append(f'{indent}RENDER_FILE "{render_dir}"')
            file_done = True
            i += 1
            continue
        if not keep_tail and s.startswith("RENDER_RANGE"):
            parts = s.split()
            if len(parts) == 6:  # RENDER_RANGE bounds start end tailflag tail_ms
                parts[5] = "0"
                out.append(indent + " ".join(parts))
                tail_done = True
                i += 1
                continue
        out.append(ln)
        i += 1
    if not (replaced and len_done and file_done):
        what = "an audio (WAVE) item" if kind == "audio" else "a MIDI item"
        raise ValueError(f"master needs {what}, an item LENGTH and a RENDER_FILE line "
                         f"(source={replaced}, length={len_done}, render_file={file_done})")
    return "\n".join(out) + "\n", tail_done


def wav_seconds(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("template", "signal", "template-fx", "stamp"):
        p = sub.add_parser(name)
        p.add_argument("--length", type=float, default=30)
        p.add_argument("--tail", type=float, default=10, help="seconds of release after notes end")
        p.add_argument("--render-dir", default="/tmp/bench_out")
    st = sub.choices["stamp"]
    st.add_argument("--poly", type=int, nargs="+", default=[1, 2, 4, 8])
    st.add_argument("--config-notes", type=int, default=8)
    st.add_argument("--clean", action="store_true",
                    help="delete projects/*.rpp that this run did not write")
    st.add_argument("--keep-reaper-tail", action="store_true",
                    help="leave Reaper's render tail setting (default 1000 ms) as saved")
    a = ap.parse_args()

    length = int(a.length) if float(a.length).is_integer() else a.length
    tpl, tpl_fx = Path("templates/template.rpp"), Path("templates/template_fx.rpp")

    if a.cmd == "template":
        tpl.parent.mkdir(exist_ok=True)
        tpl.write_text(template_text(length, a.tail, a.render_dir))
        print("Wrote", tpl)
        return
    if a.cmd == "signal":
        print(f"Generating {length} s test signal (pure Python, may take a minute)...")
        make_signal(SIGNAL, length)
        print("Wrote", SIGNAL)
        return
    if a.cmd == "template-fx":
        if not SIGNAL.exists():
            raise SystemExit("Run 'stamp.py signal --length N' first.")
        tpl_fx.parent.mkdir(exist_ok=True)
        tpl_fx.write_text(template_fx_text(length, a.render_dir, SIGNAL.resolve()))
        print("Wrote", tpl_fx)
        return

    # ---- stamp ----
    Path("projects").mkdir(exist_ok=True)
    Path(a.render_dir).mkdir(parents=True, exist_ok=True)
    monos = read_list("monos.txt")
    try:
        effects, _, _, fx_src = naming.read_effects()
    except ValueError as e:
        raise SystemExit(str(e))
    if "ignored" in fx_src:
        print("note: using effects.csv; effects.txt is ignored (delete it to silence this).")
    sig = SIGNAL.resolve()
    if effects:
        if not SIGNAL.exists():
            raise SystemExit(f"{fx_src} has entries: run 'stamp.py signal' and 'template-fx' first.")
        if wav_seconds(SIGNAL) < length - 0.01:
            raise SystemExit(f"{SIGNAL} is shorter than --length {length}: re-run "
                             f"'stamp.py signal --length {length}'.")
    tpl_fx_found = next((p for p in rpp_files("templates")
                         if p.stem.lower() == "template_fx"), None)
    tpl_found = next((p for p in rpp_files("templates") if p.stem.lower() == "template"), tpl)

    jobs = [("_baseline__empty", tpl_found.read_text(), 0, "midi")]
    if effects:
        if tpl_fx_found is None:
            raise SystemExit("Missing templates/template_fx.rpp: run 'stamp.py template-fx'.")
        jobs.append(("_baseline__audio", tpl_fx_found.read_text(), 0, "audio"))
    seen = {}  # project name -> master file it came from

    def add(name, src, txt, n, kind):
        if name in seen:
            raise SystemExit(f"{src} and {seen[name]} both produce the project '{name}' "
                             "(the same conditions in a different order or old-style spelling). "
                             "Delete one.")
        seen[name] = src
        jobs.append((name, txt, n, kind))

    for m in rpp_files("masters"):
        txt = m.read_text()
        synth, *segs = m.stem.split("__")
        is_fx, is_mono = synth in effects, synth in monos
        if is_fx and "<SOURCE WAVE" not in txt:
            raise SystemExit(f"{m.name}: is an effect (see effects.csv / effects.txt) but has no audio item. "
                             "Build it from templates/template_fx.rpp.")
        if not is_fx and "<SOURCE MIDI" not in txt:
            raise SystemExit(f"{m.name}: has no MIDI item. If it's an effect, add "
                             f"'{synth}' to effects.csv (or effects.txt).")
        if not re.match(r"^[\w.+-]+$", synth):
            raise SystemExit(f"{m.name}: synth name '{synth}' should be letters, digits, - . + _")
        ladder = "notes=ladder" in segs
        if ladder:
            segs = [x for x in segs if x != "notes=ladder"]
            if is_fx or any(x.startswith("notes=") for x in segs):
                raise SystemExit(f"{m.name}: notes=ladder is for synths, and can't be combined "
                                 "with another notes=")
        try:
            if not segs:  # base master
                conds = {} if not is_fx else {"preset": "typical"}
            else:
                conds = naming.parse_segments(
                    segs, None if is_fx else (naming.MONO_NOTES if is_mono else a.config_notes))
        except ValueError as e:
            raise SystemExit(f"{m.name}: {e}")
        if "stack" in conds:
            print(f"note: {m.name}: 'stack' isn't <test>-<level> parts, so it is kept as one "
                  f"condition (stack={conds['stack']}) and gets no interaction ratio.")
        if ladder:
            conds.pop("notes", None)
            for n in [0] + ([1] if is_mono else a.poly):
                add(naming.project_name(synth, {**conds, "notes": str(n)}), m.name, txt, n, "midi")
            continue
        if is_fx:
            if "notes" in conds:
                raise SystemExit(f"{m.name}: effects take audio, not notes; remove notes=")
            add(naming.project_name(synth, conds), m.name, txt, 0, "audio")
        elif not segs:
            add(naming.project_name(synth, {"notes": "0"}), m.name, txt, 0, "midi")
            for n in ([1] if is_mono else a.poly):
                add(naming.project_name(synth, {"notes": str(n)}), m.name, txt, n, "midi")
        else:
            add(naming.project_name(synth, conds), m.name, txt, int(conds.get("notes", 0)), "midi")

    unpatched = 0
    for name, txt, n, kind in jobs:
        try:
            new, tail_ok = stamp_text(txt, n, length, a.tail, a.render_dir, kind, sig,
                                      a.keep_reaper_tail)
        except ValueError as e:
            raise SystemExit(f"{name}: {e}")
        unpatched += not tail_ok
        Path("projects", f"{name}.rpp").write_text(new)
        print(f"projects/{name}.rpp  ({'audio' if kind == 'audio' else str(n) + ' notes'})")
    written = {f"{name}.rpp" for name, *_ in jobs}
    stale = [q for q in rpp_files("projects") if q.name not in written]
    if stale and a.clean:
        for q in stale:
            q.unlink()
        print(f"\nRemoved {len(stale)} stale project(s) from projects/.")
    elif stale:
        print(f"\nWARNING: {len(stale)} file(s) in projects/ were not written by this run "
              "(old names, or masters you removed) and run_bench.py would render them too, "
              "which wastes time and pools them again. Re-run with --clean to delete them:")
        for q in stale[:10]:
            print("  ", q.name)
        if len(stale) > 10:
            print(f"   ... and {len(stale) - 10} more")
    if unpatched:
        print(f"\nWARNING: {unpatched} project(s) had no recognisable RENDER_RANGE line, so "
              "Reaper's render tail was left as saved. Untick 'Tail' in File > Render in "
              "those masters instead.")
    print(f"\n{len(jobs)} projects. Use --length {length} with run_bench.py.")


if __name__ == "__main__":
    main()
