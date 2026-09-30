"""Exercises mcp/probe_mcp.py against a real local HTTP server that speaks a minimal MCP."""
import contextlib
import http.server
import importlib.util
import io
import json
import pathlib
import socket
import threading
import unittest

SPEC = importlib.util.spec_from_file_location("probe_mcp", pathlib.Path(__file__).parent.parent / "mcp" / "probe_mcp.py")
probe_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_mcp)

TOOLS = [{"name": "get_log", "description": "Return script log lines\nsecond line"}, {"name": "reload_instrument"}]


def make_handler(path, sse):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != path:
                self.send_response(404)
                self.end_headers()
                return
            message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method = message.get("method")
            if method == "notifications/initialized":
                self.send_response(202)
                self.end_headers()
                return
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake-kontakt", "version": "8.13.0"}}
            elif method == "tools/list":
                assert self.headers.get("Mcp-Session-Id") == "abc123", "session id was not echoed back"
                result = {"tools": TOOLS}
            else:
                result = {}
            body = json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result})
            if sse:
                body, content_type = f"event: message\ndata: {body}\n\n", "text/event-stream"
            else:
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Mcp-Session-Id", "abc123")
            self.end_headers()
            self.wfile.write(body.encode())

    return Handler


@contextlib.contextmanager
def serve(path="/mcp", sse=False):
    server = http.server.HTTPServer(("127.0.0.1", 0), make_handler(path, sse))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def run_main(port):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = probe_mcp.main(["--port", str(port)])
    return code, out.getvalue()


class ProbeTest(unittest.TestCase):
    def test_finds_server_lists_tools_and_prints_claude_command(self):
        with serve() as port:
            code, out = run_main(port)
        self.assertEqual(code, 0)
        self.assertIn("fake-kontakt 8.13.0", out)
        self.assertIn("- get_log: Return script log lines", out)
        self.assertIn("- reload_instrument", out)
        self.assertIn(f"claude mcp add --transport http kontakt http://127.0.0.1:{port}/mcp", out)

    def test_handles_event_stream_replies(self):
        with serve(sse=True) as port:
            code, out = run_main(port)
        self.assertEqual(code, 0)
        self.assertIn("get_log", out)

    def test_falls_back_to_other_paths(self):
        with serve(path="/sse") as port:
            code, out = run_main(port)
        self.assertEqual(code, 0)
        self.assertIn(f"http://127.0.0.1:{port}/sse", out)
        self.assertIn("HTTP 404", out)

    def test_reports_when_nothing_is_listening(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code, out = run_main(port)
        self.assertEqual(code, 1)
        self.assertIn("Nothing is listening", out)

    def test_parse_body_variants(self):
        self.assertEqual(probe_mcp.parse_body("application/json", '{"a": 1}'), {"a": 1})
        self.assertEqual(probe_mcp.parse_body("text/event-stream", 'event: x\ndata: {"a": 2}\n\n'), {"a": 2})
        self.assertIsNone(probe_mcp.parse_body("application/json", "not json"))
        self.assertIsNone(probe_mcp.parse_body("application/json", ""))


if __name__ == "__main__":
    unittest.main()
