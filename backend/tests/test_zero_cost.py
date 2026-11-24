"""Zero-cost guarantees: no paid request without explicit opt-in, local AI by default."""

import json

import httpx
import pytest

from deepterminal import costpolicy
from deepterminal.data.http import CachedFetcher, CostPolicyBlocked
from deepterminal_api.config import get_settings
from deepterminal_api.research.providers import OllamaProvider, get_provider
from deepterminal_api.research.providers.base import ToolSpec, guarded_http_client


@pytest.fixture
def settings(monkeypatch):
    def apply(**kw):
        for k, v in kw.items():
            monkeypatch.setenv(f"DEEPTERMINAL_{k.upper()}", str(v))
        get_settings.cache_clear()
        return get_settings()
    yield apply
    get_settings.cache_clear()


def test_hosts_are_classified():
    assert costpolicy.classify("https://data.sec.gov/submissions/CIK1.json") == "free"
    assert costpolicy.classify("https://stooq.com/q/d/l/?s=nvda.us&i=d") == "free"
    assert costpolicy.classify("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10") == "free"
    assert costpolicy.classify("http://127.0.0.1:11434/api/chat") == "local"
    assert costpolicy.classify("https://api.anthropic.com/v1/messages") == "paid"
    assert costpolicy.classify("https://api.openai.com/v1/chat/completions") == "paid"
    assert costpolicy.classify("https://example-market-data.com/quote") == "unknown"


def test_paid_and_unknown_hosts_blocked_by_default(monkeypatch):
    monkeypatch.delenv("DEEPTERMINAL_ALLOW_PAID_APIS", raising=False)
    with pytest.raises(costpolicy.PaidRequestBlocked):
        costpolicy.check_url("https://api.anthropic.com/v1/messages")
    with pytest.raises(costpolicy.UnapprovedHostBlocked):
        costpolicy.check_url("https://example-market-data.com/quote")
    monkeypatch.setenv("DEEPTERMINAL_ALLOW_PAID_APIS", "true")
    costpolicy.check_url("https://api.anthropic.com/v1/messages")          # explicit opt-in
    with pytest.raises(costpolicy.UnapprovedHostBlocked):
        costpolicy.check_url("https://example-market-data.com/quote")      # still not classified


def test_fetcher_refuses_paid_host_before_any_network(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPTERMINAL_ALLOW_PAID_APIS", raising=False)
    calls = []
    f = CachedFetcher(tmp_path, "test", opener=lambda *a, **k: calls.append(a) or None, sleep=lambda s: None)
    with pytest.raises(CostPolicyBlocked):
        f.get("https://api.openai.com/v1/models", "x.json")
    assert calls == []


def test_sdk_http_client_is_guarded(monkeypatch):
    monkeypatch.delenv("DEEPTERMINAL_ALLOW_PAID_APIS", raising=False)
    client = guarded_http_client()
    with pytest.raises(costpolicy.PaidRequestBlocked):
        client.get("https://api.anthropic.com/v1/models")


def test_default_provider_is_free_and_never_falls_back_to_paid(settings, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    s = settings(ollama_url="http://127.0.0.1:9")            # nothing listening: Ollama unavailable
    assert s.llm_provider == "auto" and s.allow_paid_apis is False
    assert get_provider() is None                              # rules, not a paid provider
    settings(llm_provider="anthropic")                         # selected, but paid APIs not enabled
    assert get_provider() is None
    settings(llm_provider="anthropic", allow_paid_apis="true")
    assert get_provider().name == "anthropic"                  # only with both explicit settings


def ollama_stub(responses: list[dict], seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b-instruct"}]})
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))
    return httpx.Client(base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(handler))


def test_ollama_tool_loop_and_usage():
    seen: list[dict] = []
    replies = [
        {"message": {"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "lookup", "arguments": {"k": "x"}}}]},
         "prompt_eval_count": 120, "eval_count": 15},
        {"message": {"role": "assistant", "content": "x is 1 [E1]"}, "prompt_eval_count": 150, "eval_count": 9},
    ]
    p = OllamaProvider("qwen2.5:7b-instruct", client=ollama_stub(replies, seen))
    assert p.available() and p.paid is False
    tool = ToolSpec("lookup", "Look up", {"type": "object", "properties": {"k": {"type": "string"}}, "required": ["k"]},
                    lambda a: {"value": {"x": 1}[a["k"]]})
    r = p.run("sys", "q", [tool], max_tool_calls=4, max_input_tokens=10_000, max_output_tokens=300)
    assert r.stopped == "end" and r.text == "x is 1 [E1]"
    assert r.usage.input_tokens == 270 and r.usage.output_tokens == 24 and r.usage.tool_calls == 1
    assert seen[0]["model"] == "qwen2.5:7b-instruct" and seen[0]["tools"][0]["function"]["name"] == "lookup"
    assert seen[0]["options"]["num_predict"] == 300 and seen[0]["stream"] is False
    assert seen[1]["messages"][-1] == {"role": "tool", "tool_name": "lookup", "content": '{"value": 1}'}


def test_ollama_reports_missing_model():
    p = OllamaProvider("llama3.1:8b", client=ollama_stub([], []))
    ok, detail = p.status()
    assert not ok and "ollama pull llama3.1:8b" in detail
