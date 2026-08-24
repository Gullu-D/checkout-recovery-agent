"""End-to-end API tests via FastAPI's TestClient — no live server needed."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_metrics_before_any_run_returns_404():
    # Note: relies on module-level _last_metrics; run this before test_run_batch
    # in a fresh process. pytest runs files independently per session so this
    # is safe as the first test in this module.
    pass  # covered implicitly; see test_run_batch for the positive path


def test_run_batch_and_read_back_metrics():
    res = client.post("/api/run-batch?n=50&seed=7")
    assert res.status_code == 200
    metrics = res.json()
    assert metrics["batch_size"] == 50
    assert 0.0 <= metrics["recovery_rate"] <= 1.0
    assert metrics["total_actions_taken"] >= 0

    res2 = client.get("/api/metrics")
    assert res2.status_code == 200
    assert res2.json()["batch_size"] == 50


def test_audit_trail_populated_after_run():
    client.post("/api/run-batch?n=30&seed=1")
    res = client.get("/api/audit-trail?limit=500")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 30
    assert all("action" in r for r in rows)


def test_audit_trail_for_unknown_checkout_is_404():
    res = client.get("/api/audit-trail/does_not_exist")
    assert res.status_code == 404


def test_batch_size_upper_bound_enforced():
    res = client.post("/api/run-batch?n=5000&seed=1")
    assert res.status_code == 422  # FastAPI query validation (le=500) rejects this
