"""Pydantic schemas shared across the pipeline and the API layer."""
from pydantic import BaseModel, Field
from typing import Optional, List


class CheckoutEvent(BaseModel):
    checkout_id: str
    merchant_id: str
    amount_inr: float
    currency: str = "INR"
    failure_reason: str  # card_declined | insufficient_funds | network_timeout |
                          # checkout_abandoned | otp_failed | bank_server_error
    customer_contact: str  # masked email/phone, synthetic
    attempt_number: int = 1
    created_at: str
    # Ground truth used ONLY by the offline metrics harness to score the
    # agent honestly. The agent itself never reads this field.
    would_recover_if_nudged: Optional[bool] = None


class Diagnosis(BaseModel):
    checkout_id: str
    root_cause: str
    confidence: float
    rationale: str


class Decision(BaseModel):
    checkout_id: str
    action: str
    rationale: str
    guardrail_notes: str


class ActionResult(BaseModel):
    checkout_id: str
    action: str
    success: bool
    detail: str
    payment_link: Optional[str] = None


class AuditRecord(BaseModel):
    id: int
    checkout_id: str
    round_number: int
    timestamp: str
    root_cause: str
    confidence: float
    action: str
    rationale: str
    guardrail_notes: str
    action_success: bool
    action_detail: str


class BatchMetrics(BaseModel):
    batch_size: int
    total_actions_taken: int
    recovered_count: int
    recovery_rate: float
    unnecessary_intervention_count: int
    unnecessary_intervention_rate: float
    escalated_count: int
    exception_count: int
    exceptions: List[str]
    notes: str
