"""
Razorpay adapter — mock mode by default, real TEST-MODE API when configured.

Why an adapter instead of calling the SDK directly everywhere: it lets the
whole pipeline (and the test suite) run deterministically with zero
credentials, while leaving a single, clearly-marked place to plug in real
Razorpay test-mode keys for the actual submission. This is standard
dependency-inversion practice, not a shortcut — swapping RAZORPAY_MODE=live
and setting the two env vars is the entire integration step.

IMPORTANT: this must only ever be pointed at a Razorpay TEST-MODE account.
Nothing in this file has been exercised against live keys.
"""
from . import config


def create_retry_payment_link(checkout_id: str, amount_inr: float, contact_hint: str) -> dict:
    if config.RAZORPAY_MODE == "live":
        return _create_link_live(checkout_id, amount_inr, contact_hint)
    return _create_link_mock(checkout_id, amount_inr, contact_hint)


def _create_link_mock(checkout_id: str, amount_inr: float, contact_hint: str) -> dict:
    fake_id = f"plink_mock_{checkout_id}"
    return {
        "success": True,
        "mode": "mock",
        "payment_link": f"https://rzp.io/test-mock/{fake_id}",
        "detail": f"[mock] would create a Razorpay test payment link for INR {amount_inr:.2f}",
    }


def _create_link_live(checkout_id: str, amount_inr: float, contact_hint: str) -> dict:
    if not (config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET):
        return {
            "success": False,
            "mode": "live",
            "payment_link": None,
            "detail": "RAZORPAY_MODE=live but RAZORPAY_KEY_ID/SECRET are not set — refusing to call the API.",
        }
    try:
        import razorpay  # imported lazily so `mock` mode never requires the package at import time
        client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
        link = client.payment_link.create({
            "amount": int(round(amount_inr * 100)),  # paise
            "currency": "INR",
            "description": f"Payment retry for checkout {checkout_id}",
            "customer": {"contact": "", "email": contact_hint if "@" in contact_hint else ""},
            "notify": {"sms": False, "email": True},
            "reminder_enable": True,
            "notes": {"checkout_id": checkout_id, "source": "recovery-agent"},
        })
        return {
            "success": True,
            "mode": "live",
            "payment_link": link.get("short_url"),
            "detail": "created via Razorpay test-mode Payment Links API",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "mode": "live",
            "payment_link": None,
            "detail": f"Razorpay API call failed: {exc.__class__.__name__}: {exc}",
        }
