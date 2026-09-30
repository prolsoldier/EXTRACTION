# MCP servers that let Claude drive a DAW

I found these in search results and read only their listing excerpts. **I have not audited or run any of them.**
Read the code before you run one: each is a local program that controls your DAW and often listens on a local port.

## FL Studio
| Repo | Notes from its listing |
|---|---|
| [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp) | Config shown: `uv run --directory /path/to/fl-studio-mcp fl-studio-mcp` |
| [rosasynthesiz/flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp) | Says it drives mixer, plugins, piano roll and routing; one directory lists 67 tools; a TCP daemon or direct MIDI transport (`FLSTUDIO_MCP_TRANSPORT`) |
| [szichedelic/fl-studio-mcp](https://github.com/szichedelic/fl-studio-mcp) | Transport control (play/stop/record, playback state) and more |
| [ohhalim/flstudio-mcp](https://github.com/ohhalim/flstudio-mcp) | Credits the FL Studio API stubs and Ableton MCP as inspiration |

They work through FL Studio's Python MIDI-scripting layer, which is the same one `fl-studio/device_TrapDJ.py` uses.

## Ableton Live
| Repo | Notes |
|---|---|
| [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) | Python server plus a Remote Script listening on `localhost:9877` (JSON over TCP); one review notes recurring install issues and a single-client listener |
| [uisato/ableton-mcp-extended](https://github.com/uisato/ableton-mcp-extended) | Extended fork |
| [Simon-Kansara/ableton-live-mcp-server](https://github.com/Simon-Kansara/ableton-live-mcp-server) | Controls Live over OSC |

## REAPER
| Repo | Notes |
|---|---|
| [shiehn/total-reaper-mcp](https://github.com/shiehn/total-reaper-mcp) | Claims full ReaScript coverage with selectable tool profiles. Listing shows `claude mcp add reaper-mcp -- /path/to/.venv/bin/python -m server.app` (Windows needs `REAPER_MCP_BRIDGE_DIR`) |
| [xdarkzx/reaper-mcp](https://mcpservers.org/servers/xdarkzx/reaper-mcp) | Uses a Lua script in REAPER and JSON files for IPC |
| "Reaper Dev MCP" ([forum thread](https://forums.cockos.com/showthread.php?t=305990)) | Static reference docs for ReaScript/JSFX development, aimed at LLMs |

## Safe habits
- Pin to a specific commit and read what the tool handlers do (file writes? shell commands? network?).
- Look at the tool list a server advertises before you let an agent use it without asking.
- Keep them on `127.0.0.1`; don't expose their ports.
- Save your project before an agent edits it.
