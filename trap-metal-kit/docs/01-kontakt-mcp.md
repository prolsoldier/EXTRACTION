# Kontakt 8 MCP server: what it is and how to connect

## What's confirmed
- Kontakt **8.13.0 (2026-09-03)** added "AI tooling support via an MCP Server for debugging script errors" for
  Instrument Builders ([Toolfarm release notes](https://www.toolfarm.com/news/kontakt-8-13/),
  [Rekkerd](https://rekkerd.org/native-instruments-updates-kontakt-to-v8-13-0/)).
- Your screenshot (Options ▸ Developer) shows an **Enable MCP server** checkbox, **Port 3006**, a
  "Running on port 3006" status and a **Restart** button.

So it is a local endpoint for an AI assistant to help *build and debug Kontakt scripts*. It is **not** a host for audio
servers or sound generators, and you don't plug other MCP servers into it.

## What's *not* confirmed
The notes you pasted say it can "retrieve Komplete Script log messages" and "reload instruments". The public release
notes only say "debugging script errors". I could not find the URL path or tool list published anywhere, so don't assume
them: **ask the server** (below).

## Terminology (the pasted notes blur these)
| Name | What it is |
|---|---|
| **Kontakt Lua API** | Lua scripts that build/edit instruments from code. Run with `File ▸ Run Lua script…` (F11) after ticking **Enable developer features**. [Reference](https://docs.native-instruments.com/ni-tech-manuals/kontakt-api-reference-manual/en/welcome-to-the-kontakt-lua-api-reference-manual). `kontakt/map_folder_to_keys.lua` is one of these. |
| **Komplete UI / Komplete Script** | A separate language (`.kscript` files) for drawing instrument GUIs, edited with NI's VS Code extension. It is not Lua. |
| **KSP** | Kontakt's older real-time script language for MIDI/sample behaviour inside an instrument. |
| **MCP server (8.13+)** | The AI-debugging endpoint on port 3006. |

## Connect Claude Code to it
Claude Code has to run **on the same computer as Kontakt** (your Windows PC). A cloud session like the one that wrote
this kit cannot reach `localhost:3006` on your machine.

1. Kontakt ▸ Options ▸ Developer: tick **Enable MCP server**, press **Restart**, note the port.
2. In a terminal on that PC, from this repo:
   ```
   python mcp/probe_mcp.py            # add --port N if you changed it
   ```
   It tries `/mcp`, `/` and `/sse`, sends an MCP `initialize`, lists the tools, and prints the exact command to use.
3. Register it (use the URL the probe printed):
   ```
   claude mcp add --transport http kontakt http://127.0.0.1:3006/mcp
   ```
   Or copy `mcp/kontakt-mcp.example.json` to `.mcp.json` in your project and fix the path.
4. In Claude Code run `/mcp` to confirm it connected, then ask it to debug your script.

If the probe prints "Nothing is listening", the server isn't running (check the checkbox and Restart).

## Seeing script output while you develop
NI's manual recommends launching Kontakt from a terminal or editor so Lua `print` output and script errors show up in it
(it gives a VS Code `tasks.json` and a Sublime build file). Run `Kontakt 8.exe path\to\script.lua` and the script executes
at start-up with output in that terminal.

## Security
- Kontakt's own warning: with developer features on, Lua scripts can **modify and execute files on your system**
  (NI's manual notes that Lua's operating-system library is available and advises running scripts from trusted parties
  only). Only run scripts you have read.
- The MCP server is a door into that environment for whatever assistant you connect. Look at the tool list the probe prints
  before you let an agent call anything without asking.
- Confirm the port is local-only: `netstat -ano | findstr :3006`. You want `127.0.0.1:3006`; if it shows `0.0.0.0:3006`,
  block it in Windows Firewall.
