"""Provider tool loops, exercised offline with stub SDK clients (no network, no API key)."""

from types import SimpleNamespace as NS

import pytest

from deepterminal_api.research.providers.anthropic_provider import AnthropicProvider
from deepterminal_api.research.providers.base import ToolSpec
from deepterminal_api.research.providers.openai_provider import OpenAIProvider

pytest.importorskip("anthropic")
pytest.importorskip("openai")


class StubAnthropic:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})   # snapshot: the provider keeps appending
        return self.responses.pop(0)


def a_resp(blocks, stop, i=100, o=20):
    return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=i, output_tokens=o))


def tool_use(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


TOOLS = [ToolSpec("lookup", "Look up a value", {"type": "object", "properties": {"k": {"type": "string"}},
                                                "required": ["k"], "additionalProperties": False},
                  lambda a: {"value": {"x": 1}[a["k"]]})]


def test_anthropic_tool_loop_runs_tools_and_returns_final_text():
    p = AnthropicProvider(model="claude-opus-5-5")
    p._client = StubAnthropic([
        a_resp([text("checking"), tool_use("t1", "lookup", {"k": "x"}), tool_use("t2", "lookup", {"k": "missing"})], "tool_use"),
        a_resp([text("x is 1 [E1]")], "end_turn"),
    ])
    r = p.run("sys", "question", TOOLS, max_tool_calls=5, max_input_tokens=10_000, max_output_tokens=500)
    assert r.stopped == "end" and r.text == "x is 1 [E1]"
    assert r.usage.calls == 2 and r.usage.input_tokens == 200 and r.usage.tool_calls == 2
    first = p._client.calls[0]
    assert first["model"] == "claude-opus-5-5" and first["max_tokens"] == 500 and first["system"] == "sys"
    assert first["tools"][0]["strict"] is True
    results = p._client.calls[1]["messages"][-1]["content"]
    assert results[0] == {"type": "tool_result", "tool_use_id": "t1", "content": '{"value": 1}', "is_error": False}
    assert results[1]["is_error"] is True and "tool error" in results[1]["content"]   # tool failure goes back to the model


def test_anthropic_tool_call_budget_and_input_budget():
    p = AnthropicProvider()
    p._client = StubAnthropic([
        a_resp([tool_use("t1", "lookup", {"k": "x"}), tool_use("t2", "lookup", {"k": "x"})], "tool_use", i=600),
        a_resp([tool_use("t3", "lookup", {"k": "x"})], "tool_use", i=600),
    ])
    r = p.run("s", "u", TOOLS, max_tool_calls=1, max_input_tokens=1000, max_output_tokens=100)
    over = p._client.calls[1]["messages"][-1]["content"][1]
    assert over["is_error"] and "budget exhausted" in over["content"]
    assert r.stopped == "budget" and r.usage.input_tokens == 1200 and len(p._client.calls) == 2


def test_anthropic_refusal_is_reported():
    p = AnthropicProvider()
    p._client = StubAnthropic([a_resp([], "refusal")])
    assert p.run("s", "u", [], 3, 1000, 100).stopped == "refusal"


class StubOpenAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = NS(completions=self)

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})   # snapshot: the provider keeps appending
        return self.responses.pop(0)


def o_msg(content=None, tool_calls=None):
    m = NS(content=content, tool_calls=tool_calls)
    m.model_dump = lambda exclude_none=True: {"role": "assistant", "content": content}
    return NS(choices=[NS(message=m)], usage=NS(prompt_tokens=50, completion_tokens=5))


def test_openai_tool_loop():
    p = OpenAIProvider(model="gpt-5")
    call = NS(id="c1", function=NS(name="lookup", arguments='{"k": "x"}'))
    p._client = StubOpenAI([o_msg(tool_calls=[call]), o_msg(content="done")])
    r = p.run("s", "u", TOOLS, 3, 10_000, 200)
    assert r.text == "done" and r.usage.tool_calls == 1 and r.usage.input_tokens == 100
    assert p._client.calls[1]["messages"][-1] == {"role": "tool", "tool_call_id": "c1", "content": '{"value": 1}'}
