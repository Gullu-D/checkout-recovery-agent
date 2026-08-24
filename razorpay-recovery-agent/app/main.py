"""
FastAPI entrypoint.

Endpoints:
  POST /api/run-batch          -> generate a fresh synthetic batch and run the full pipeline
  GET  /api/metrics            -> last computed batch metrics
  GET  /api/audit-trail        -> paginated audit log
  GET  /api/audit-trail/{id}   -> full decision trace for one checkout
  GET  /health                 -> liveness check
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from . import audit
from .orchestrator import run_batch
from .models import BatchMetrics, AuditRecord

app = FastAPI(
    title="Checkout & Payment-Failure Recovery Agent",
    description=(
        "Diagnoses payment failures / checkout drop-offs and recovers revenue "
        "through bounded, gated, audit-logged interventions. Built for the "
        "Razorpay AI Buildathon — AI Revenue Recovery track."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_last_metrics: BatchMetrics | None = None

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/run-batch", response_model=BatchMetrics)
def api_run_batch(n: int = Query(80, ge=1, le=500), seed: int = Query(42)):
    global _last_metrics
    _, metrics = run_batch(n=n, seed=seed, round_number=1, reset=True)
    _last_metrics = metrics
    return metrics


@app.get("/api/metrics", response_model=BatchMetrics)
def api_metrics():
    if _last_metrics is None:
        raise HTTPException(status_code=404, detail="No batch has been run yet. POST /api/run-batch first.")
    return _last_metrics


@app.get("/api/audit-trail", response_model=list[AuditRecord])
def api_audit_trail(limit: int = Query(200, ge=1, le=1000)):
    return audit.fetch_all(limit=limit)


@app.get("/api/audit-trail/{checkout_id}", response_model=list[AuditRecord])
def api_audit_trail_for_checkout(checkout_id: str):
    records = audit.fetch_for_checkout(checkout_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No audit records for {checkout_id}")
    return records


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
