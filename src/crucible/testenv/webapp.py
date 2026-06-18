"""A vulnerable chatbot web app (stdlib only).

Serves the same AcmeBot vulnerability logic as `SampleTarget`, but as a real
HTTP service with an HTML chat widget. The widget renders the bot's reply AND any
tool calls into the DOM, so a browser-driven adapter can read *what the UI actually
shows* (the "observe the side effect" oracle) rather than a trusted JSON field.

Endpoints:
  GET  /?id=<instance>        -> chat UI for an agent instance
  POST /chat   {message,id}   -> {text, tool_calls}
  GET  /admin/config?id=      -> grey-box config of an instance
  POST /admin/clone {base,patch} -> {id}   (creates a patched instance; used by fixes)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..sample_target import SampleTarget

_INSTANCES: dict[str, SampleTarget] = {"default": SampleTarget()}
_LOCK = threading.Lock()
_COUNTER = {"n": 0}

_PAGE = """<!doctype html><html><head><meta charset=utf-8><title>AcmeBot</title>
<style>body{font-family:sans-serif;max-width:640px;margin:2rem auto}
#log{border:1px solid #ccc;min-height:200px;padding:8px}
.turn{margin:6px 0;padding:6px;border-bottom:1px solid #eee}
.bot-msg{white-space:pre-wrap}.tool-call{color:#b00;font-family:monospace;font-size:.9em}</style>
</head><body><h2>AcmeBot support</h2>
<div id=log></div>
<input id=msg style="width:80%"><button id=send>Send</button>
<script>
const ID=%ID%;
const log=document.getElementById('log');
document.getElementById('send').onclick=async()=>{
  const message=document.getElementById('msg').value;
  const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message,id:ID})});
  const d=await r.json();
  const turn=document.createElement('div');turn.className='turn';
  const bm=document.createElement('div');bm.className='bot-msg';bm.textContent=d.text;turn.appendChild(bm);
  (d.tool_calls||[]).forEach(c=>{const t=document.createElement('div');t.className='tool-call';
    t.dataset.tool=c.name;t.dataset.amount=(c.args&&c.args.amount)||'';
    t.textContent='executed '+c.name+'('+JSON.stringify(c.args)+')';turn.appendChild(t);});
  log.appendChild(turn);
};
</script></body></html>"""


def _clone_instance(base: str, patch: dict) -> str:
    with _LOCK:
        src = _INSTANCES.get(base, _INSTANCES["default"])
        _COUNTER["n"] += 1
        new_id = f"inst{_COUNTER['n']}"
        _INSTANCES[new_id] = src.clone_with_config(patch)
        return new_id


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        return

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        inst = qs.get("id", ["default"])[0]
        if parsed.path == "/admin/config":
            target = _INSTANCES.get(inst)
            if target is None:
                return self._send_json({"error": "no such instance"}, 404)
            return self._send_json(target.get_config())
        # default: serve the chat UI
        html = _PAGE.replace("%ID%", json.dumps(inst)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/chat":
            inst = body.get("id", "default")
            target = _INSTANCES.get(inst)
            if target is None:
                return self._send_json({"error": "no such instance"}, 404)
            resp = target.send(body.get("message", ""))
            return self._send_json({
                "text": resp.text,
                "tool_calls": [{"name": c.name, "args": c.args} for c in resp.tool_calls],
            })
        if self.path == "/admin/clone":
            new_id = _clone_instance(body.get("base", "default"), body.get("patch", {}))
            return self._send_json({"id": new_id})
        self._send_json({"error": "not found"}, 404)


def serve_background(host: str = "127.0.0.1", port: int = 0):
    """Start the web app in a daemon thread. Returns (server, base_url)."""
    # fresh instance table per launch keeps runs isolated
    _INSTANCES.clear()
    _INSTANCES["default"] = SampleTarget()
    _COUNTER["n"] = 0
    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://{host}:{actual_port}"
