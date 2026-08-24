"""Tests for the decision policy — the guardrails are the whole point of
this file. If these break, the "bounded and gated" claim is false."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import CheckoutEvent, Diagnosis
from app.policy import decide
from app import config


def make_event(**overrides):
    defaults = dict(
        checkout_id="chk_test",
        merchant_id="m1",
        amount_inr=999.0,
        failure_reason="network_timeout",
        customer_contact="a@b.test",
        attempt_number=1,
        created_at="2026-08-01T00:00:00",
        would_recover_if_nudged=True,
    )
    defaults.update(overrides)
    return CheckoutEvent(**defaults)


def make_diag(**overrides):
    defaults = dict(
        checkout_id="chk_test",
        root_cause="transient_technical_failure",
        confidence=0.9,
        rationale="test",
    )
    defaults.update(overrides)
    return Diagnosis(**defaults)


def test_action_always_in_allowlist():
    event = make_event()
    diag = make_diag()
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action in config.ALLOWED_ACTIONS


def test_max_retries_forces_escalation():
    event = make_event(attempt_number=config.MAX_RETRIES_PER_CHECKOUT + 1)
    diag = make_diag()
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action == "ESCALATE_TO_HUMAN"
    assert "MAX_RETRIES_PER_CHECKOUT" in decision.guardrail_notes


def test_cooldown_blocks_repeat_action():
    event = make_event()
    diag = make_diag()
    decision = decide(event, diag, prior_attempts_in_window=1)
    assert decision.action == "NO_ACTION_COOLDOWN"


def test_low_confidence_routes_to_exception_not_guessed():
    event = make_event()
    diag = make_diag(confidence=config.LOW_CONFIDENCE_THRESHOLD - 0.01)
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action == "NO_ACTION_LOW_CONFIDENCE"


def test_insufficient_funds_never_gets_a_retry_link():
    """Nudging someone who genuinely has no money is the textbook wasted
    (and mildly predatory-feeling) intervention this policy must avoid."""
    event = make_event(failure_reason="insufficient_funds")
    diag = make_diag(root_cause="funds_unavailable", confidence=0.9)
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action == "ESCALATE_TO_HUMAN"


def test_card_issue_suggests_alt_method_not_blind_retry():
    event = make_event(failure_reason="card_declined")
    diag = make_diag(root_cause="payment_instrument_issue", confidence=0.9)
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action == "SUGGEST_ALT_PAYMENT_METHOD"


def test_guardrail_priority_retries_beats_everything_else():
    """Even a high-confidence, clearly-actionable diagnosis must not
    override the hard retry ceiling."""
    event = make_event(attempt_number=config.MAX_RETRIES_PER_CHECKOUT + 5)
    diag = make_diag(root_cause="transient_technical_failure", confidence=0.99)
    decision = decide(event, diag, prior_attempts_in_window=0)
    assert decision.action == "ESCALATE_TO_HUMAN"
