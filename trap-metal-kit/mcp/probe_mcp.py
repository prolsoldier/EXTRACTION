#!/usr/bin/env python3
"""Find out what a local MCP-over-HTTP server (e.g. Kontakt 8.13+) actually speaks.

Kontakt's MCP server is switched on in Options > Developer > "Enable MCP server" and listens
on the port shown there (3006 by default). The public release notes don't give the URL path or
the tool names, so this script asks the server: it tries common paths, sends an MCP `initialize`
request, then `tools/list`, and prints the `claude mcp add` command that will work.

    python3 probe_mcp.py                # 127.0.0.1:3006
    python3 probe_mcp.py --port 3010

Standard library only. It only talks to the host/port you give it (127.0.0.1 by default).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

CANDIDATE_PATHS = ("/mcp", "/", "/sse")
PROTOCOL_VERSION = "2025-06-18"


def post(url, payload, session_id=None, timeout=5.0):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
        return response.status, response.headers, parse_body(response.headers.get("Content-Type", ""), body)


def parse_body(content_type, body):
    """Return the JSON-RPC message from a plain JSON or a text/event-stream reply."""
    if not body.strip():
        return None
    if "text/event-stream" in content_type:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def initialize(url):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "probe_mcp", "version": "1.0"}},
    }
    return post(url, payload)


def list_tools(url, session_id):
    post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    _, _, message = post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id)
    return (message or {}).get("result", {}).get("tools", [])


def probe(host, port):
    base = f"http://{host}:{port}"
    for path in CANDIDATE_PATHS:
        url = base + path
        try:
            status, headers, message = initialize(url)
        except urllib.error.HTTPError as err:
            print(f"{url}: HTTP {err.code}")
            continue
        except (urllib.error.URLError, OSError) as err:
            print(f"{url}: {getattr(err, 'reason', err)}")
            if path == CANDIDATE_PATHS[0] and "refused" in str(getattr(err, "reason", err)).lower():
                print("Nothing is listening. Is 'Enable MCP server' ticked (and Kontakt restarted/Restart pressed)?")
                return None
            continue
        if not message or "result" not in message:
            print(f"{url}: HTTP {status} but no MCP initialize result")
            continue
        info = message["result"].get("serverInfo", {})
        print(f"{url}: MCP server {info.get('name', '?')} {info.get('version', '')} "
              f"(protocol {message['result'].get('protocolVersion', '?')})")
        tools = []
        try:
            tools = list_tools(url, headers.get("Mcp-Session-Id"))
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"  tools/list failed: {err}")
        for tool in tools:
            print(f"  - {tool.get('name')}: {(tool.get('description') or '').strip().splitlines()[0] if tool.get('description') else ''}")
        return url
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3006)
    args = parser.parse_args(argv)

    url = probe(args.host, args.port)
    if not url:
        print("\nNo MCP endpoint answered.")
        return 1
    print(f"\nAdd it to Claude Code with:\n  claude mcp add --transport http kontakt {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
