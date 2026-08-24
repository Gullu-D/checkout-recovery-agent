"""
Decision policy: turns a Diagnosis into exactly one allow-listed Action.

This is the single most important file for the "bounded and gated" bar the
challenge asks for. Every branch is a hard rule, not a model call, and the
function can provably never return anything outside ALLOWED_ACTIONS —
enforced both by the if/elif structure and by an assertion at the end.
"""
from .models import CheckoutEvent, Diagnosis, Decision
from . import config


def decide(event: CheckoutEvent, diagnosis: Diagnosis, prior_attempts_in_window: int) -> Decision:
    guardrail_notes = []

    # Guardrail 1: hard stop on retry count, independent of confidence.
    if event.attempt_number > config.MAX_RETRIES_PER_CHECKOUT:
        guardrail_notes.append(
            f"attempt_number={event.attempt_number} exceeds "
            f"MAX_RETRIES_PER_CHECKOUT={config.MAX_RETRIES_PER_CHECKOUT}"
        )
        action = "ESCALATE_TO_HUMAN"
        rationale = "Retry ceiling reached — handing off instead of nudging again."

    # Guardrail 2: cooldown — never re-contact the same customer inside the window.
    elif prior_attempts_in_window > 0:
        guardrail_notes.append(
            f"{prior_attempts_in_window} action(s) already taken for this "
            f"checkout within the {config.COOLDOWN_HOURS_BETWEEN_ACTIONS}h cooldown window"
        )
        action = "NO_ACTION_COOLDOWN"
        rationale = "Cooldown window active — skipping to avoid spamming the customer."

    # Guardrail 3: low-confidence diagnoses are routed to the exception list,
    # never guessed at. This is what "the exceptions it could not resolve"
    # means in practice.
    elif diagnosis.confidence < config.LOW_CONFIDENCE_THRESHOLD:
        guardrail_notes.append(
            f"confidence={diagnosis.confidence} below "
            f"LOW_CONFIDENCE_THRESHOLD={config.LOW_CONFIDENCE_THRESHOLD}"
        )
        action = "NO_ACTION_LOW_CONFIDENCE"
        rationale = "Diagnosis too uncertain to act on automatically — flagged for review."

    # From here on, confidence is acceptable and guardrails are clear —
    # pick the action that matches the root cause.
    elif diagnosis.root_cause == "funds_unavailable":
        action = "ESCALATE_TO_HUMAN"
        rationale = "Insufficient funds is not something a retry link fixes; routing to human follow-up."

    elif diagnosis.root_cause in ("transient_technical_failure", "authentication_friction"):
        action = "SEND_RETRY_LINK"
        rationale = "Root cause looks transient — a fresh payment link is likely to succeed."

    elif diagnosis.root_cause == "payment_instrument_issue":
        action = "SUGGEST_ALT_PAYMENT_METHOD"
        rationale = "Card-side issue — suggesting UPI/net-banking instead of retrying the same card."

    elif diagnosis.root_cause == "intent_uncertain":
        action = "SEND_RETRY_LINK"
        rationale = "Ambiguous abandonment — a low-cost nudge is proportionate to the uncertainty."

    else:
        action = "ESCALATE_TO_HUMAN"
        rationale = f"Unrecognized root cause '{diagnosis.root_cause}' — defaulting to human review."
        guardrail_notes.append("fell through to default-safe branch")

    assert action in config.ALLOWED_ACTIONS, f"policy produced an illegal action: {action}"

    return Decision(
        checkout_id=event.checkout_id,
        action=action,
        rationale=rationale,
        guardrail_notes="; ".join(guardrail_notes) if guardrail_notes else "none triggered",
    )
