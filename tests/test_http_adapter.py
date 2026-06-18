import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from crucible.adapter import HTTPAdapter, _dig


def test_dig_navigates_dot_and_index_paths():
    obj = {"choices": [{"message": {"content": "hi"}}]}
    assert _dig(obj, "choices.0.message.content") == "hi"
    assert _dig(obj, "choices.9.message") is None
    assert _dig(obj, "nope") is None


@pytest.fixture
def echo_server():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            out = {"choices": [{"message": {"content": "you said: " + body.get("q", "")}}],
                   "calls": [{"name": "refund", "args": {"amount": 50}}]}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_http_adapter_with_custom_request_and_response_paths(echo_server):
    a = HTTPAdapter(echo_server, message_field="q",
                    response_path="choices.0.message.content", tool_calls_path="calls")
    r = a.send("hello")
    assert r.text == "you said: hello"
    assert r.tool_calls and r.tool_calls[0].name == "refund"
    assert r.tool_calls[0].args["amount"] == 50
