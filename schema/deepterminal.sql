-- DEEPTERMINAL relational schema (v0.1)
-- Target: PostgreSQL 15+. Written in a portable subset so the test suite can
-- load it into SQLite (tests/test_schema.py). JSON columns are TEXT here and
-- JSONB in the Postgres migration; timestamps are ISO-8601 UTC.
--
-- Design rules (docs/DATA_MODEL.md):
--  * every analytical number links to evidence_items, and every evidence item to a source;
--  * publication time (published_at), period described (period_start/end) and
--    retrieval time (retrieved_at) are separate columns: point-in-time queries
--    filter on published_at <= decision date;
--  * epistemic_status is mandatory and never collapsed;
--  * restatements are new rows (supersedes_id), never in-place updates.

-- ───────────────────────── Identity ─────────────────────────
CREATE TABLE companies (
    company_id      INTEGER PRIMARY KEY,
    legal_name      TEXT NOT NULL,
    cik             TEXT UNIQUE,                 -- SEC Central Index Key
    lei             TEXT,                        -- Legal Entity Identifier
    country         TEXT,
    sector          TEXT,
    industry        TEXT,
    is_financial_institution INTEGER NOT NULL DEFAULT 0,
    legitimacy_status TEXT CHECK (legitimacy_status IN ('unverified','verified','concerns','failed')),
    created_at      TEXT NOT NULL
);

CREATE TABLE securities (
    security_id     INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    ticker          TEXT NOT NULL,
    exchange        TEXT,
    share_class     TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD'
);

-- ───────────────────────── Provenance ─────────────────────────
CREATE TABLE sources (
    source_id       TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    publisher       TEXT NOT NULL,
    url             TEXT,
    source_type     TEXT NOT NULL CHECK (source_type IN
                    ('sec_filing','company_release','market_data','news','review_platform',
                     'government','academic','alternative_data','analyst','social','fixture','other')),
    published_at    TEXT,                        -- when the information became public
    retrieved_at    TEXT,                        -- when DEEPTERMINAL fetched it
    period_start    TEXT,
    period_end      TEXT,
    accession       TEXT,                        -- SEC accession number
    content_hash    TEXT,                        -- sha256 of archived raw content
    archive_uri     TEXT,                        -- immutable copy of the raw document
    licence         TEXT,                        -- see docs/DATA_SOURCES.md
    reliability     TEXT CHECK (reliability IN ('primary','reputable_secondary','unverified','synthetic')),
    synthetic       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_sources_published ON sources(published_at);

CREATE TABLE evidence_items (
    evidence_id     INTEGER PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(company_id),
    name            TEXT NOT NULL,
    value_numeric   REAL,
    value_text      TEXT,
    unit            TEXT,
    epistemic_status TEXT NOT NULL CHECK (epistemic_status IN
                    ('historical_fact','company_statement','corroborated_fact','estimate',
                     'model_assumption','analytical_inference','speculative_scenario','unverified_claim')),
    quality         TEXT NOT NULL CHECK (quality IN ('high','medium','low')),
    as_of           TEXT,
    published_at    TEXT,                        -- max(published_at) of supporting sources
    rationale       TEXT,                        -- required for assumptions/inferences without sources
    supersedes_id   INTEGER REFERENCES evidence_items(evidence_id),
    created_by      TEXT NOT NULL,               -- 'deterministic:<module>' or 'agent:<name>' or 'user'
    created_at      TEXT NOT NULL
);
CREATE INDEX ix_evidence_company_name ON evidence_items(company_id, name, published_at);

CREATE TABLE evidence_sources (
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    locator         TEXT,                        -- page, XBRL tag, paragraph, timestamp
    quote           TEXT,                        -- short verbatim excerpt for verification
    PRIMARY KEY (evidence_id, source_id)
);

-- Claims are statements in reports/assessments; links record support AND contradiction.
CREATE TABLE claims (
    claim_id        INTEGER PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(company_id),
    text            TEXT NOT NULL,
    epistemic_status TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE claim_evidence (
    claim_id        INTEGER NOT NULL REFERENCES claims(claim_id),
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id),
    relation        TEXT NOT NULL CHECK (relation IN ('supports','contradicts','context')),
    PRIMARY KEY (claim_id, evidence_id, relation)
);

-- ───────────────────────── Filings & financial facts ─────────────────────────
CREATE TABLE filings (
    accession       TEXT PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    form            TEXT NOT NULL,               -- 10-K, 10-Q, 8-K, DEF 14A, Form 4, 13F...
    filed_at        TEXT NOT NULL,
    period_end      TEXT,
    source_id       TEXT REFERENCES sources(source_id)
);

CREATE TABLE financial_facts (
    fact_id         INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    concept         TEXT NOT NULL,               -- e.g. us-gaap:Revenues
    period_start    TEXT,
    period_end      TEXT NOT NULL,
    value           REAL NOT NULL,
    unit            TEXT NOT NULL,
    accession       TEXT NOT NULL REFERENCES filings(accession),
    filed_at        TEXT NOT NULL,
    is_original     INTEGER NOT NULL,            -- first filing reporting this period
    supersedes_fact_id INTEGER REFERENCES financial_facts(fact_id)
);
CREATE INDEX ix_facts_pit ON financial_facts(company_id, concept, period_end, filed_at);

CREATE TABLE filing_changes (                    -- section-level diffs between successive filings
    change_id       INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    from_accession  TEXT NOT NULL REFERENCES filings(accession),
    to_accession    TEXT NOT NULL REFERENCES filings(accession),
    section         TEXT NOT NULL,               -- risk factors, MD&A, accounting policies...
    change_type     TEXT NOT NULL CHECK (change_type IN ('added','removed','modified')),
    summary         TEXT,
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id)
);

CREATE TABLE market_prices (
    security_id     INTEGER NOT NULL REFERENCES securities(security_id),
    as_of           TEXT NOT NULL,               -- exact timestamp of the price
    price           REAL NOT NULL,
    price_type      TEXT NOT NULL CHECK (price_type IN ('close','last','vwap','adjusted_close')),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    PRIMARY KEY (security_id, as_of, price_type)
);

-- ───────────────────────── Valuation ─────────────────────────
CREATE TABLE valuation_runs (
    run_id          INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    analysis_date   TEXT NOT NULL,               -- point-in-time cut-off
    price_evidence_id INTEGER NOT NULL REFERENCES evidence_items(evidence_id),
    engine_version  TEXT NOT NULL,
    case_file_hash  TEXT NOT NULL,               -- reproducibility: exact inputs
    market_cap      REAL,
    market_ev       REAL,
    diluted_shares  REAL,
    created_at      TEXT NOT NULL
);

CREATE TABLE method_selections (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    method          TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('primary','cross-check','excluded','caveat')),
    reason          TEXT NOT NULL,
    PRIMARY KEY (run_id, method, role)
);

CREATE TABLE valuation_assumptions (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    scenario        TEXT NOT NULL CHECK (scenario IN ('bear','base','bull','shared')),
    key             TEXT NOT NULL,               -- discount_rate, terminal_roic, revenue_growth[3]...
    value           REAL NOT NULL,
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id),
    rationale       TEXT NOT NULL,
    PRIMARY KEY (run_id, scenario, key)
);

CREATE TABLE bridge_items (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    item            TEXT NOT NULL,               -- debt, leases, pension, minority, ... (unique => no double count)
    amount          REAL NOT NULL,               -- signed EV→equity adjustment
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id),
    PRIMARY KEY (run_id, item)
);

CREATE TABLE scenario_results (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    scenario        TEXT NOT NULL CHECK (scenario IN ('bear','base','bull')),
    narrative       TEXT NOT NULL,
    enterprise_value REAL NOT NULL,
    equity_value    REAL NOT NULL,
    per_share       REAL NOT NULL,
    terminal_share  REAL NOT NULL,
    probability     REAL,                        -- NULL unless calibrated
    calibration_basis TEXT,
    yearly_json     TEXT NOT NULL,               -- revenue, margin, NOPAT, reinvestment, FCFF per year
    PRIMARY KEY (run_id, scenario),
    CHECK (probability IS NULL OR calibration_basis IS NOT NULL)
);

CREATE TABLE multiple_results (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    name            TEXT NOT NULL,
    value           REAL,
    meaningful      INTEGER NOT NULL,
    reason          TEXT,
    PRIMARY KEY (run_id, name)
);

CREATE TABLE reverse_dcf_results (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    lever           TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('unique','multiple','none_in_bounds')),
    solutions_json  TEXT NOT NULL,               -- list of solved values
    held_constant_json TEXT NOT NULL,            -- every assumption held fixed
    lower_bound     REAL NOT NULL,
    upper_bound     REAL NOT NULL,
    PRIMARY KEY (run_id, lever)
);

CREATE TABLE misvaluation_assessments (
    run_id          INTEGER PRIMARY KEY REFERENCES valuation_runs(run_id),
    verdict         TEXT NOT NULL CHECK (verdict IN
                    ('potentially_undervalued','approximately_fair','potentially_overvalued','too_uncertain')),
    margin_of_safety REAL NOT NULL,
    reasons_json    TEXT NOT NULL,
    steps_json      TEXT NOT NULL                -- 13-step investigation with performed flags
);

-- ───────────────────────── Multidimensional assessment (§10) ─────────────────────────
CREATE TABLE assessment_categories (
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    category        TEXT NOT NULL CHECK (category IN
                    ('financial_strength','business_quality','product_strength','competitive_positioning',
                     'supply_chain_resilience','management_governance','growth_sustainability',
                     'intrinsic_valuation','market_implied_expectations','market_sentiment',
                     'permanent_capital_loss_risk','future_catalysts','evidence_confidence')),
    key_findings    TEXT,
    historical_trend TEXT,
    important_unknowns TEXT,
    relevant_risks  TEXT,
    confidence_limitations TEXT,
    status          TEXT NOT NULL CHECK (status IN ('assessed','partial','not_assessed')),
    PRIMARY KEY (run_id, category)
);
CREATE TABLE assessment_evidence (
    run_id          INTEGER NOT NULL,
    category        TEXT NOT NULL,
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id),
    relation        TEXT NOT NULL CHECK (relation IN ('supports','counterevidence')),
    PRIMARY KEY (run_id, category, evidence_id),
    FOREIGN KEY (run_id, category) REFERENCES assessment_categories(run_id, category)
);

-- ───────────────────────── Research modules ─────────────────────────
CREATE TABLE people (
    person_id       INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    name            TEXT NOT NULL,
    role            TEXT NOT NULL,
    start_date      TEXT,
    end_date        TEXT
);
CREATE TABLE management_claims (                 -- forecasts/promises vs outcomes
    claim_id        INTEGER PRIMARY KEY REFERENCES claims(claim_id),
    person_id       INTEGER REFERENCES people(person_id),
    made_at         TEXT NOT NULL,
    target_date     TEXT,
    metric          TEXT,
    promised_value  REAL,
    outcome_value   REAL,
    outcome_evidence_id INTEGER REFERENCES evidence_items(evidence_id),
    status          TEXT CHECK (status IN ('pending','met','missed','withdrawn','unverifiable'))
);
CREATE TABLE insider_transactions (
    txn_id          INTEGER PRIMARY KEY,
    person_id       INTEGER REFERENCES people(person_id),
    security_id     INTEGER NOT NULL REFERENCES securities(security_id),
    txn_date        TEXT NOT NULL,
    filed_at        TEXT NOT NULL,
    shares          REAL NOT NULL,
    price           REAL,
    code            TEXT,                        -- Form 4 transaction code (P, S, A, M, F...)
    planned_10b5_1  INTEGER,
    accession       TEXT REFERENCES filings(accession)
);

CREATE TABLE competitors (
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    competitor_id   INTEGER NOT NULL REFERENCES companies(company_id),
    segment         TEXT NOT NULL,
    materiality_rationale TEXT NOT NULL,
    PRIMARY KEY (company_id, competitor_id, segment)
);
CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    name            TEXT NOT NULL,
    segment         TEXT,
    launched_at     TEXT,
    list_price      REAL,
    currency        TEXT
);
CREATE TABLE product_comparisons (               -- per-criterion, never a single universal score
    comparison_id   INTEGER PRIMARY KEY,
    criterion       TEXT NOT NULL CHECK (criterion IN
                    ('technical_benchmark','reliability','customer_satisfaction','ownership_cost',
                     'capabilities','price','availability','support_quality')),
    customer_segment TEXT NOT NULL,
    methodology     TEXT NOT NULL,
    product_a       INTEGER NOT NULL REFERENCES products(product_id),
    product_b       INTEGER NOT NULL REFERENCES products(product_id),
    result          TEXT NOT NULL CHECK (result IN ('a_better','b_better','comparable','insufficient_evidence')),
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id)
);
CREATE TABLE market_share_observations (
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    market          TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    share           REAL NOT NULL,
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id),
    PRIMARY KEY (company_id, market, period_end, evidence_id)
);

CREATE TABLE supply_chain_nodes (
    node_id         INTEGER PRIMARY KEY,
    company_id      INTEGER REFERENCES companies(company_id),
    name            TEXT NOT NULL,
    tier            TEXT NOT NULL CHECK (tier IN
                    ('raw_material','component','manufacturing','logistics','distribution','end_customer')),
    country         TEXT,
    financial_health TEXT
);
CREATE TABLE supply_chain_edges (
    from_node       INTEGER NOT NULL REFERENCES supply_chain_nodes(node_id),
    to_node         INTEGER NOT NULL REFERENCES supply_chain_nodes(node_id),
    dependency_share REAL,                       -- share of input sourced via this edge
    single_source   INTEGER NOT NULL DEFAULT 0,
    alternatives    TEXT,
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id),
    PRIMARY KEY (from_node, to_node)
);
CREATE TABLE supply_chain_events (
    event_id        INTEGER PRIMARY KEY,
    node_id         INTEGER REFERENCES supply_chain_nodes(node_id),
    event_type      TEXT NOT NULL,               -- shortage, strike, tariff, export_control, recall...
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    revenue_effect  TEXT CHECK (revenue_effect IN ('negative','positive','mixed','unknown')),
    margin_effect   TEXT CHECK (margin_effect IN ('negative','positive','mixed','unknown')),
    dominant_effect_analysis TEXT,               -- volume loss vs pricing power: which dominates
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id)
);

CREATE TABLE demand_indicators (                 -- reviews, returns, downloads, retention, job posts...
    indicator_id    INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    product_id      INTEGER REFERENCES products(product_id),
    metric          TEXT NOT NULL,
    platform        TEXT,
    region          TEXT,
    customer_segment TEXT,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    value           REAL NOT NULL,
    sample_size     INTEGER,
    verified_only   INTEGER,
    coverage_note   TEXT NOT NULL,               -- measurement limitations
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id)
);

CREATE TABLE sentiment_observations (
    obs_id          INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    channel         TEXT NOT NULL,               -- news, search, reddit, options, short_interest...
    observed_at     TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    method          TEXT NOT NULL,
    evidence_id     INTEGER NOT NULL REFERENCES evidence_items(evidence_id)
);

CREATE TABLE analogues (
    analogue_id     INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES valuation_runs(run_id),
    analogue_company TEXT NOT NULL,
    decision_date   TEXT NOT NULL,               -- information cut-off for the analogue
    outcome_class   TEXT NOT NULL CHECK (outcome_class IN ('success','failure','mixed')),
    selection_criteria TEXT NOT NULL,
    similarity_json TEXT NOT NULL,
    survivorship_note TEXT NOT NULL
);

CREATE TABLE catalysts (
    catalyst_id     INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    expected_date   TEXT,
    date_confidence TEXT CHECK (date_confidence IN ('confirmed','estimated','unknown')),
    catalyst_type   TEXT NOT NULL,
    description     TEXT NOT NULL,
    evidence_id     INTEGER REFERENCES evidence_items(evidence_id)
);

-- ───────────────────────── Agents & audit ─────────────────────────
CREATE TABLE agent_runs (
    agent_run_id    INTEGER PRIMARY KEY,
    agent           TEXT NOT NULL,               -- planner, filings, forensic, thesis_challenger...
    company_id      INTEGER REFERENCES companies(company_id),
    model           TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    tools_json      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','rejected')),
    output_claims   INTEGER NOT NULL DEFAULT 0,
    rejected_claims INTEGER NOT NULL DEFAULT 0   -- failed citation verification
);
CREATE TABLE audit_log (
    log_id          INTEGER PRIMARY KEY,
    at              TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action          TEXT NOT NULL,
    object_type     TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    detail_json     TEXT
);
