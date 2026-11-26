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
    effects.csv        effect plugins and their categories (optional, see step 5)
    effects.txt        older alternative: effect plugin names, one per line (no categories)
    tags.csv           optional: "synth,tag,project" rows; ranks synths per tag
    scripts/           run_bench.py  analyze.py  stamp.py  naming.py (shared name parser)
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
  pip install pandas numpy matplotlib plotly
  (plotly is only for the interactive report; analyze.py works without it, but then
  results/report.html needs an internet connection to open. With it, the report is a
  single self-contained file, about 5 MB, that works offline.)

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
    Gives: Synth__notes=0 (idle) and Synth__notes=1, 2, 4, 8.

  CONDITION MASTERS  ->  masters/Synth__key=value__key=value.RPP
    Every test is a synth plus any number of conditions, each a key=value pair, in any
    order. Open the BASE master each time (not the previous variant), set the patch up as
    the name says, Save As. Each plays a held 8-note chord (1 note for monos) unless the
    name has notes=.
      Serum-2__mode=granular.RPP                  one condition
      Serum-2__mode=granular__unison=4.RPP        two at once (a "stack")
      Serum-2__fx=all__mode=fm__unison=8.RPP      three at once; keys can be anything
      Serum-2__unison=4__notes=4.RPP              notes=N sets the chord size (0 = idle)
    NOTE LADDER INSIDE A CONFIG
      masters/Serum-2__mode=granular__notes=ladder.RPP  gives idle + notes=1,2,4,8 in
      granular mode (the --poly levels), from ONE master. Notes are never stored in a
      master (stamp.py writes the MIDI), so there is no need to save a copy per note count.
      The analysis then reports notes_cost_per_step@mode=granular and draws it as its own
      line on notes_ladder.png. Each ladder master adds idle plus one project per --poly level (5 by default),
      so use it for the configs you care about. The bare Synth.RPP is the same thing for
      the base config, plus it is what ref_load and interaction ratios are measured against.
      Which config the base is doesn't matter to the analysis: it needs no cheapest mode.
    Keys and values: letters, digits, hyphen, dot, plus; never two underscores in a row.
    The name is a promise about the patch: nothing checks that the plugin state matches it.
    Use IDENTICAL keys and levels across synths so tables and rankings line up, and
    lowercase them: "Mode=Granular" and "mode=granular" are different conditions. The
    analysis prints every factor and level it found ("Conditions found"), so a typo such
    as "unision" shows up as its own factor.

    Keys with special meaning:
      notes=N        held notes. 0 is idle. Left out of a name, it means 8 (1 for monos).
      preset=typical your everyday preset; this is what the tiers are based on if present.
                     Any other preset=name is just an ordinary condition. (The old names
                     "Synth__typical" and "Hall__heavy" still work and mean preset=...)
    Anything numeric becomes a ladder (see ANALYSE): unison=1,4,8 or grains=8,32. The same
    holds for any other factor you vary with the rest held fixed, e.g. unison=1,4,8 inside
    mode=granular.

    What the analysis does with a stack: the conditions it combines are compared with
    the base config and with each condition alone at the same notes. So before the
    stack mode=granular__unison=4 can be judged, mode=granular and unison=4 need projects
    of their own (and so does the base). A stack with a missing part is listed under
    "interactions:" in the output, not silently dropped.

  OLD NAMES  still work everywhere (existing masters and results do not need renaming):
      Synth__unison__4                      = Synth__unison=4
      Synth__stack__mode-fm+unison-4        = Synth__mode=fm__unison=4
      Synth__typical                        = Synth__preset=typical
      Synth__poly__8 / Synth__idle          = Synth__notes=8 / Synth__notes=0
    Both spellings give the same project, so old and new results pool. stamp.py writes
    projects under one canonical name (keys sorted, notes last):
      masters/Pigments__stack__mode-fm+unison-4.RPP
        -> projects/Pigments__mode=fm__unison=4__notes=8.rpp
    and stops if two masters would give the same project (e.g. Synth__a=1__b=2 next to
    Synth__b=2__a=1). A malformed old stack name such as Synth__stack__fx becomes a single
    opaque condition stack=fx (shown in heatmap and summary, no interaction ratio).

  MONOPHONIC SYNTHS
    Add the synth name to monos.txt (one per line, must match the master
    name, e.g. Minimoog for Minimoog.RPP). They get idle + notes=1 only, 1-note
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

    --clean            delete projects/*.rpp that this run did not write
  Re-stamp whenever you change a master, monos.txt, the length or the
  render folder. stamp.py warns about files in projects/ it did not write (old
  names, removed masters). run_bench.py would render those too, so use --clean.
  Note /tmp is wiped on reboot; stamp.py recreates the folder.

  The output ends with "N projects"; if it says "1 projects", it found no
  masters (check they're in masters/ and end in .rpp/.RPP).

--------------------------------------------------------------------------
STEP 5. SANITY CHECK ONE PROJECT (recommended before the first full run)
--------------------------------------------------------------------------
  Quit Reaper, then:
  /Applications/REAPER.app/Contents/MacOS/REAPER -nosplash -renderproject projects/Synth__notes=8.rpp
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
    results/report.html                 INTERACTIVE report (open in a browser; see below)
    results/summary.csv                 all metrics, one row per synth
    results/charts/tiers_poly.png       reference load, coloured by tier
    results/charts/tiers_mono.png       (if any monos)
    results/interactions.csv            one row per stack: measured vs predicted
    results/cost_over_base.csv          each project's load minus its base (see below)
    results/charts/<factor>_ladder.png  notes, unison and any other numeric factor
    results/charts/config_heatmap.png   every config/mode/fx test

  THE INTERACTIVE REPORT (results/report.html)
    One page with the summary table, tier bars, ladders, config heatmap, interactions, tag
    ranking and a table of every project. The PNGs are still written too.
    The header filters in layers, and each layer only offers what survived the one above:
      1. VIEW        Instruments | Effects (with counts). Everything on the page, including
                     the summary columns, the ladder factors and the tag list, follows the
                     view. A tab is hidden if there is nothing to switch to.
      2. TYPE or CATEGORY
         Instruments: a Type row with one chip per type. Types belong to PROJECTS, and
                     the row filters the ladders, heatmap, interactions and project table
                     as well as the instruments:
                       - a project with a mode has that mode's type: the tag of the
                         mode=X row in tags.csv (mode=va -> analog), or the mode value
                         itself if no row names it. mode=granular__unison=4 is granular.
                       - a project with no mode (the base config, its notes ladder,
                         unison=4, ...) has the instrument's baseline type: its tag rows
                         with a blank project.
                       - a tag whose project has more conditions (e.g. combo,
                         mode=granular__unison=4) also applies to every project that has
                         those conditions (notes ignored unless the tag names them).
                       - a project left with no type is "untyped".
                     An instrument has every type any of its projects has, and is shown
                     while at least one of them is ticked. Only tags whose project has
                     results count. Every tag in tags.csv becomes a Type chip, so keep
                     tags.csv to types of sound. A Class select (poly / mono) appears next
                     to the tabs when there are several classes.
         Effects:    one row per effects.csv column (category, vendor, ...). Empty cells are
                     under "uncategorised".
      3. WHAT SURVIVES
         Instrument / Effect chips for the plugins that passed layers 1 and 2 (alphabetical),
         then one row per FILTER_FACTORS condition (default: none) listing only the levels
         that those plugins actually have, plus "no <condition>" for projects without one.
    Every row has All / None, which act on the chips shown, and double-click shows only that
    chip. A plugin you untick stays unticked if a Type filter hides it and later brings it back.
    The Type row and any FILTER_FACTORS rows filter the ladders, heatmap, interactions and the
    project table (the summary and tier bars are per plugin, so they only follow which plugins
    have a ticked type). Other conditions can get a row: add them to FILTER_FACTORS in
    analyze.py, e.g. ("quality",).
    Reset zoom resets the zoom on every chart.
    In the charts:
      hover         over a ladder LINE (not just its points) to see its legend name; the other
                    lines dim. Tooltips show load and the fastest and slowest run.
      legend        click an entry to hide that line, double-click to show only it.
      zoom          drag a box to zoom, scroll to zoom, double-click the plot to reset.
                    The toolbar on each chart also has pan and a PNG download.
      Ladders       pick any numeric factor in the dropdown; tick "log scale" to read cheap
                    and heavy synths on one chart.
      Heatmap       type words into "Filter conditions" to narrow the columns
                    (e.g. "granular unison=4" shows only conditions containing both);
                    put a minus in front of a word to exclude it ("granular -unison").
                    "Hide ladder steps" has a checkbox per numeric factor (unison, grains,
                    ...). It hides every project that is a step on that ladder: the same
                    other conditions measured at 2+ levels by any synth, so unison=1,4,8
                    and also the same ladder inside granular. A stack that merely includes
                    unison=4 together with other conditions stays.
                    The notes box works the same way for the polyphony ladders (notes=0,1,2,4,8
                    inside a mode), except that one notes level is kept: "keep notes=" defaults
                    to 1, so each laddered config collapses to its 1-note result. A config
                    whose ladder was not measured at the kept level disappears, so pick another
                    level there. Configs with no notes ladder (e.g. a mode measured only at 8
                    notes) are not steps and stay. To show only the 1-note results across the
                    whole heatmap, type notes=1 in the filter box instead.
      Tables        click a column heading to sort.
    The page follows your system's light or dark mode. Everything is computed when you run
    analyze.py; re-run it to refresh the report. Set HTML_REPORT = False in analyze.py to skip it.

  Columns:
    idle                      load with synth loaded, no notes
    <factor>_cost_per_step    slope of a ladder, e.g. notes_cost_per_step = cost per extra
                              voice, unison_cost_per_step. If the ladder was measured with
                              other conditions held fixed, they follow an @, e.g.
                              unison_cost_per_step@mode=granular
    ref_load                  preset=typical, else base config at 8 notes
                              (1 note for monos); this decides the tier
    heaviest                  highest load of any test
    max_spike                 worst wall-clock run vs median. Wall-clock
                              stalls (seen with Pigments) can inflate it
                              without extra CPU use; CPU time is what the
                              load figure uses
    <condition>               one column per project with conditions, named by them, with
                              the note count always shown (notes last): mode=granular__notes=8,
                              preset=typical__notes=8, mode=granular__unison=4__notes=8.
                              Poly synths play 8 notes in config tests and monos 1, so
                              mode=fm__notes=8 and mode=fm__notes=1 are different columns.
                              Effects have no notes, so no suffix.
    interaction:<a>+<b>       additive stacking ratio (1.0 = additive); several parts allowed,
                              and @notes=N if the stack is at a non-default note count
    tier                      workhorse / acceptable / avoid?
    tier_stable               True if the reference test's fastest and slowest
                              runs both land in the same tier. False means the
                              tier is within run-to-run noise: re-run or treat
                              as borderline
    redundant_in              (with tags.csv) tags where this synth is flagged
                              as redundant; see TAGS below

  COST OVER BASE (results/cost_over_base.csv, report.html, and the top 15 printed)
    For every project that has conditions: its load minus the BASE project at the same note
    count (the bare Synth.RPP's notes=N project). For effects the base is preset=typical.
    So mode=granular__notes=4 is compared with notes=4, not notes=8, and a stack is compared
    with the plain base. Columns: load, base_load, over_base (the difference, in load units),
    x_base (load / base_load, blank when the base is under MIN_INCREMENT), over_lo and over_hi,
    and resolved.
      over_lo / over_hi   a deliberately conservative range: the fastest run minus the base's
                          slowest run, and the slowest minus the base's fastest.
      resolved            True when that range excludes zero, i.e. the difference is larger
                          than run-to-run noise. False (shown with ~ in the printout and as a
                          faded bar in the report) means "can't tell this from the base".
    Both loads already have the empty-project baseline taken off, so over_base is the cost the
    condition adds. This is the number to use for "what does this FX / mode / unison setting
    cost": an effect built into a synth (fx=all) and the same effect placed after it
    (after=hall) can be compared directly this way. A cost that does not depend on polyphony
    shows up as the same over_base at notes=1,2,4,8 (use a notes=ladder master with the
    condition applied). Projects with no base at their notes, and the base projects
    themselves, have no row. In the report the heatmap has a "Show" selector
    (load / cost over base / x base) and a ranked bar chart under it, with "Rank top"
    to limit it; both follow the same filters (synths, type, hide ladder steps, text box).

  INTERACTIONS (results/interactions.csv, and printed after the main table)
    For each stack: load measured, the base load, and two predictions made from the
    parts measured alone (each part's increment over the base):
      add_ratio   measured increment / sum of the single increments. 1.0 = costs add.
      mult_ratio  measured load / (base x product of each part's multiplier). 1.0 = costs
                  multiply. Things like unison x notes x engine scale each other, so for
                  those add_ratio comes out above 1 even when nothing unusual happens;
                  mult_ratio is the one that flags a real surprise.
    The printed table is sorted by distance from mult_ratio = 1, biggest surprise first.
    Ratios are left blank when the parts together add less than MIN_INCREMENT load.

  RENAMED OUTPUT (from the key=value change; the numbers are unchanged)
    poly_cost_per_step -> notes_cost_per_step       poly_ladder.png -> notes_ladder.png
    summary.csv columns: unison:4 -> unison=4, mode:granular -> mode=granular,
    typical -> preset=typical, stack:a-x+b-y -> a=x__b=y,
    interaction:a-x+b-y -> interaction:a=x+b=y
    Config columns now always end in notes=N (previously the default 8, or 1 for monos, was
    left out, so one column mixed poly 8-note and mono 1-note results):
    mode=granular -> mode=granular__notes=8, preset=typical -> preset=typical__notes=8.
    Notes now come last in every label, as in project names.

  TAGS (optional tags.csv, in the synth-bench folder)
    Ranks synths against each other by what they can do. Columns:
      synth,tag,project
    One row per synth AND tag, so a multi-engine synth appears once per
    synthesis type it's capable of. "project" names the conditions that
    represent that tag for that synth, as in the file name (mode=granular,
    mode=granular__unison=4, preset=typical; old forms like mode__granular and typical also
    work). Use __ between conditions, not a comma, because it's a CSV file. Leave it blank to use the
    synth's reference load (typical, else base config).
    In report.html each tag is also a TYPE (the Type row in the header) for projects: a blank
    project is the synth's baseline type, a mode project names the type of that mode's
    projects, and a project with more conditions (mode=granular__unison=4) also tags every
    project matching them.
    Example:
      synth,tag,project
      Vital,wavetable,
      Pigments,granular,mode=granular
      Phase-Plant,granular,mode=granular
      Serum-2,spectral,mode=spectral
      Pigments,granular-unison,mode=granular__unison=4
    Output: a ranking per tag, printed and saved in results/by_tag.csv, a
    chart results/charts/tags.png (bars show fastest-slowest run), and a
    redundant_in column in summary.csv. A synth is "redundant" in a tag if it
    costs more than 2x (REDUNDANT_FACTOR) the cheapest synth in that tag AND
    is above the workhorse cost for its class. A tag with one synth never flags.
    Tips:
      - Tag by what a synth does and build a master per tag (mode=granular
        etc.) with the same level names across synths. Compare like with like:
        the same source material and comparable settings in each. The project can be
        any set of conditions, so a tag can also rank synths at matched settings
        (mode=granular__unison=4, if every synth in that tag has that project).
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
    MIN_INCREMENT = 0.002     minimum summed load increment for an interaction ratio
    HTML_REPORT = True        write results/report.html

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
    2. List each effect in effects.csv (name = master file name). The first row is a header,
       the first column is the effect name, and every other column is a category the report
       can filter by:
           effect,category,vendor
           Hall,reverb,Acme
           Plate,reverb,Acme
           Echo,delay,Bright
           Squash,dynamics,
       Use any columns you like (category, vendor, character, ...); each becomes a row of
       filter chips in report.html, and a column in summary.csv. Leave a cell empty for
       "uncategorised". Use the same spelling every time ("reverb", not "Reverb"). Comment
       lines starting with # and blank lines are ignored, and Excel/Numbers csv exports work.
       A plain effects.txt (one name per line) still works, with no categories. If both
       files exist, effects.csv is used and you get a note saying effects.txt is ignored.
    Re-run "signal" and "template-fx" if you change --length (the signal
    must be at least as long as --length; stamp.py checks).

  MASTERS (build them from template_fx.rpp, never from the synth template)
    masters/Hall.RPP                  base, default settings -> Hall__preset=typical
    masters/Hall__preset=heavy.RPP    heaviest settings (long time, high density)
    masters/Hall__quality=hq.RPP      quality / oversampling options
    masters/Hall__instances=4.RPP     4 copies of the plugin on the track;
    masters/Hall__instances=1.RPP     with 1, 4, 8 you get cost per instance
    masters/Hall__instances=4__quality=hq.RPP   conditions combine as for synths
    (Effects take no notes= condition. The old names Hall__heavy, Hall__quality__hq,
    Hall__instances__4 still work.)
  One change from the base each time, as for synths. Check mix/dry-wet is not
  at 0% (some plugins skip processing when there is nothing to mix).

  HOW IT'S ANALYSED
    Class "fx". Load = CPU above _baseline__audio (an empty track playing the
    same signal), so reading the audio file isn't charged to the plugin.
    Tier uses the preset=typical project. THRESHOLDS["fx"] in analyze.py are
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
  report.html opens but charts are blank, with a "plotly.js did not load" message
      The report was made without the plotly package and you are offline. Run
      pip install plotly (in the venv) and re-run analyze.py.
  "WARNING: could not write results/report.html"
      The CSVs and PNGs were still written. The message says why; the cause is usually a
      read-only results/ folder or a corrupted plotly install.
  Only the baseline project gets stamped
      Masters missing, wrong folder, or run from the wrong directory (pwd
      must end in synth-bench).
  Nothing in the render folder after stamp.py
      Normal: stamp.py doesn't render. Rendering happens in run_bench.py,
      which then clears the folder. Test with step 5.
  "Only baseline results so far"
      Run run_bench.py after stamping real masters.
  "is an effect ... but has no audio item" / "has no MIDI item"
      The master was built from the wrong template, or the plugin is listed in
      the wrong file. Synths use template.rpp, effects use template_fx.rpp.
  "Effects found but no _baseline__audio results"
      Stamp (needs effects.csv or effects.txt + template_fx) and run run_bench.py again; the
      audio baseline is included in every run.
  "results/ mixes runs with different --length values"
      analyze.py refuses to pool CSVs recorded at different lengths. Move the
      older ones: mkdir -p results/old && mv results/run_<old>.csv results/old/
  Blank slope column (e.g. unison)
      A slope needs two or more numeric levels, with every other condition identical
      (including notes); add unison=1.
  "no single-condition project for ..." under interactions
      A stack is judged against its parts: make a project for each condition alone, at the
      same notes, plus the base config at that notes. Or the name has a typo; check the
      "Conditions found" list.
  "both produce the project ..." from stamp.py
      Two masters have the same conditions (maybe one in old style). Delete one.
  "N file(s) in projects/ were not written by this run"
      Old-name project files from before the key=value change. stamp.py --clean removes them.
  "project name(s) could not be read and were skipped"
      A name in an old results CSV fits neither style (e.g. three bare segments). The
      message says which; rename the project in the CSV, or ignore the data.
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
