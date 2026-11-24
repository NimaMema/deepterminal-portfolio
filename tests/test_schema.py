import sqlite3

import pytest

from conftest import ROOT


@pytest.fixture
def db():
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((ROOT / "schema" / "deepterminal.sql").read_text())
    return con


def test_schema_loads_with_core_tables(db):
    names = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    for t in ("sources", "evidence_items", "financial_facts", "valuation_runs", "scenario_results",
              "reverse_dcf_results", "misvaluation_assessments", "assessment_categories",
              "product_comparisons", "supply_chain_events", "demand_indicators", "analogues",
              "agent_runs"):
        assert t in names


def test_constraints_enforced(db):
    db.execute("insert into companies(company_id, legal_name, created_at) values (1,'X','2026-01-01')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into evidence_items(company_id,name,epistemic_status,quality,created_by,created_at)"
                   " values (1,'x','opinion','high','user','2026-01-01')")
    db.execute("insert into sources(source_id,title,publisher,source_type,published_at) "
               "values ('p','price','fixture','fixture','2026-01-01')")
    db.execute("insert into evidence_items(evidence_id,company_id,name,epistemic_status,quality,created_by,created_at)"
               " values (1,1,'price','historical_fact','low','user','2026-01-01')")
    db.execute("insert into valuation_runs(run_id,company_id,analysis_date,price_evidence_id,engine_version,"
               "case_file_hash,created_at) values (1,1,'2026-01-02',1,'0.1','h','2026-01-02')")
    with pytest.raises(sqlite3.IntegrityError):   # probability without calibration basis
        db.execute("insert into scenario_results values (1,'base','n',1,1,1,0.5,0.6,NULL,'[]')")
