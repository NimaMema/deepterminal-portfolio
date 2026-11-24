"""Ollama (local, open-weight models): the default AI engine. No API key, no per-token charges.

Uses Ollama's native chat API (``POST /api/chat``) with function tools, so the same
read-only research tools and budgets apply as for any other provider. Token counts come
from Ollama's ``prompt_eval_count`` / ``eval_count`` and are recorded with zero cost.
"""

from __future__ import annotations

import json
import time
from typing import Callable

import httpx

from deepterminal.costpolicy import check_url

from .base import AgentResult, BudgetExceeded, ToolSpec, Usage, tool_result_text


class OllamaProvider:
    name = "ollama"
    paid = False

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 1800.0,
                 client: httpx.Client | None = None, num_ctx: int = 16384):
        self.model = model
        self.num_ctx = num_ctx
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self._seen: tuple[float, bool, str] | None = None     # (checked_at, available, detail)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            check_url(self.base_url)
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def status(self) -> tuple[bool, str]:
        """(available, detail). Cached for 30 seconds so status pages do not hammer the server."""
        if self._seen and time.monotonic() - self._seen[0] < 30:
            return self._seen[1], self._seen[2]
        try:
            tags = self.client.get("/api/tags", timeout=3).json().get("models", [])
            names = [m.get("name", "") for m in tags]
            # "llama3.1" matches "llama3.1:latest"; a tagged name must match exactly.
            ok = self.model in names or (":" not in self.model and any(n.split(":")[0] == self.model for n in names))
            detail = "ready" if ok else (f"model '{self.model}' not pulled; run `ollama pull {self.model}`"
                                          + (f" (installed: {', '.join(names[:5])})" if names else ""))
        except (httpx.HTTPError, ValueError) as e:
            ok, detail = False, f"Ollama not reachable at {self.base_url} ({type(e).__name__})"
        self._seen = (time.monotonic(), ok, detail)
        return ok, detail

    def available(self) -> bool:
        return self.status()[0]

    def run(self, system: str, user: str, tools: list[ToolSpec], max_tool_calls: int, max_input_tokens: int,
            max_output_tokens: int, on_event: Callable[[str], None] | None = None) -> AgentResult:
        usage = Usage()
        transcript: list[dict] = []
        defs = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                  "parameters": t.parameters}} for t in tools]
        by_name = {t.name: t for t in tools}
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_text = ""
        while True:
            if usage.input_tokens > max_input_tokens:
                return AgentResult(last_text, usage, transcript, "budget")
            body = {"model": self.model, "messages": messages, "stream": False,
                    "options": {"num_predict": max_output_tokens, "temperature": 0.2, "num_ctx": self.num_ctx}}
            if defs:
                body["tools"] = defs
            try:
                r = self.client.post("/api/chat", json=body)
                r.raise_for_status()
                data = r.json()
            except httpx.HTTPStatusError as e:
                return AgentResult(f"Ollama error {e.response.status_code}: {e.response.text[:200]}", usage,
                                   transcript, "error")
            except httpx.HTTPError as e:
                return AgentResult(f"Ollama unreachable: {e}", usage, transcript, "error")
            usage.add(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
            if data.get("prompt_eval_count", 0) >= self.num_ctx - 8:
                return AgentResult("The prompt filled the model's context window (DEEPTERMINAL_OLLAMA_NUM_CTX); "
                                   "the answer would rest on truncated evidence, so none is given.", usage, transcript, "budget")
            msg = data.get("message") or {}
            last_text = msg.get("content") or last_text
            messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            calls = msg.get("tool_calls") or []
            if not calls:
                return AgentResult(msg.get("content") or "", usage, transcript, "end")
            for call in calls:
                fn = call.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments") or {}
                if isinstance(args, str):           # some models return JSON text
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                usage.tool_calls += 1
                if usage.tool_calls > max_tool_calls:
                    content, err = "Tool-call budget exhausted; answer with the evidence you have.", True
                else:
                    tool = by_name.get(name)
                    if on_event:
                        on_event(f"tool: {name}({json.dumps(args)[:160]})")
                    try:
                        out = tool.fn(dict(args)) if tool else {"error": f"unknown tool {name}"}
                        content, err = tool_result_text(out), False
                    except BudgetExceeded:
                        raise
                    except Exception as e:  # tool errors go back to the model
                        content, err = f"tool error: {e}", True
                transcript.append({"tool": name, "input": args, "error": err, "chars": len(content)})
                messages.append({"role": "tool", "tool_name": name, "content": content})
