# Architecture — Checkout & Payment-Failure Recovery Agent

Track 03: AI Revenue Recovery. This agent closes the loop from "a payment
failed or a checkout was abandoned" to "a bounded, logged intervention was
taken, or the case was honestly flagged as something it couldn't resolve."

## Pipeline

```
                 ┌──────────────────┐
  synthetic /    │   data_gen.py     │   (swap for real Razorpay test-mode
  real webhook   │  CheckoutEvent    │    webhooks: payment.failed, order
  events         └─────────┬─────────┘    abandoned — same schema)
                            │
                            ▼
                 ┌──────────────────┐
                 │   diagnosis.py    │   rule-based root-cause classifier
                 │  Diagnosis        │   + confidence score
                 │  (root_cause,     │   (optional LLM gloss for readability
                 │   confidence)     │    only — never changes the decision)
                 └─────────┬─────────┘
                            │
                            ▼
                 ┌──────────────────┐
                 │    policy.py      │   THE control point. Enforces every
                 │  Decision         │   guardrail (retry ceiling, cooldown,
                 │  (action,         │   low-confidence routing) before ever
                 │   rationale,      │   picking an action. Can only return
                 │   guardrails)     │   one of 5 allow-listed actions —
                 └─────────┬─────────┘   asserted in code, not just documented.
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
      ┌────────────────────┐  ┌─────────────────────┐
      │ razorpay_client.py │  │  (no-op branches:     │
      │ SEND_RETRY_LINK →  │  │  ESCALATE_TO_HUMAN,   │
      │ real or mock       │  │  NO_ACTION_COOLDOWN,  │
      │ Payment Link       │  │  NO_ACTION_LOW_CONF)  │
      └──────────┬─────────┘  └───────────┬───────────┘
                 └─────────────┬───────────┘
                                ▼
                     ┌──────────────────┐
                     │    audit.py       │   append-only SQLite log.
                     │  every decision   │   Written BEFORE the action result
                     │  + outcome        │   is even known to matter — this is
                     └─────────┬─────────┘   the audit trail, not an afterthought.
                                │
                                ▼
                     ┌──────────────────┐
                     │   metrics.py      │   scores the FULL batch against
                     │  recovery rate,   │   hidden ground truth. Cannot see
                     │  false-positive   │   or filter the batch before scoring —
                     │  rate, exceptions │   see orchestrator.run_batch.
                     └─────────┬─────────┘
                                │
                     ┌─────────┴─────────┐
                     ▼                   ▼
              FastAPI (main.py)   frontend/index.html
              JSON API             live dashboard
```

## Why it's structured this way

**Diagnosis and policy are separate files.** Diagnosis only ever answers
"what probably went wrong, and how sure am I." It has no idea what actions
exist. Policy is the only file that knows about `ALLOWED_ACTIONS` and the
guardrail constants. This separation is what makes it possible to say, in
an interview, "here is the one function that can ever spend money or
contact a customer" — `policy.decide()` — and nothing else in the codebase
can bypass it.

**Guardrails are checked in priority order, not independently.** Retry
ceiling beats everything else, including a highly confident diagnosis
(`test_guardrail_priority_retries_beats_everything_else` in
`tests/test_policy.py` locks this in). A confident agent that ignores its
own retry ceiling because "this one looks promising" is exactly the failure
mode this design forecloses.

**Low confidence routes to a human, it is never guessed at.** The
`LOW_CONFIDENCE_THRESHOLD` in `config.py` is what turns "the exceptions it
could not resolve" from a reporting afterthought into an actual code path.
Roughly 10–25% of a batch lands here depending on the random seed — that's
by design, not a bug to be tuned away. `checkout_abandoned` diagnoses
start above the threshold (a first-touch nudge is a reasonable, low-cost
bet) but decay below it on repeat attempts, so the same signal that once
justified action correctly stops justifying it as evidence accumulates
that the nudge isn't working.

**Metrics score the whole batch, no filtering.** `orchestrator.run_batch`
always passes every record through to `compute_metrics` — there's no
intermediate step where "hard" cases could be dropped before scoring.
"Recovered" only counts when the agent took an action AND the ground truth
says it would have converted anyway; a lucky outcome on a case the agent
did nothing about is never credited to the agent.

**Razorpay integration is an adapter, not a hard dependency.**
`razorpay_client.py` runs in `mock` mode with zero configuration (so the
test suite and any reviewer can run this offline, deterministically) and
switches to real Razorpay TEST-MODE Payment Links with two environment
variables. Nothing here has been run against live keys.

## Known limitations (stated up front, not discovered by a judge)

- The ground-truth "would this recover if nudged" label is synthetic — a
  real deployment needs either historical A/B data or a slower rollout
  with a holdout group to validate the recovery-rate number against reality.
- The diagnosis step is deliberately rule-based for transparency. It will
  not catch novel failure patterns outside `ROOT_CAUSE_MAP` — those fall
  through to `unknown_failure_mode` at low confidence and get routed to a
  human, which is the safe failure mode but not a scalable one long-term.
- Cooldown and retry-ceiling state currently live in the same SQLite table
  as the audit log and are scoped per `checkout_id` only — a production
  version would also want a per-customer (not just per-checkout) rate
  limit, so one customer with three separate abandoned carts doesn't get
  triple-nudged in the same day.
- The optional LLM gloss step (`diagnosis.explain_with_llm`) is not wired
  into the API by default — it's included to show the extension point, but
  the live pipeline currently only uses the deterministic rationale so
  demo runs stay reproducible without needing an API key.
