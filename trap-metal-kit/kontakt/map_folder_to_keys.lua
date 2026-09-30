-- map_folder_to_keys.lua
--
-- Kontakt 8 Lua API script: maps every audio file in a folder onto its own key,
-- one sample per key, so you can trigger different songs/loops/stems and blend
-- them like a DJ.
--
-- Run it:
--   1. Kontakt > Options (F12) > Developer > tick "Enable developer features".
--   2. Put your audio in a folder called "samples" next to this script (or change
--      CONFIG.sample_dir below).
--   3. Kontakt > File > "Run Lua script..." (F11) and pick this file.
--      Ctrl+F11 re-runs the last script.
--
-- The API calls used here come from the Kontakt Lua API reference manual
-- (docs.native-instruments.com/ni-tech-manuals/kontakt-api-reference-manual).
-- The script has been exercised against a mock of that API, not inside Kontakt
-- itself, so the parts marked BEST EFFORT below may need a tweak on your machine.
--
-- SECURITY: Kontakt's Lua environment exposes the os/io libraries. Only run
-- Lua scripts you have read and trust.

local kt = Kontakt
local fs = Filesystem

local CONFIG = {
  sample_dir      = fs.join(kt.script_path, "samples"),
  name            = "Trap DJ Keys",

  first_key       = 36,     -- MIDI note of the first sample. Kontakt names 60 as C3, so 36 = C1.
  white_keys_only = false,  -- true = skip black keys (nicer for playing by hand)
  overrides       = {},     -- pin a file to a key: [40] = "vocal_chop.wav" (a name inside sample_dir)

  loop            = true,   -- BEST EFFORT: loop each sample while its key is held
  loop_mode       = "until_release",  -- one of Kontakt.sample_loop_modes
  loop_index      = nil,    -- nil = try loop slots 0 and 1 (the manual doesn't say which base is used)

  tempo_sync      = true,   -- BEST EFFORT: time-stretch files named like "..._140_BPM.wav" to host tempo
  reset_multi     = false,  -- true wipes the whole rack first. Leave false to add alongside what's loaded.
  save_to         = nil,    -- absolute path ending in .nki to save the result, or nil to skip
}

-- Another Lua script can set a global MAPPER_CONFIG table before dofile()-ing this one to override
-- any of the values above without editing the file.
for k, v in pairs(rawget(_G, "MAPPER_CONFIG") or {}) do CONFIG[k] = v end

local AUDIO_EXTENSIONS = { [".wav"] = true, [".aif"] = true, [".aiff"] = true, [".flac"] = true }
local BLACK_PITCH_CLASSES = { [1] = true, [3] = true, [6] = true, [8] = true, [10] = true }
local NOTE_NAMES = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" }

local function note_name(note)
  -- Kontakt convention: MIDI 60 is C3.
  return NOTE_NAMES[(note % 12) + 1] .. tostring(math.floor(note / 12) - 2)
end

local function parse_bpm(file_name)
  local bpm = tonumber(file_name:match("(%d+)[%s_%-]*[bB][pP][mM]"))
  if bpm and bpm >= 40 and bpm <= 300 then return bpm end
  return nil
end

local function list_audio_files(dir)
  assert(fs.exists(dir), "Sample folder not found: " .. tostring(dir))
  local files = {}
  for _, p in fs.directory(dir) do
    if AUDIO_EXTENSIONS[fs.extension(p):lower()] then
      files[#files + 1] = p
    end
  end
  table.sort(files, function(a, b) return fs.filename(a):lower() < fs.filename(b):lower() end)
  return files
end

-- Returns { [midi_note] = absolute_path }, plus the highest key used.
local function build_assignments(files)
  local by_name, assignments, pinned = {}, {}, {}
  for _, p in ipairs(files) do by_name[fs.filename(p)] = p end

  for key, wanted in pairs(CONFIG.overrides) do
    local p = by_name[wanted]
    assert(p, ("override for key %d names a file that is not in the folder: %s"):format(key, wanted))
    assignments[key], pinned[p] = p, true
  end

  local key = CONFIG.first_key
  for _, p in ipairs(files) do
    if not pinned[p] then
      while key <= 127 and (assignments[key] or (CONFIG.white_keys_only and BLACK_PITCH_CLASSES[key % 12])) do
        key = key + 1
      end
      if key > 127 then
        print(("WARNING: ran out of keys, skipping %s and the files after it"):format(fs.filename(p)))
        break
      end
      assignments[key] = p
      key = key + 1
    end
  end
  return assignments
end

-- BEST EFFORT: loop the whole sample. The manual doesn't state whether loop_idx starts at 0 or 1,
-- so unless CONFIG.loop_index is set, both slots get the same infinite whole-sample loop. If slot 0
-- is the first loop, slot 1 is never reached (slot 0 never ends), so setting both is harmless.
local function apply_loop(inst, zone)
  local frames = kt.get_zone_sample_frames(inst, zone)
  if not frames then return false end
  local slots = CONFIG.loop_index and { CONFIG.loop_index } or { 0, 1 }
  local any = false
  for _, slot in ipairs(slots) do
    local ok = pcall(function()
      kt.set_sample_loop_mode(inst, zone, slot, CONFIG.loop_mode)
      kt.set_sample_loop_start(inst, zone, slot, 0)
      kt.set_sample_loop_length(inst, zone, slot, frames)
      kt.set_sample_loop_count(inst, zone, slot, 0)  -- 0 = loop indefinitely (verify in the Wave Editor)
    end)
    any = any or ok
  end
  return any
end

-- BEST EFFORT: Time Machine Pro with a fixed grid tempo lets Kontakt follow the host BPM.
local function apply_tempo_sync(inst, group, zone, bpm)
  return pcall(function()
    kt.set_group_playback_mode(inst, group, "time_machine_pro")
    kt.set_zone_grid(inst, zone, "fixed", bpm)
  end)
end

local function main()
  if CONFIG.reset_multi then kt.reset_multi() end

  local files = list_audio_files(CONFIG.sample_dir)
  assert(#files > 0, "No .wav/.aif/.aiff/.flac files found in " .. CONFIG.sample_dir)
  local assignments = build_assignments(files)

  local inst = kt.add_instrument()
  kt.set_instrument_name(inst, CONFIG.name)

  local keys = {}
  for key in pairs(assignments) do keys[#keys + 1] = key end
  table.sort(keys)

  print(("Mapping %d samples into '%s':"):format(#keys, CONFIG.name))
  for _, key in ipairs(keys) do
    local path = assignments[key]
    local file_name = fs.filename(path)
    local group = kt.add_group(inst)
    kt.set_group_name(inst, group, fs.stem(path))

    local zone = kt.add_zone(inst, group, path)
    kt.set_zone_geometry(inst, zone, { root_key = key, low_key = key, high_key = key })

    local notes = {}
    if CONFIG.loop and apply_loop(inst, zone) then notes[#notes + 1] = "loop" end
    local bpm = CONFIG.tempo_sync and parse_bpm(file_name)
    if bpm and apply_tempo_sync(inst, group, zone, bpm) then notes[#notes + 1] = bpm .. " BPM sync" end

    print(("  %-4s (%3d)  %s  %s"):format(note_name(key), key, file_name,
      #notes > 0 and ("[" .. table.concat(notes, ", ") .. "]") or ""))
  end

  if CONFIG.save_to then
    kt.save_instrument(inst, CONFIG.save_to, { mode = "patch", absolute_paths = true })
    print("Saved " .. CONFIG.save_to)
  end
  print(("Done: %d groups, %d zones."):format(kt.get_num_groups(inst), kt.get_num_zones(inst)))
end

local ok, err = pcall(main)
if not ok then print("map_folder_to_keys failed: " .. tostring(err)) end
