"""Tests for the scoring harness — these guard against the metrics module
ever becoming the thing that cherry-picks results."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import CheckoutEvent, Diagnosis, Decision
from app.metrics import compute_metrics


def make_result(action, would_recover, root_cause="transient_technical_failure", confidence=0.9):
    event = CheckoutEvent(
        checkout_id="chk_x", merchant_id="m1", amount_inr=500.0,
        failure_reason="network_timeout", customer_contact="a@b.test",
        attempt_number=1, created_at="2026-08-01T00:00:00",
        would_recover_if_nudged=would_recover,
    )
    diagnosis = Diagnosis(checkout_id="chk_x", root_cause=root_cause, confidence=confidence, rationale="r")
    decision = Decision(checkout_id="chk_x", action=action, rationale="r", guardrail_notes="none")
    return {"event": event, "diagnosis": diagnosis, "decision": decision,
            "action_success": True, "action_detail": "d"}


def test_full_batch_is_scored_no_filtering():
    results = [make_result("SEND_RETRY_LINK", True) for _ in range(10)]
    m = compute_metrics(results)
    assert m.batch_size == 10


def test_recovery_only_credited_for_actionable_and_true_ground_truth():
    results = [
        make_result("SEND_RETRY_LINK", True),   # counts as recovered
        make_result("SEND_RETRY_LINK", False),  # counts as unnecessary intervention
        make_result("NO_ACTION_COOLDOWN", True),  # NOT credited — agent took no action
        make_result("ESCALATE_TO_HUMAN", True),   # NOT credited — escalation, not a recovery
    ]
    m = compute_metrics(results)
    assert m.recovered_count == 1
    assert m.unnecessary_intervention_count == 1
    assert m.total_actions_taken == 2  # only the two SEND_RETRY_LINK count as "actions taken"


def test_low_confidence_cases_appear_in_exception_list():
    results = [make_result("NO_ACTION_LOW_CONFIDENCE", True, confidence=0.2)]
    m = compute_metrics(results)
    assert m.exception_count == 1
    assert "chk_x" in m.exceptions[0]


def test_empty_batch_does_not_divide_by_zero():
    m = compute_metrics([])
    assert m.batch_size == 0
    assert m.recovery_rate == 0.0
    assert m.unnecessary_intervention_rate == 0.0
