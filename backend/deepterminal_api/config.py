"""Application settings from environment variables (never from source code)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPTERMINAL_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres@localhost:5432/deepterminal"
    data_mode: str = Field("live", pattern="^(live|demo)$")       # demo = synthetic, labelled companies
    sec_user_agent: str | None = None                               # "Name email@example.com"
    cache_dir: str = ".cache/sec"
    offline: bool = False                                           # replay cache only

    # AI. Zero-cost by default: "auto" means local Ollama if it is running, otherwise rule-based.
    # Paid providers (Anthropic/OpenAI) are used only if llm_provider names them explicitly AND
    # allow_paid_apis is true; they are never chosen automatically or as a fallback.
    llm_provider: str = Field("auto", pattern="^(auto|ollama|rules|anthropic|openai)$")
    allow_paid_apis: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"     # Apache-2.0 weights, supports tool calling
    ollama_num_ctx: int = 16384                   # Ollama's default (2048) would silently truncate evidence packs
    ollama_timeout_seconds: int = 1800            # CPU-only inference of a long synthesis can take minutes
    # Local-model profile: shorter prompts and answers keep CPU-only runs to a few minutes.
    ollama_synthesis_findings: int = 40           # most material findings sent to the model
    ollama_synthesis_evidence: int = 30           # evidence documents sent with them
    ollama_max_output_tokens: int = 900
    ollama_max_tool_calls: int = 5                # each tool round re-reads the growing context on CPU
    anthropic_model: str = "claude-opus-5-5"
    openai_model: str = "gpt-5"
    llm_max_output_tokens: int = 4000
    llm_max_tool_calls: int = 12                 # per agent run
    llm_max_input_tokens_per_job: int = 400_000  # hard budget per research job
    llm_daily_token_budget: int = 2_000_000

    # Market-data adapters (optional, user-supplied keys; nothing is purchased by the app)
    # Free data sources (no payment). Prices: Stooq end-of-day CSV; macro: FRED keyless CSV.
    # auto: Stooq → Alpha Vantage (if a free key is set) → SEC Form 4 insider trade prices
    price_provider: str = Field("auto", pattern="^(auto|stooq|alphavantage|sec_form4|none)$")
    stooq_apikey: str | None = None              # only if Stooq asks for its free key
    alphavantage_api_key: str | None = None      # FREE tier key (no payment); premium endpoints are never used

    api_token: str | None = None                 # if set, required as Bearer token
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_per_minute: int = 240
    max_filing_documents_per_job: int = 12
    chromium_executable: str | None = None
    log_level: str = "INFO"
    network_note: str | None = None              # shown on the Data sources screen, e.g. egress restrictions

    # Hosted public demo: a fixed snapshot served read-only. No network access (cache replay only),
    # rule-based AI only, no paid APIs, and only stateless calculations, chat and the Thesis
    # Challenger accept POSTs, each rate-limited per client.
    public_demo: bool = False
    # Reverse proxies in front of the API that append to X-Forwarded-For (0 = use the socket peer).
    # The client is the entry that many hops from the end, so a client-supplied header cannot spoof it.
    proxy_hops: int = Field(0, ge=0, le=5)
    demo_chat_per_hour: int = 30                 # chat messages per client per hour
    demo_jobs_per_hour: int = 3                  # Thesis Challenger runs per client per hour
    demo_global_per_hour: int = 600              # chat messages + runs across all clients
    demo_max_running_jobs: int = 1               # across all clients
    max_request_bytes: int = 64_000
    demo_showcase_path: str | None = None        # judges' guide data; default backend/demo/showcase.json
    demo_responses_path: str | None = None       # responses recorded with the snapshot (gzip JSON), preloaded

    @model_validator(mode="after")
    def _lock_public_demo(self):
        if self.public_demo:
            self.offline = True
            self.llm_provider = "rules"
            self.allow_paid_apis = False
            self.price_provider = "none"
            self.api_token = None
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
