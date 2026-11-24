"""Analysis module registry. Order matters: valuation runs after the evidence-gathering modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import (analogues, competitors, corporate, demand, forensic, legal, management, mentions, product,
               sec_intel, sentiment, supply_chain, valuation)


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    capability: str
    compute: Callable
    findings: Callable


MODULES: dict[str, ModuleSpec] = {m.key: m for m in [
    ModuleSpec("sec_analysis", "SEC filing analysis", "SEC analysis", sec_intel.compute, sec_intel.findings),
    ModuleSpec("corporate_legitimacy", "Corporate legitimacy", "Corporate legitimacy", corporate.compute, corporate.findings),
    ModuleSpec("management_governance", "Management & governance", "Management and governance",
               management.compute, management.findings),
    ModuleSpec("forensic_accounting", "Forensic accounting", "Forensic accounting", forensic.compute, forensic.findings),
    ModuleSpec("supply_chain", "Supply-chain intelligence", "Supply-chain intelligence",
               supply_chain.compute, supply_chain.findings),
    ModuleSpec("product_research", "Product research", "Product research", product.compute, product.findings),
    ModuleSpec("customer_demand", "Customer & demand", "Customer sentiment", demand.compute, demand.findings),
    ModuleSpec("competitors", "Competitor research", "Competitor research", competitors.compute, competitors.findings),
    ModuleSpec("external_mentions", "Mentions by other filers", "Competitor research", mentions.compute, mentions.findings),
    ModuleSpec("legal_regulatory", "Legal & regulatory", "Legal and regulatory intelligence", legal.compute, legal.findings),
    ModuleSpec("market_sentiment", "Market sentiment & hype", "Market sentiment", sentiment.compute, sentiment.findings),
    ModuleSpec("historical_analogues", "Historical analogues", "Historical analogues", analogues.compute, analogues.findings),
    ModuleSpec("financial_valuation", "Financial valuation", "Financial valuation", valuation.compute, valuation.findings),
    ModuleSpec("market_expectations", "Market expectations", "Market expectations",
               lambda ctx: ctx.cache.get("financial_valuation_data") or valuation.compute(ctx),
               valuation.findings_expectations),
]}
