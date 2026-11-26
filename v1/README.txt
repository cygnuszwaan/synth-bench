SYNTH-BENCH: CPU benchmarking of synths via offline Reaper renders (macOS)
==========================================================================

WHAT IT DOES
  Renders the same held notes through each synth with Reaper's command line,
  times each render (CPU seconds), subtracts an empty-project baseline, and
  turns the result into a "load" figure: net CPU seconds per second of audio
  (0.10 = about 10% of one core). Then tiers each synth: workhorse /
  acceptable / avoid?, and draws charts.

FOLDER LAYOUT (run every command from inside synth-bench/)
  synth-bench/
    README.txt
    monos.txt          synths that are monophonic (optional, one name per line)
    effects.txt        effect plugins (optional, one name per line)
    tags.csv           optional: "synth,tag,project" rows; ranks synths per tag
    scripts/           run_bench.py  analyze.py  stamp.py
    templates/         template.rpp (synths), template_fx.rpp (effects), both plugin-free
    signals/           fx_test.wav  (test audio for effects; made by stamp.py signal)
    masters/           YOU create: one project per synth config (see step 3)
    projects/          stamp.py fills this; run_bench.py reads it
    results/           run_*.csv, summary.csv, charts/
    .venv/             Python virtual environment (step 1)

--------------------------------------------------------------------------
STEP 1. ONE-TIME PYTHON SETUP
--------------------------------------------------------------------------
  cd /Applications/Scripts/synth-bench      (or wherever the folder is)
  python3 -m venv .venv
  source .venv/bin/activate
  pip install pandas numpy matplotlib

  In every new terminal window, before analyze.py:
  source .venv/bin/activate        (prompt then starts with (.venv))
  stamp.py and run_bench.py need no extra packages.

  Don't paste lines containing "# comments" into zsh; it treats them as
  arguments.

--------------------------------------------------------------------------
STEP 2. CHECK THE TEMPLATE (once)
--------------------------------------------------------------------------
  1. Quit Reaper fully, then open templates/template.rpp.
  2. File > Render. Confirm:
       Bounds: Entire project      Format: WAV, 24-bit
       Speed: Full-speed offline   Pattern: $project
       Output folder: your scratch folder, e.g. /tmp/bench_out
  3. Save (Cmd+S). Reaper may rewrite the file with an uppercase .RPP
     extension. That's fine; the scripts accept either.
  (Reaper's "Tail 1000 ms" checkbox can be left as is: stamp.py sets the tail
  to 0 in every project it writes. See RENDER TAIL below.)

  To regenerate the template if lost:
  python3 scripts/stamp.py template --length 30

--------------------------------------------------------------------------
STEP 3. MAKE THE MASTERS (per synth)
--------------------------------------------------------------------------
  A master = the template with ONE synth loaded and configured. stamp.py only
  changes the MIDI notes, the item length and the render folder; everything
  about the synth is whatever you saved.

  BASE MASTER  ->  masters/Synth.RPP
    1. Open templates/template.rpp.
    2. Add the synth to the track's FX chain.
    3. Cheapest sensible setup: 1 unison voice, plain oscillator, FX off,
       default quality. Max voices set to at least 8.
    4. File > Save As: masters/Synth.RPP
    The synth name is the file name. Hyphens are fine ("Serum-2");
    never use two underscores in a name.
    Gives: Synth__idle and Synth__poly__1, 2, 4, 8.

  CONFIG MASTERS  ->  masters/Synth__test__level.RPP
    Open the BASE master each time (not the previous variant), change ONE
    thing, Save As. Each plays a held 8-note chord (1 note for monos).

    Test names the analysis understands:
      unison__1, unison__4, unison__8     numeric ladder (cost per step, chart)
                                          (unison__1 = copy of the base)
      mode__granular, mode__wavetable,    one-off configs (heatmap columns)
      mode__fm, mode__spectral
      mode__granular-max                  heaviest settings of that mode
      fx__off, fx__all, fx__reverb        effects section
      quality__hq, quality__oversample    quality toggles
      typical                             your everyday preset; this is what
                                          the tiers are based on if present
      <anything>__<number>                any other numeric ladder, e.g.
                                          grains__8, grains__32
    Use IDENTICAL level names across synths so the heatmap lines up.
    Lowercase, hyphens not underscores.

  STACKED CONFIGS  ->  masters/Synth__stack__a+b.RPP
    e.g. Pigments__stack__mode-granular+unison-4.RPP
    Each part is <test>-<level> of a project you also made alone
    (mode__granular and unison__4). Three+ parts are fine. Make it by
    combining those settings in the base master. The summary reports an
    interaction ratio: 1.0 = costs just add, >1 = worse than the parts
    suggest, <1 = they share cost.

  MONOPHONIC SYNTHS
    Add the synth name to monos.txt (one per line, must match the master
    name, e.g. Minimoog for Minimoog.RPP). They get idle + poly__1 only, 1-note
    config tests, and are tiered as a separate class.

  Tip: also freeze randomness where possible (fixed seeds, retrigger LFOs).

--------------------------------------------------------------------------
STEP 4. STAMP THE PROJECTS
--------------------------------------------------------------------------
  python3 scripts/stamp.py stamp --render-dir /tmp/bench_out --length 30
  (--length defaults to 30)

  Options:
    --length 30        audio length in seconds (baked into each project)
    --tail 10          release seconds after the held notes end
    --poly 1 2 4 8     polyphony ladder (default)
    --config-notes 8   notes for config masters (keep equal to REF_POLY in
                       analyze.py)
    --render-dir PATH  scratch folder (created if missing)
    --keep-reaper-tail leave Reaper's saved render tail (1000 ms) alone

  Re-stamp whenever you change a master, monos.txt, the length or the
  render folder. Delete projects/ files that no longer apply.
  Note /tmp is wiped on reboot; stamp.py recreates the folder.

  The output ends with "N projects"; if it says "1 projects", it found no
  masters (check they're in masters/ and end in .rpp/.RPP).

--------------------------------------------------------------------------
STEP 5. SANITY CHECK ONE PROJECT (recommended before the first full run)
--------------------------------------------------------------------------
  Quit Reaper, then:
  /Applications/REAPER.app/Contents/MacOS/REAPER -nosplash -renderproject projects/Synth__poly__8.rpp
  ls -la /tmp/bench_out
  Open the .wav and listen: 8 held notes, then a release tail.
  Silent? The plugin probably didn't load in the stamped project.

--------------------------------------------------------------------------
STEP 6. RUN THE BENCHMARK
--------------------------------------------------------------------------
  Keep Reaper closed and the Mac otherwise idle.
  caffeinate -i python3 scripts/run_bench.py --runs 3 --length 30 --render-dir /tmp/bench_out

  Options:
    --runs 3           renders per project (your data: 3 is plenty;
                       run-to-run spread was about 1%)
    --length 30        must match the stamped length
    --only Serum       run only projects whose name contains "Serum"
                       (the baseline is always included)
  Rough time: about 4 to 6 seconds per render, so
  projects x runs x 5 s. (21 projects x 3 runs is about 5 minutes.)

  WARNING: the render folder is emptied before each run and at the end.
  Never point --render-dir at a folder with files you want to keep. An empty
  folder afterwards is normal.

  Results accumulate: each run writes a new results/run_*.csv, and analyze.py
  pools them all by project name. So:
    - Adding a new synth later: stamp, then run with --only NewSynth.
    - Changed a master, the length, or want a fresh start? Move the old
      results out first or the old runs will be mixed in:
      mkdir -p results/old && mv results/run_*.csv results/old/

--------------------------------------------------------------------------
STEP 7. ANALYSE
--------------------------------------------------------------------------
  source .venv/bin/activate
  python3 scripts/analyze.py

  Prints a table and writes:
    results/summary.csv                 all metrics, one row per synth
    results/charts/tiers_poly.png       reference load, coloured by tier
    results/charts/tiers_mono.png       (if any monos)
    results/charts/<test>_ladder.png    poly, unison and any numeric ladder
    results/charts/config_heatmap.png   every config/mode/fx test

  Columns:
    idle                      load with synth loaded, no notes
    <test>_cost_per_step      slope of a ladder, e.g. cost per extra voice
    ref_load                  "typical" test, else base config at 8 notes
                              (1 note for monos); this decides the tier
    heaviest                  highest load of any test
    max_spike                 worst wall-clock run vs median. Wall-clock
                              stalls (seen with Pigments) can inflate it
                              without extra CPU use; CPU time is what the
                              load figure uses
    interaction:<a>+<b>       stacking ratio (1.0 = additive)
    tier                      workhorse / acceptable / avoid?
    tier_stable               True if the reference test's fastest and slowest
                              runs both land in the same tier. False means the
                              tier is within run-to-run noise: re-run or treat
                              as borderline
    redundant_in              (with tags.csv) tags where this synth is flagged
                              as redundant; see TAGS below

  TAGS (optional tags.csv, in the synth-bench folder)
    Ranks synths against each other by what they can do. Columns:
      synth,tag,project
    One row per synth AND tag, so a multi-engine synth appears once per
    synthesis type it's capable of. "project" names the test that represents
    that tag for that synth, in the same Test__Level form as the file name
    (mode__granular, mode__fm, typical, ...). Leave it blank to use the
    synth's reference load (typical, else base config).
    Example:
      synth,tag,project
      Vital,wavetable,
      Pigments,granular,mode__granular
      Phase-Plant,granular,mode__granular
      Serum-2,spectral,mode__spectral
    Output: a ranking per tag, printed and saved in results/by_tag.csv, a
    chart results/charts/tags.png (bars show fastest-slowest run), and a
    redundant_in column in summary.csv. A synth is "redundant" in a tag if it
    costs more than 2x (REDUNDANT_FACTOR) the cheapest synth in that tag AND
    is above the workhorse cost for its class. A tag with one synth never flags.
    Tips:
      - Tag by what a synth does and build a master per tag (mode__granular
        etc.) with the same level names across synths. Compare like with like:
        the same source material and comparable settings in each.
      - Synths are ranked separately by class (poly / mono / fx), since their
        tests use different note counts.
      - Synth names must match exactly; a row with no matching results is
        reported at the end of the analysis output.
    Starter file included, based on the tests in your results so far.

  TUNING (constants at the top of scripts/analyze.py)
    SPREAD_STYLE = "size"     how run-to-run spread is drawn on ladder charts:
                              "size" (marker area grows with (max-min)/median),
                              "bars" (min-max whiskers), "both", or "off"
    MARKER_MIN/MARKER_MAX     marker area range; SPREAD_CAP = relative spread
                              (default 30%) at which markers reach full size
    SPREAD_FADE = True        noisier points are also more transparent
    ALPHA_MAX/ALPHA_MIN       opacity of the steadiest / noisiest points
                              (1.0 and 0.30). Noisy points are drawn first so
                              steadier ones stay visible on top
    REF_POLY = 8              keep equal to --config-notes
    THRESHOLDS                (workhorse max, acceptable max) per class.
                              Mono values are placeholders; tune them.
    WARMUP_RUNS = 0           discard leading runs (run 0 wasn't slower)
    REDUNDANT_FACTOR = 2.0    redundancy flag multiple
    MIN_INCREMENT = 0.002     minimum load for an interaction ratio

--------------------------------------------------------------------------
EFFECTS PLUGINS (reverbs, delays, compressors, ...)
--------------------------------------------------------------------------
  Effects process audio, so they get an audio test signal instead of MIDI: a
  continuous stereo mix (detuned saw chord with tremolo, pink noise, a kick
  every half second). It is never silent, so no plugin can idle or hit
  denormal (near-zero) slowdowns.

  ONE-TIME SETUP
    python3 scripts/stamp.py signal --length 30
    python3 scripts/stamp.py template-fx
    1. Open templates/template_fx.rpp, check File > Render as in step 2, save.
    2. List each effect in effects.txt (name = master file name).
    Re-run "signal" and "template-fx" if you change --length (the signal
    must be at least as long as --length; stamp.py checks).

  MASTERS (build them from template_fx.rpp, never from the synth template)
    masters/Hall.RPP                  base, default settings -> Hall__typical
    masters/Hall__heavy.RPP           heaviest settings (long time, high density)
    masters/Hall__quality__hq.RPP     quality / oversampling options
    masters/Hall__instances__4.RPP    4 copies of the plugin on the track;
    masters/Hall__instances__1.RPP    with 1, 4, 8 you get cost per instance
  One change from the base each time, as for synths. Check mix/dry-wet is not
  at 0% (some plugins skip processing when there is nothing to mix).

  HOW IT'S ANALYSED
    Class "fx". Load = CPU above _baseline__audio (an empty track playing the
    same signal), so reading the audio file isn't charged to the plugin.
    Tier uses the "typical" test. THRESHOLDS["fx"] in analyze.py are
    placeholders (0.01, 0.04); tune them. Tag effects by function (reverb,
    compressor, ...) in tags.csv to compare like with like.

  Synth and effect masters can live in the same masters/ folder. stamp.py
  stops with a clear message if a master doesn't match its listing.

--------------------------------------------------------------------------
RENDER TAIL (Reaper's "Tail 1000 ms")
--------------------------------------------------------------------------
  By default Reaper renders 1000 ms of extra audio after the project end. It
  is in the template, so every render ran 1 s longer than --length, which
  inflates every load by about 3% at 30 s. The release of held notes is
  already inside the project (--tail, default 10 s of the 30 s), so the extra
  second isn't needed. stamp.py now sets it to 0 in every project it writes.
  Use --keep-reaper-tail to leave it alone. If stamp.py prints a WARNING about
  RENDER_RANGE, untick Tail in File > Render in your masters instead.
  Changing this changes loads slightly: don't mix pre- and post-change
  results (move old CSVs to results/old/).

--------------------------------------------------------------------------
BUFFER SIZE
--------------------------------------------------------------------------
  Offline rendering isn't tied to the audio device the way live playback is,
  but plugins are still called block by block, so per-block overhead,
  parameter smoothing, FFT/granular frame boundaries and look-ahead can make
  cost vary a little with block size. Whether Reaper's renderer follows the
  device buffer size isn't something I could confirm; measure it once:
    1. Preferences > Audio > Device > Request block size: 128. Quit Reaper.
    2. mkdir -p results/old && mv results/run_*.csv results/old/
       caffeinate -i python3 scripts/run_bench.py --only Pigments --runs 3 --length 30 --render-dir /tmp/bench_out
       python3 scripts/analyze.py && cp results/summary.csv results/summary_buf128.csv
    3. Repeat with 1024 (move the CSVs away first, save as summary_buf1024.csv).
    4. Compare ref_load for one heavy and one light synth. Under about 3%
       difference: ignore buffer size. More: use your normal live size and
       keep it constant, and never pool results from different sizes.
  Also keep constant between runs: sample rate (projects use 44.1 kHz),
  Reaper's preferences, and any plugin "render quality" / HQ options.

--------------------------------------------------------------------------
TROUBLESHOOTING
--------------------------------------------------------------------------
  "externally-managed-environment" from pip
      Use the venv in step 1.
  "No module named numpy" / pandas / matplotlib
      Activate the venv: source .venv/bin/activate
  Only the baseline project gets stamped
      Masters missing, wrong folder, or run from the wrong directory (pwd
      must end in synth-bench).
  Nothing in the render folder after stamp.py
      Normal: stamp.py doesn't render. Rendering happens in run_bench.py,
      which then clears the folder. Test with step 5.
  "Only baseline results so far"
      Run run_bench.py after stamping real masters.
  "listed in effects.txt but has no audio item" / "has no MIDI item"
      The master was built from the wrong template, or the plugin is listed in
      the wrong file. Synths use template.rpp, effects use template_fx.rpp.
  "Effects found but no _baseline__audio results"
      Stamp (needs effects.txt + template_fx) and run run_bench.py again; the
      audio baseline is included in every run.
  "results/ mixes runs with different --length values"
      analyze.py refuses to pool CSVs recorded at different lengths. Move the
      older ones: mkdir -p results/old && mv results/run_<old>.csv results/old/
  Blank slope column (e.g. unison)
      A slope needs two or more numeric levels; add unison__1.
  A stamped project looks wrong in Reaper
      Check masters have exactly one MIDI item. Plugin missing on the
      track? Re-save the master with the synth loaded.
  Odd timings in one run
      Ignore a single wall-clock outlier; medians handle it. Make sure
      nothing else is busy and Reaper isn't open.
  Heavy offline-vs-live differences
      Offline renders don't expose real-time glitching at small buffers; for
      your shortlist, also do a live stress test at your usual buffer size.

QUICK REFERENCE (after masters exist)
  source .venv/bin/activate
  python3 scripts/stamp.py stamp --render-dir /tmp/bench_out --length 30
  caffeinate -i python3 scripts/run_bench.py --runs 3 --length 30 --render-dir /tmp/bench_out
  python3 scripts/analyze.py
