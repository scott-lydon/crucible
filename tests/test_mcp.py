import json

from crucible.mcp_server import handle


def test_initialize_and_tools_list():
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "crucible"
    tools = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert tools[0]["name"] == "crucible_run"


def test_tools_call_runs_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # reports + catalog land in tmp
    resp = handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "crucible_run", "arguments": {"operator_owned": True, "mode": "auto"}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["findings"] > 0
    assert payload["held_out_catch_rate"] >= 0.99
