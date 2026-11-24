"""End-to-end local-AI path through the real API, against a scripted Ollama-compatible server.

The stand-in speaks Ollama's HTTP protocol (/api/tags, /api/chat with tool calls). It is not a
language model: it calls the search tool, then answers citing one evidence id it received and
one fabricated id. This checks the plumbing a real local model relies on — tool execution,
evidence storage, citation validation, zero paid usage — without downloading model weights.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from deepterminal_api.config import get_settings
from deepterminal_api.research import providers


class ScriptedOllama(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:7b-instruct"}]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ScriptedOllama.calls.append(req)
        tool_msgs = [m for m in req["messages"] if m["role"] == "tool"]
        if not req.get("tools"):            # synthesis: evidence is in the prompt, no tools offered
            ids = re.findall(r"\[(E\d+)\]", req["messages"][-1]["content"])
            self._send({"message": {"role": "assistant", "content": f"(1) The business depends on a sole-source "
                                    f"foundry [{ids[0]}]. A fair value range is $300 to $450 per share [{ids[0]}]. "
                                    f"Unsupported claim [E999999]."},
                        "prompt_eval_count": 1500, "eval_count": 60})
            return
        if not tool_msgs:
            self._send({"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "search_filings", "arguments": {"query": "foundry Taiwan supply", "forms": None}}}]},
                "prompt_eval_count": 400, "eval_count": 20})
            return
        ids = re.findall(r'"evidence_id": "(E\d+)"', tool_msgs[-1]["content"])
        self._send({"message": {"role": "assistant",
                                "content": f"The company relies on a single foundry in Taiwan [{ids[0]}]. "
                                           "It also claims something unsupported [E999999]."},
                    "prompt_eval_count": 900, "eval_count": 40})


@pytest.fixture
def local_ollama(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), ScriptedOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("DEEPTERMINAL_OLLAMA_URL", f"http://127.0.0.1:{srv.server_port}")
    get_settings.cache_clear()
    providers._OLLAMA = None
    ScriptedOllama.calls = []
    yield srv
    srv.shutdown()
    get_settings.cache_clear()
    providers._OLLAMA = None


def test_chat_with_local_model_validates_citations_and_costs_nothing(client, dqd, local_ollama):
    client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation", "modules": ["supply_chain"]})
    st = client.get("/api/status").json()
    assert next(p for p in st["providers"] if p["provider"] == "ollama")["active"] is True
    s = client.post("/api/chat/sessions", json={"company_id": dqd["id"]}).json()
    m = client.post(f"/api/chat/sessions/{s['id']}/messages",
                    json={"content": "What does the company say about its foundry?"}).json()
    assert m["generated_by"] == "ollama:qwen2.5:7b-instruct"
    assert "[E999999]" not in m["content"] and "removed" in m["content"]       # fabricated citation stripped
    cited = {int(x) for x in re.findall(r"\[E(\d+)\]", m["content"])}
    assert cited and cited <= {c["id"] for c in m["citations"]}
    assert all(c["verification_status"] == "verified" for c in m["citations"])
    assert "foundry" in m["citations"][0]["excerpt"].lower()
    req = next(c for c in ScriptedOllama.calls if c.get("tools"))                  # the chat call
    assert req["model"] == "qwen2.5:7b-instruct" and {t["function"]["name"] for t in req["tools"]} >= {"search_filings"}
    assert "untrusted" in req["messages"][0]["content"].lower()                 # injection guard rules sent
    assert client.get("/api/status").json()["llm_tokens_today"] == 0            # local tokens are not paid usage


def test_investigation_synthesis_runs_on_local_model(client, dqd, local_ollama):
    job = client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation",
                                          "modules": ["supply_chain"]}).json()
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["status"] == "succeeded" and j["result"]["synthesis"]["status"] != "skipped"
    fs = client.get(f"/api/jobs/{job['id']}/findings").json()
    syn = next(f for f in fs if f["module"] == "synthesis")
    assert syn["generated_by"].startswith("ollama") and "[E999999]" not in syn["summary"]
    assert "$300" not in syn["summary"] and "figure not found in the evidence" in syn["summary"]   # invented range removed
