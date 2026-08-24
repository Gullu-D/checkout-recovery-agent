"""
Orchestrator: wires diagnosis -> policy -> execution -> audit for a batch,
then hands off to metrics.py for honest scoring.

`run_batch` processes the WHOLE batch every call — there is no code path
that lets a caller cherry-pick a subset of "good" records before scoring.
"""
from datetime import datetime, timezone
from . import config, audit
from .data_gen import generate_batch
from .diagnosis import diagnose
from .policy import decide
from .razorpay_client import create_retry_payment_link
from .metrics import compute_metrics


def run_batch(n: int = 80, seed: int = 42, round_number: int = 1, reset: bool = True):
    if reset:
        audit.reset_db()

    events = generate_batch(n=n, seed=seed)
    if len(events) > config.MAX_ACTIONS_PER_RUN:
        raise ValueError(
            f"batch size {len(events)} exceeds MAX_ACTIONS_PER_RUN="
            f"{config.MAX_ACTIONS_PER_RUN} — refusing to run unbounded."
        )

    results = []
    for event in events:
        diagnosis = diagnose(event)
        prior = audit.count_actions_for_checkout(event.checkout_id)
        decision = decide(event, diagnosis, prior_attempts_in_window=prior)

        if decision.action in ("SEND_RETRY_LINK",):
            outcome = create_retry_payment_link(
                event.checkout_id, event.amount_inr, event.customer_contact
            )
            action_success = outcome["success"]
            action_detail = outcome["detail"]
        elif decision.action == "SUGGEST_ALT_PAYMENT_METHOD":
            action_success = True
            action_detail = "[mock] would send an alternate-payment-method suggestion (UPI/net-banking)."
        elif decision.action == "ESCALATE_TO_HUMAN":
            action_success = True
            action_detail = "[mock] queued for human collections/support follow-up."
        else:  # NO_ACTION_* branches
            action_success = True
            action_detail = "no outbound action taken by design."

        audit.write_record(
            checkout_id=event.checkout_id,
            round_number=round_number,
            timestamp=datetime.now(timezone.utc).isoformat(),
            root_cause=diagnosis.root_cause,
            confidence=diagnosis.confidence,
            action=decision.action,
            rationale=decision.rationale,
            guardrail_notes=decision.guardrail_notes,
            action_success=action_success,
            action_detail=action_detail,
        )

        results.append({
            "event": event,
            "diagnosis": diagnosis,
            "decision": decision,
            "action_success": action_success,
            "action_detail": action_detail,
        })

    metrics = compute_metrics(results)
    return results, metrics
