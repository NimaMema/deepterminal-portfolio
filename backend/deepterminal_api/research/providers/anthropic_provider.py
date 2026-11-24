"""Anthropic Claude provider (official SDK), manual tool-use loop with hard budgets."""

from __future__ import annotations

import json
import os
from typing import Callable

from .base import AgentResult, BudgetExceeded, ToolSpec, Usage, guarded_http_client, tool_result_text

DEFAULT_BASE_URL = "https://api.anthropic.com"


class AnthropicProvider:
    paid = True
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium"):
        self.model = model
        self.effort = effort
        self._client = None

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def client(self):
        if self._client is None:
            import anthropic
            # Explicit base URL: never inherit a base URL configured for another tool in the environment.
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                               base_url=os.environ.get("DEEPTERMINAL_ANTHROPIC_BASE_URL", DEFAULT_BASE_URL),
                                               max_retries=3, http_client=guarded_http_client())
        return self._client

    def run(self, system: str, user: str, tools: list[ToolSpec], max_tool_calls: int, max_input_tokens: int,
            max_output_tokens: int, on_event: Callable[[str], None] | None = None) -> AgentResult:
        import anthropic
        usage = Usage()
        transcript: list[dict] = []
        tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True}
                     for t in tools]
        by_name = {t.name: t for t in tools}
        messages: list[dict] = [{"role": "user", "content": user}]
        while True:
            if usage.input_tokens > max_input_tokens:
                return AgentResult(_last_text(messages), usage, transcript, "budget")
            try:
                kwargs = dict(model=self.model, max_tokens=max_output_tokens, system=system, messages=messages,
                              output_config={"effort": self.effort})
                if tool_defs:
                    kwargs["tools"] = tool_defs
                resp = self.client.messages.create(**kwargs)
            except anthropic.RateLimitError as e:
                return AgentResult(f"Rate limited by provider: {e}", usage, transcript, "error")
            except anthropic.APIStatusError as e:
                return AgentResult(f"Provider error {e.status_code}: {e.message}", usage, transcript, "error")
            except anthropic.APIConnectionError as e:
                return AgentResult(f"Provider unreachable: {e}", usage, transcript, "error")
            usage.add(resp.usage.input_tokens, resp.usage.output_tokens)
            messages.append({"role": "assistant", "content": resp.content})   # keep thinking blocks intact
            if resp.stop_reason == "refusal":
                return AgentResult("The model declined this request.", usage, transcript, "refusal")
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return AgentResult(text, usage, transcript, "end")
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                usage.tool_calls += 1
                if usage.tool_calls > max_tool_calls:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": "Tool-call budget exhausted; answer with the evidence you have."})
                    continue
                tool = by_name.get(block.name)
                if on_event:
                    on_event(f"tool: {block.name}({json.dumps(block.input)[:160]})")
                try:
                    out = tool.fn(dict(block.input)) if tool else {"error": f"unknown tool {block.name}"}
                    content, err = tool_result_text(out), False
                except BudgetExceeded:
                    raise
                except Exception as e:  # tool errors go back to the model
                    content, err = f"tool error: {e}", True
                transcript.append({"tool": block.name, "input": block.input, "error": err, "chars": len(content)})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": err})
            messages.append({"role": "user", "content": results})


def _last_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m["role"] == "assistant":
            c = m["content"]
            return "".join(getattr(b, "text", "") for b in c) if not isinstance(c, str) else c
    return ""
