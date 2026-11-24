"""OpenAI provider (official SDK, Chat Completions function calling) behind the same interface."""

from __future__ import annotations

import json
import os
from typing import Callable

from .base import AgentResult, BudgetExceeded, ToolSpec, Usage, guarded_http_client, tool_result_text


class OpenAIProvider:
    paid = True
    name = "openai"

    def __init__(self, model: str):
        self.model = model
        self._client = None

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=3,
                                         http_client=guarded_http_client())
        return self._client

    def run(self, system: str, user: str, tools: list[ToolSpec], max_tool_calls: int, max_input_tokens: int,
            max_output_tokens: int, on_event: Callable[[str], None] | None = None) -> AgentResult:
        import openai
        usage = Usage()
        transcript: list[dict] = []
        defs = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                  "parameters": t.parameters}} for t in tools]
        by_name = {t.name: t for t in tools}
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        while True:
            if usage.input_tokens > max_input_tokens:
                return AgentResult(messages[-1].get("content") or "", usage, transcript, "budget")
            try:
                kw = dict(model=self.model, messages=messages, max_completion_tokens=max_output_tokens)
                if defs:
                    kw["tools"] = defs
                resp = self.client.chat.completions.create(**kw)
            except openai.RateLimitError as e:
                return AgentResult(f"Rate limited by provider: {e}", usage, transcript, "error")
            except openai.APIStatusError as e:
                return AgentResult(f"Provider error {e.status_code}", usage, transcript, "error")
            except openai.APIConnectionError as e:
                return AgentResult(f"Provider unreachable: {e}", usage, transcript, "error")
            if resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return AgentResult(msg.content or "", usage, transcript, "end")
            for call in msg.tool_calls:
                usage.tool_calls += 1
                if usage.tool_calls > max_tool_calls:
                    content, err = "Tool-call budget exhausted; answer with the evidence you have.", True
                else:
                    tool = by_name.get(call.function.name)
                    if on_event:
                        on_event(f"tool: {call.function.name}({call.function.arguments[:160]})")
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        out = tool.fn(args) if tool else {"error": f"unknown tool {call.function.name}"}
                        content, err = tool_result_text(out), False
                    except BudgetExceeded:
                        raise
                    except Exception as e:
                        content, err = f"tool error: {e}", True
                transcript.append({"tool": call.function.name, "error": err, "chars": len(content)})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
