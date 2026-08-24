# Checkout & Payment-Failure Recovery Agent

Built for the **Razorpay AI Buildathon — Track 03: AI Revenue Recovery**.

Detects payment failures and checkout drop-offs, diagnoses the root cause,
and executes a bounded, gated, fully-logged recovery action — or honestly
flags the case as one it couldn't resolve automatically. Every run is
scored against a held-out synthetic batch with no cherry-picking: recovery
rate, false-positive ("unnecessary intervention") cost, and an explicit
exception list are all reported together.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full pipeline diagram and
design rationale — read that before the code if you want the "why" first.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
# open http://127.0.0.1:8000  → click "Run batch"
```

Or with Docker:

```bash
docker compose up --build
# open http://localhost:8000
```

No credentials are required to run the full pipeline — it defaults to
`RAZORPAY_MODE=mock`, which generates deterministic fake payment links
instead of calling the real API. See `.env.example` for how to point it at
a real Razorpay **test-mode** account.

## Running the tests

```bash
pytest -v
```

17 tests cover three things specifically: the decision policy's guardrails
(retry ceiling, cooldown, low-confidence routing — `tests/test_policy.py`),
the honesty of the scoring harness (no filtering, no crediting recoveries
the agent didn't cause — `tests/test_metrics.py`), and the API end to end
(`tests/test_api.py`).

## What "recovery rate" actually means here

A record only counts as recovered if **both** are true: the agent took an
outbound action (a retry link or an alt-payment-method suggestion), *and*
the hidden ground truth says that customer would have converted given a
nudge. Escalations and no-actions are never counted as recoveries, even
when the ground-truth label happens to be favorable — the agent didn't
cause the outcome, so it doesn't get credit for it. The unnecessary-
intervention rate (nudges sent to customers who were never going to
convert) is reported alongside it, not hidden.

## Project layout

```
app/
  config.py          guardrail constants — the entire safety envelope in one file
  models.py          pydantic schemas
  data_gen.py        synthetic batch generator (swap for real Razorpay webhooks)
  diagnosis.py       root-cause classifier + confidence score
  policy.py          THE decision function — every guardrail lives here
  razorpay_client.py mock / real Razorpay test-mode adapter
  audit.py           SQLite audit trail
  orchestrator.py    wires the pipeline together for a batch
  metrics.py         honest scoring against ground truth
  main.py            FastAPI app
frontend/
  index.html         single-file dashboard (no build step)
tests/
  test_policy.py, test_metrics.py, test_api.py
```

## Honest limitations

See the "Known limitations" section at the bottom of
[ARCHITECTURE.md](./ARCHITECTURE.md) — stated up front rather than left for
a reviewer to find.
