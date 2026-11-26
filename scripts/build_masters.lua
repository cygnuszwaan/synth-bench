-- build_masters.lua : build synth-bench BASE masters (plugin at its default state) inside REAPER.
--
-- What it does, for every row of build_list.tsv (made by scripts/plugins.py list ...):
--   open templates/template.rpp (instruments) or template_fx.rpp (effects)
--   add the plugin to the track's FX chain, check REAPER loaded the plugin you meant
--   Save As masters/<name>.RPP
-- Nothing else is touched, so the result is the same as steps 3.1-3.4 of the README done by hand,
-- except that the plugin keeps whatever state it loads with (no "cheapest setup" tweaks).
--
-- Use:
--   1. In a terminal:  python3 scripts/plugins.py list --folder Reverb --missing
--   2. In REAPER: new empty project (this script discards the open project without asking),
--      Actions > Show action list > New action > Load ReaScript..., pick this file, run it.
--   3. Read masters_build.log in the synth-bench folder. Only "ok" rows were saved.
-- Plugins that open a licence/login dialog on first load will stall the script until you close it.

local OVERWRITE   = false   -- true: rebuild masters that already exist
local ALLOW_FUZZY = false   -- true: also save when REAPER matched a longer name (e.g. "Serum" -> "Serum 2")

local SEP = package.config:sub(1, 1)
local src = debug.getinfo(1, "S").source:sub(2)
local BASE = src:match("^(.*)[/\\]scripts[/\\][^/\\]*$")
if not BASE then
  reaper.ShowMessageBox("Keep this script inside synth-bench/scripts/ so it can find the folder.", "build_masters", 0)
  return
end

local function exists(path)
  local f = io.open(path, "rb")
  if f then f:close() return true end
  return false
end

local function first_existing(...)
  for _, p in ipairs({ ... }) do if exists(p) then return p end end
end

local function norm(s) return (s:lower():gsub("[^%w]", "")) end

local function split_tab(line)
  local out = {}
  for field in (line .. "\t"):gmatch("([^\t]*)\t") do out[#out + 1] = field end
  return out
end

-- ---- read build_list.tsv ----
local list_path = BASE .. SEP .. "build_list.tsv"
local fh = io.open(list_path, "r")
if not fh then
  reaper.ShowMessageBox("build_list.tsv not found. Run:\n  python3 scripts/plugins.py list --folder <name>", "build_masters", 0)
  return
end
local header = split_tab((fh:read("*l") or ""):gsub("\r", ""))
local col = {}
for i, h in ipairs(header) do col[h] = i end
for _, need in ipairs({ "master", "kind", "format", "fx_name" }) do
  if not col[need] then
    reaper.ShowMessageBox("build_list.tsv is missing the column '" .. need .. "'.", "build_masters", 0)
    return
  end
end
local jobs = {}
for raw in fh:lines() do
  local line = raw:gsub("\r", "")
  if line ~= "" then
    local f = split_tab(line)
    jobs[#jobs + 1] = { master = f[col.master], kind = f[col.kind], format = f[col.format], stem = f[col.fx_name] }
  end
end
fh:close()

-- ---- templates ----
local tpl_synth = first_existing(BASE .. SEP .. "templates" .. SEP .. "template.rpp",
                                 BASE .. SEP .. "templates" .. SEP .. "template.RPP")
local tpl_fx    = first_existing(BASE .. SEP .. "templates" .. SEP .. "template_fx.rpp",
                                 BASE .. SEP .. "templates" .. SEP .. "template_fx.RPP")
if not tpl_synth then
  reaper.ShowMessageBox("templates/template.rpp not found. Run: python3 scripts/stamp.py template --length 30", "build_masters", 0)
  return
end
if not reaper.Main_SaveProjectEx then
  reaper.ShowMessageBox("This REAPER has no Main_SaveProjectEx; update REAPER (7.x).", "build_masters", 0)
  return
end
reaper.RecursiveCreateDirectory(BASE .. SEP .. "masters", 0)

local log = io.open(BASE .. SEP .. "masters_build.log", "w")
local function say(msg)
  reaper.ShowConsoleMsg(msg .. "\n")
  if log then log:write(msg .. "\n"); log:flush() end
end

-- ---- loading one plugin ----
-- REAPER's own plugin list maps a file name (ident) to the name it shows, e.g. Serum2.vst3 ->
-- "VST3i: Serum 2 (Xfer Records)". Looking the file up there is exact; guessing a name is the fallback.
local installed = {}
if reaper.EnumInstalledFX then
  local n = 0
  while true do
    local ok, name, ident = reaper.EnumInstalledFX(n)
    if not ok then break end
    local base = (ident or ""):match("([^/\\]+)$") or ""
    local stem, ext = base:match("^(.*)%.([%w]+)$")
    if stem then
      local key = norm(stem) .. "." .. ext:lower()
      installed[key] = installed[key] or name
    end
    n = n + 1
  end
end

local function fx_candidates(job)
  local inst = job.kind == "instrument"
  local pre
  if job.format == "vst3" then pre = inst and "VST3i: " or "VST3: " else pre = inst and "VSTi: " or "VST: " end
  local c = {}
  local exact = installed[norm(job.stem) .. "." .. job.format]
  if exact then c[#c + 1] = exact end
  c[#c + 1] = pre .. job.stem
  c[#c + 1] = job.stem .. "." .. job.format
  c[#c + 1] = job.stem
  if job.stem:find("%s") then c[#c + 1] = pre .. job.stem:gsub("%s+", "") end
  return c, exact ~= nil   -- second value: the first candidate came from REAPER's own list
end

local function classify(track, idx, job)
  local _, full = reaper.TrackFX_GetFXName(track, idx, "")
  local core = full:gsub("^[^:]*:%s*", ""):gsub("%s*%b()%s*$", "")
  local got = norm(core)
  local a, b = norm(job.stem), norm(job.master)
  if got == a or got == b then return "exact", full end
  if (a ~= "" and got:find(a, 1, true)) or (b ~= "" and got:find(b, 1, true)) then return "fuzzy", full end
  return "mismatch", full
end

local function add_plugin(track, job)
  local fuzzy_name, fuzzy_full
  local cands, first_trusted = fx_candidates(job)
  for n, name in ipairs(cands) do
    local idx = reaper.TrackFX_AddByName(track, name, false, -1)
    if idx >= 0 then
      local status, full = classify(track, idx, job)
      if n == 1 and first_trusted then status = "exact" end   -- matched by file name: trust it
      if status == "exact" then
        reaper.TrackFX_SetOpen(track, idx, false)
        reaper.TrackFX_Show(track, idx, 2)
        return "ok", full
      end
      reaper.TrackFX_Delete(track, idx)
      if status == "fuzzy" and not fuzzy_name then fuzzy_name, fuzzy_full = name, full end
    end
  end
  if fuzzy_name then
    if ALLOW_FUZZY then
      local idx = reaper.TrackFX_AddByName(track, fuzzy_name, false, -1)
      if idx >= 0 then
        reaper.TrackFX_Show(track, idx, 2)
        return "fuzzy", fuzzy_full
      end
    end
    return "fuzzy-skipped", fuzzy_full
  end
  return "not-found", ""
end

local counts = {}
local i = 0
say(string.format("build_masters: %d plugins from build_list.tsv", #jobs))

local function step()
  i = i + 1
  local job = jobs[i]
  if not job then
    local parts = {}
    for k, v in pairs(counts) do parts[#parts + 1] = k .. "=" .. v end
    table.sort(parts)
    say("done: " .. table.concat(parts, "  "))
    if log then log:close() end
    return
  end
  local target = BASE .. SEP .. "masters" .. SEP .. job.master .. ".RPP"
  local status, detail
  if (exists(target) or exists(target:gsub("%.RPP$", ".rpp"))) and not OVERWRITE then
    status, detail = "skipped-exists", ""
  else
    local tpl = (job.kind == "effect") and tpl_fx or tpl_synth
    if not tpl then
      status, detail = "no-template", "templates/template_fx.rpp missing (stamp.py signal; stamp.py template-fx)"
    else
      reaper.Main_openProject("noprompt:" .. tpl)
      local track = reaper.GetTrack(0, 0)
      if not track then
        status, detail = "no-track", "template has no track"
      else
        status, detail = add_plugin(track, job)
        if status == "ok" or status == "fuzzy" then
          if reaper.TrackFX_GetCount(track) ~= 1 then
            status, detail = "fx-count", "expected exactly 1 FX on the track"
          else
            reaper.Main_SaveProjectEx(0, target, 0)
            if not exists(target) then status, detail = "save-failed", target end
          end
        end
      end
    end
  end
  counts[status] = (counts[status] or 0) + 1
  say(string.format("[%d/%d] %-14s %-36s %s", i, #jobs, status, job.master, detail))
  reaper.defer(step)   -- one plugin per cycle keeps REAPER responsive; closing the script stops the run
end

step()
