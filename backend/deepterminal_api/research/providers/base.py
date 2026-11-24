"""LLM provider abstraction with bounded tool-use loops and token accounting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict           # JSON schema (object)
    fn: Callable[[dict], Any]  # executor; returns JSON-serialisable result


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    tool_calls: int = 0

    def add(self, i: int, o: int) -> None:
        self.input_tokens += i or 0
        self.output_tokens += o or 0
        self.calls += 1


@dataclass
class AgentResult:
    text: str
    usage: Usage
    transcript: list[dict] = field(default_factory=list)   # tool calls and results (for audit)
    stopped: str = "end"                                    # end | budget | max_tool_calls | refusal | error


class BudgetExceeded(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    def run(self, system: str, user: str, tools: list[ToolSpec], max_tool_calls: int, max_input_tokens: int,
            max_output_tokens: int, on_event: Callable[[str], None] | None = None) -> AgentResult: ...


def tool_result_text(result: Any, limit: int = 12000) -> str:
    s = json.dumps(result, default=str)
    return s if len(s) <= limit else s[:limit] + '..."(truncated)"'


def guarded_http_client():
    """httpx client for SDKs: every request passes the zero-cost policy check first."""
    import httpx

    from deepterminal.costpolicy import check_url

    def guard(request):
        check_url(str(request.url))
    return httpx.Client(event_hooks={"request": [guard]}, timeout=120)
