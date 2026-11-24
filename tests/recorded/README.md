# Recorded SEC responses (genuine data only)

This directory holds **unmodified** SEC EDGAR responses used by
`tests/integration/test_recorded_sec.py`. SEC EDGAR data is U.S. government public
data and may be redistributed; keep the `.meta.json` sidecars (URL, retrieval time,
SHA-256) so every recording stays verifiable.

Record (needs network access to `www.sec.gov` and `data.sec.gov`):

```bash
export DEEPTERMINAL_SEC_USER_AGENT="Your Name your.email@example.com"
deepterminal record AAPL KO CAT --dest tests/recorded/sec
```

`prices.json` contains genuine archived SEC Form 4 transaction observations for AAPL, MSFT and
NVDA, extracted unchanged from `deploy/snapshot/responses.json.gz` at commit
`c566a05da86d807dfcbde6d72d00f6c3c00fda37`. Each entry retains the exact value, date, source,
filing URL and replay endpoint. The integration test compares them against that archive.
They are **not closing prices or current quotes**. The analysis date is 2026-10-30; 9% is an
explicit illustrative test assumption, not an estimated company discount rate. These tests
exercise the real-data pipeline without claiming freshness or investment suitability.

To add more genuine observations, retain this structure (replace placeholders with real data):

```json
{"AAPL": {"value": 0.0, "as_of": "YYYY-MM-DD", "source": "where you observed it",
          "analysis_date": "YYYY-MM-DD", "settings": {"discount_rate": 0.085}}}
```

Never place synthetic or hand-edited data here. Synthetic fixtures live in `fixtures/` and
`tests/sec_synth.py`.
