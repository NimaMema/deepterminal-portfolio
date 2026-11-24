"""Backend API tests run against a real PostgreSQL test database in demo mode (synthetic, labelled data)."""

import os
import sys
from pathlib import Path

import pytest

# The suite drops and recreates the schema, so it only ever runs against a database whose name ends in
# "_test", taken from DEEPTERMINAL_TEST_DATABASE_URL — never from the app's own DEEPTERMINAL_DATABASE_URL.
TEST_DB = os.environ.get("DEEPTERMINAL_TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/deepterminal_test")
if not TEST_DB.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError(f"refusing to run destructive tests against {TEST_DB!r}: database name must end in '_test'")
os.environ["DEEPTERMINAL_DATABASE_URL"] = TEST_DB
os.environ["DEEPTERMINAL_DATA_MODE"] = "demo"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("DEEPTERMINAL_ALLOW_PAID_APIS", None)
os.environ["DEEPTERMINAL_OLLAMA_URL"] = "http://127.0.0.1:9"   # deterministic: no local model in tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def client():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from deepterminal_api.db import engine
    with engine().begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")
    from fastapi.testclient import TestClient
    from deepterminal_api.main import create_app
    from deepterminal_api.research import orchestrator
    orchestrator.submit = lambda job_id, sync=False: orchestrator.run_job(job_id)   # run jobs synchronously in tests
    import deepterminal_api.routers.research as rr
    rr.submit = orchestrator.submit
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="session")
def dqd(client):
    return client.get("/api/companies/resolve/DQD").json()
