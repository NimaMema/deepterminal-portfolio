"""Provider selection and budget ledger."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from ...config import get_settings
from ...db import session_scope
from ...models import LLMUsage
from .anthropic_provider import AnthropicProvider
from .base import AgentResult, BudgetExceeded, ToolSpec, Usage
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


def _ollama() -> OllamaProvider:
    s = get_settings()
    global _OLLAMA
    if _OLLAMA is None or (_OLLAMA.model, _OLLAMA.base_url) != (s.ollama_model, s.ollama_url.rstrip("/")):
        _OLLAMA = OllamaProvider(s.ollama_model, s.ollama_url, timeout=s.ollama_timeout_seconds, num_ctx=s.ollama_num_ctx)
    return _OLLAMA


_OLLAMA: OllamaProvider | None = None


def get_provider(name: str | None = None):
    """The AI provider to use, or None for rule-based (no generated prose) operation.

    Zero-cost policy:
    * ``auto`` (default) → local Ollama if it is running with the configured model, else rules;
    * ``ollama`` → Ollama if available, else rules (never a paid fallback);
    * ``anthropic`` / ``openai`` → only with DEEPTERMINAL_ALLOW_PAID_APIS=true and a key.
    """
    s = get_settings()
    choice = name or s.llm_provider
    if choice == "rules":
        return None
    if choice in ("auto", "ollama"):
        p = _ollama()
        return p if p.available() else None
    if not s.allow_paid_apis:
        return None                                     # paid provider selected but not enabled
    p = AnthropicProvider(s.anthropic_model) if choice == "anthropic" else OpenAIProvider(s.openai_model)
    return p if p.available() else None


def provider_status() -> list[dict]:
    s = get_settings()
    active = get_provider()
    ok, detail = _ollama().status()
    out = [{"provider": "ollama", "model": s.ollama_model, "configured": ok, "paid": False, "detail": detail,
            "key_env": None, "active": active is not None and active.name == "ollama"}]
    for p, env in ((AnthropicProvider(s.anthropic_model), "ANTHROPIC_API_KEY"), (OpenAIProvider(s.openai_model), "OPENAI_API_KEY")):
        enabled = s.allow_paid_apis and s.llm_provider == p.name
        out.append({"provider": p.name, "model": p.model, "configured": p.available() and enabled, "paid": True,
                    "detail": ("enabled by DEEPTERMINAL_ALLOW_PAID_APIS and DEEPTERMINAL_LLM_PROVIDER" if enabled else
                               "disabled (paid; opt in with DEEPTERMINAL_ALLOW_PAID_APIS=true and "
                               f"DEEPTERMINAL_LLM_PROVIDER={p.name})"),
                    "key_env": env, "active": active is not None and active.name == p.name})
    out.append({"provider": "rules", "model": "deterministic (no generated prose)", "configured": True, "paid": False,
                "detail": "always available", "key_env": None, "active": active is None})
    return out


PAID_PROVIDERS = ("anthropic", "openai")


def tokens_used_today(paid_only: bool = True) -> int:
    """Tokens used today. The budget is about money, so by default only paid providers count;
    local Ollama tokens cost nothing."""
    q = select(func.coalesce(func.sum(LLMUsage.input_tokens + LLMUsage.output_tokens), 0)).where(LLMUsage.day == date.today())
    if paid_only:
        q = q.where(LLMUsage.provider.in_(PAID_PROVIDERS))
    with session_scope() as db:
        return int(db.scalar(q) or 0)


def check_daily_budget(provider=None) -> None:
    if provider is not None and not getattr(provider, "paid", True):
        return                      # local model: no charge, no budget needed
    if tokens_used_today() >= get_settings().llm_daily_token_budget:
        raise BudgetExceeded("Daily LLM token budget reached (DEEPTERMINAL_LLM_DAILY_TOKEN_BUDGET).")


def record_usage(provider, usage: Usage, job_id: str | None) -> None:
    with session_scope() as db:
        db.add(LLMUsage(day=date.today(), provider=provider.name, model=provider.model,
                        input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, job_id=job_id))


__all__ = ["get_provider", "OllamaProvider", "provider_status", "ToolSpec", "AgentResult", "BudgetExceeded", "Usage",
           "check_daily_budget", "record_usage", "tokens_used_today"]
