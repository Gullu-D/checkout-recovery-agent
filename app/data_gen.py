"""
Synthetic checkout / payment-failure batch generator.

Real Razorpay test-mode webhook payloads (`payment.failed`, abandoned order
events) can be dropped in later with the same shape as `CheckoutEvent` — this
generator exists so the pipeline, tests, and metrics can be exercised and
demoed without needing live credentials or waiting on real traffic.

Determinism: the caller passes a seed so a reviewer can regenerate the exact
same batch and re-verify the reported metrics themselves. There is no
cherry-picking here — every record in the batch is scored, including the
ones the agent gets wrong.
"""
import random
from datetime import datetime, timedelta
from .models import CheckoutEvent

FAILURE_REASONS = {
    # reason: (relative frequency, base probability it recovers IF nudged well)
    "card_declined": (0.30, 0.55),
    "insufficient_funds": (0.20, 0.20),   # nudging rarely helps if funds genuinely aren't there
    "network_timeout": (0.15, 0.80),      # transient — a retry link usually works
    "checkout_abandoned": (0.25, 0.35),   # user changed their mind — moderate recovery
    "otp_failed": (0.07, 0.65),
    "bank_server_error": (0.03, 0.75),
}


def generate_batch(n: int = 80, seed: int = 42):
    """Return a list of CheckoutEvent with a hidden ground-truth recovery
    probability baked in. Ground truth is intentionally noisy (not a clean
    lookup table) so a policy that just memorizes `failure_reason` cannot
    trivially top the leaderboard — it has to actually reason about
    per-record signals like attempt_number.
    """
    rng = random.Random(seed)
    reasons = list(FAILURE_REASONS.keys())
    weights = [FAILURE_REASONS[r][0] for r in reasons]

    batch = []
    base_time = datetime(2026, 8, 1, 9, 0, 0)
    for i in range(n):
        reason = rng.choices(reasons, weights=weights, k=1)[0]
        _, base_p = FAILURE_REASONS[reason]

        attempt_number = rng.choices([1, 2, 3, 4], weights=[0.55, 0.25, 0.12, 0.08])[0]
        # Recovery odds degrade with repeated attempts (customer fatigue) —
        # this is the signal an honest agent should pick up on to justify
        # escalating instead of nudging a 4th time.
        fatigue_penalty = 0.12 * (attempt_number - 1)
        noise = rng.uniform(-0.15, 0.15)
        p_recover = max(0.0, min(1.0, base_p - fatigue_penalty + noise))
        would_recover = rng.random() < p_recover

        amount = round(rng.uniform(199, 24999), 2)
        created_at = (base_time + timedelta(minutes=i * 7)).isoformat()

        batch.append(CheckoutEvent(
            checkout_id=f"chk_{i:04d}",
            merchant_id=f"merchant_{rng.randint(1, 6)}",
            amount_inr=amount,
            failure_reason=reason,
            customer_contact=f"cust_{i:04d}@masked.test",
            attempt_number=attempt_number,
            created_at=created_at,
            would_recover_if_nudged=would_recover,
        ))
    return batch
