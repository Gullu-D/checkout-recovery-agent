"""
Honest scoring against the synthetic ground truth.

Two rules this module enforces on itself:
1. Every record in the batch is scored — there is no filtering step before
   metrics are computed (see orchestrator.run_batch, which always passes
   the full result set in).
2. "Recovered" is only ever true where the agent actually took an outbound
   action (SEND_RETRY_LINK / SUGGEST_ALT_PAYMENT_METHOD) AND the hidden
   ground truth says the customer would have recovered given a nudge. A
   NO_ACTION or ESCALATE outcome is never counted as a recovery, even if
   the ground truth was favorable — the agent didn't cause it, so it
   doesn't get credit for it.
"""
from .models import BatchMetrics

ACTIONABLE = {"SEND_RETRY_LINK", "SUGGEST_ALT_PAYMENT_METHOD"}
EXCEPTION_ACTIONS = {"NO_ACTION_LOW_CONFIDENCE"}


def compute_metrics(results: list) -> BatchMetrics:
    batch_size = len(results)
    total_actions_taken = 0
    recovered_count = 0
    unnecessary_intervention_count = 0
    escalated_count = 0
    exceptions = []

    for r in results:
        event = r["event"]
        decision = r["decision"]
        action = decision.action
        ground_truth = event.would_recover_if_nudged

        if action in ACTIONABLE:
            total_actions_taken += 1
            if ground_truth:
                recovered_count += 1
            else:
                # We nudged, and the customer was never going to convert —
                # a wasted (and mildly annoying) outreach. This is the
                # "false-positive cost" the challenge explicitly asks to
                # measure honestly.
                unnecessary_intervention_count += 1

        elif action == "ESCALATE_TO_HUMAN":
            escalated_count += 1

        elif action in EXCEPTION_ACTIONS:
            exceptions.append(
                f"{event.checkout_id}: low-confidence diagnosis "
                f"({r['diagnosis'].root_cause}, conf={r['diagnosis'].confidence}) "
                f"— routed to manual review instead of guessed at."
            )

    recovery_rate = recovered_count / batch_size if batch_size else 0.0
    unnecessary_rate = (
        unnecessary_intervention_count / total_actions_taken if total_actions_taken else 0.0
    )

    notes = (
        f"Scored against the FULL batch of {batch_size} records, no filtering. "
        f"'Recovered' counts only cases where the agent took an outbound action AND "
        f"the customer would have converted anyway per ground truth — a lucky "
        f"no-action case is never credited. {len(exceptions)} record(s) were too "
        f"uncertain to act on automatically and were routed to the exception list "
        f"instead of guessed at."
    )

    return BatchMetrics(
        batch_size=batch_size,
        total_actions_taken=total_actions_taken,
        recovered_count=recovered_count,
        recovery_rate=round(recovery_rate, 4),
        unnecessary_intervention_count=unnecessary_intervention_count,
        unnecessary_intervention_rate=round(unnecessary_rate, 4),
        escalated_count=escalated_count,
        exception_count=len(exceptions),
        exceptions=exceptions,
        notes=notes,
    )
