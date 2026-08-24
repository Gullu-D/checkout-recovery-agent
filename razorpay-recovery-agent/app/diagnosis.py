"""
Root-cause diagnosis.

Deliberately rule-based and transparent rather than an opaque model call:
for a "money action" agent, an interviewer (or a real risk team) needs to be
able to read exactly why a diagnosis was made. A confidence score is
attached so the policy layer can route low-confidence cases to a human
instead of guessing — see LOW_CONFIDENCE_THRESHOLD in config.py.

An optional LLM rationale pass can be layered on top (see
`explain_with_llm`) purely to turn the machine reasoning into a readable
sentence for the audit trail / pitch demo. It never changes the decision
itself — the diagnosis is fully reproducible without it, and it fails
silently closed (falls back to the rule-based rationale) if no API key is
configured, so the pipeline never breaks in front of a panel because a
network call failed.
"""
import os
from .models import CheckoutEvent, Diagnosis

ROOT_CAUSE_MAP = {
    "network_timeout": ("transient_technical_failure", 0.90),
    "bank_server_error": ("transient_technical_failure", 0.85),
    "otp_failed": ("authentication_friction", 0.80),
    "card_declined": ("payment_instrument_issue", 0.70),
    "insufficient_funds": ("funds_unavailable", 0.75),
    "checkout_abandoned": ("intent_uncertain", 0.62),  # ambiguous on repeat attempts — could be
                                                        # price hesitation, distraction, or a
                                                        # change of mind — but a first-touch
                                                        # nudge is still a reasonable, low-cost
                                                        # bet. Confidence decays with attempt
                                                        # count below, so repeat abandoners
                                                        # correctly fall into the exception
                                                        # list instead of being nudged forever.
}


def diagnose(event: CheckoutEvent) -> Diagnosis:
    root_cause, base_confidence = ROOT_CAUSE_MAP.get(
        event.failure_reason, ("unknown_failure_mode", 0.30)
    )

    # Repeated attempts erode confidence that "one more nudge" is the right
    # call, independent of the original failure reason.
    confidence = base_confidence - 0.10 * max(0, event.attempt_number - 1)
    confidence = max(0.05, min(0.95, confidence))

    rationale = (
        f"failure_reason='{event.failure_reason}' on attempt "
        f"#{event.attempt_number} maps to root cause '{root_cause}' "
        f"(base confidence {base_confidence:.2f}, adjusted for attempt count "
        f"to {confidence:.2f})."
    )

    return Diagnosis(
        checkout_id=event.checkout_id,
        root_cause=root_cause,
        confidence=round(confidence, 3),
        rationale=rationale,
    )


def explain_with_llm(event: CheckoutEvent, diagnosis: Diagnosis) -> str:
    """Best-effort natural-language gloss on the rule-based diagnosis, for
    the audit trail / demo readability only. Returns the plain rationale
    unchanged if no OPENAI_API_KEY is set or the call fails for any reason —
    this function is intentionally allowed to fail closed and silent.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return diagnosis.rationale
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "In one short sentence, explain to a non-technical "
                    f"support agent why a payment with failure reason "
                    f"'{event.failure_reason}' on attempt {event.attempt_number} "
                    f"was diagnosed as '{diagnosis.root_cause}' "
                    f"(confidence {diagnosis.confidence})."
                ),
            }],
            max_tokens=60,
            timeout=8,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001 — deliberate broad catch, see docstring
        return diagnosis.rationale + f" [LLM gloss unavailable: {exc.__class__.__name__}]"
