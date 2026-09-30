-- key_slots.lua  (ReaScript, Lua)
--
-- Loads every audio file in a folder onto its own key: one ReaSamplOmatic5000 per file on the
-- selected track, each restricted to a single MIDI note. Arm the track, play the keys, and blend
-- the pieces live.
--
-- Run: select a track > Actions > Show action list > New action > Load ReaScript... > pick this file.
--
-- ReaSamplOmatic5000 does not time-stretch. Use loops that already share a BPM (or pre-stretch them),
-- or use Reaper's media-item workflow if you need warping.
--
-- Parameters are looked up by name (TrackFX_GetParamName) instead of by hard-coded index, and
-- anything that cannot be found is skipped with a message in the ReaScript console. This has been
-- tested against a mock of the ReaScript API, not inside Reaper.

local FIRST_NOTE = 36                      -- MIDI note of the first file
local EXTENSIONS = { wav = true, aif = true, aiff = true, flac = true, mp3 = true, ogg = true }
local LOOP_WHILE_HELD = true               -- set RS5k's loop switch if this build exposes one

local function log(msg) reaper.ShowConsoleMsg(msg .. "\n") end

local function find_param(track, fx, wanted)
  wanted = wanted:lower()
  for i = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
    local _, name = reaper.TrackFX_GetParamName(track, fx, i, "")
    if name:lower():find(wanted, 1, true) then return i end
  end
  return nil
end

local function set_param_by_name(track, fx, wanted, normalized)
  local idx = find_param(track, fx, wanted)
  if not idx then
    log(("  (no parameter named like '%s' - skipped)"):format(wanted))
    return false
  end
  return reaper.TrackFX_SetParamNormalized(track, fx, idx, normalized)
end

local function list_audio_files(dir)
  local files, i = {}, 0
  while true do
    local name = reaper.EnumerateFiles(dir, i)
    if not name then break end
    local ext = name:match("%.([^.]+)$")
    if ext and EXTENSIONS[ext:lower()] then files[#files + 1] = name end
    i = i + 1
  end
  table.sort(files, function(a, b) return a:lower() < b:lower() end)
  return files
end

local function main()
  local track = reaper.GetSelectedTrack(0, 0)
  if not track then log("Select a track first."); return end

  local ok, dir = reaper.GetUserInputs("Sample folder", 1, "Folder path:,extrawidth=380", "")
  if not ok or dir == "" then return end
  dir = dir:gsub("[/\\]+$", "")

  local files = list_audio_files(dir)
  if #files == 0 then log("No audio files found in " .. dir); return end
  if FIRST_NOTE + #files - 1 > 127 then
    log(("Only the first %d files fit on the keyboard."):format(128 - FIRST_NOTE))
    for i = #files, 128 - FIRST_NOTE + 1, -1 do files[i] = nil end
  end

  reaper.Undo_BeginBlock()
  for i, name in ipairs(files) do
    local note = FIRST_NOTE + i - 1
    local fx = reaper.TrackFX_AddByName(track, "ReaSamplOmatic5000", false, -1)
    if fx < 0 then
      log("ReaSamplOmatic5000 not found - is it installed?")
      break
    end
    reaper.TrackFX_SetNamedConfigParm(track, fx, "FILE0", dir .. "/" .. name)
    reaper.TrackFX_SetNamedConfigParm(track, fx, "DONE", "")
    reaper.TrackFX_SetNamedConfigParm(track, fx, "renamed_name", ("%d  %s"):format(note, name))

    set_param_by_name(track, fx, "note range start", note / 127)
    set_param_by_name(track, fx, "note range end", note / 127)
    if LOOP_WHILE_HELD then set_param_by_name(track, fx, "loop", 1) end
    log(("note %3d  %s"):format(note, name))
  end
  reaper.Undo_EndBlock("Map folder to keys", -1)
end

main()
