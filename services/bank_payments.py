from __future__ import annotations

import os
import secrets
from datetime import datetime

from extensions import db
from models import PaymentRequest, User


def _ref_code() -> str:
    # Short, human-friendly ref. Example: EVS-8F3K2J
    return "EVS-" + secrets.token_hex(3).upper()


def create_bank_payment_request(user: User, plan: str) -> PaymentRequest | None:
    """Create a pending payment request for bank transfer.

    Notes:
      - If a pending request exists for the same plan, reuse it.
      -... this keeps the flow simple without Stripe.
    """
    plan = (plan or "").strip().lower()
    if plan not in {"starter", "pro", "enterprise"}:
        return None

    # Reuse existing pending request (latest)
    existing = (
        PaymentRequest.query.filter_by(user_id=user.id, status="pending")
        .order_by(PaymentRequest.created_at.desc())
        .first()
    )
    if existing and existing.plan == plan:
        return existing

    # Create new unique ref
    for _ in range(10):
        code = _ref_code()
        if not PaymentRequest.query.filter_by(reference_code=code).first():
            pr = PaymentRequest(user_id=user.id, plan=plan, reference_code=code, status="pending")
            db.session.add(pr)
            db.session.commit()
            return pr

    return None


def bank_info() -> dict:
    """Return bank transfer info from env vars (with sensible defaults)."""
    return {
        "bank_name": os.environ.get("BANK_NAME", "楽天銀行"),
        "branch_name": os.environ.get("BANK_BRANCH", "エンカ支店"),
        "account_type": os.environ.get("BANK_ACCOUNT_TYPE", "普通"),
        "account_number": os.environ.get("BANK_ACCOUNT_NUMBER", "1546960"),
        "account_name": os.environ.get("BANK_ACCOUNT_NAME", "カミデケンタロウ"),
        "note": os.environ.get(
            "BANK_NOTE",
            "振込名義の末尾に参照コード（例: EVS-XXXXXX）を入れてください。",
        ),
    }


def approve_payment_request(pr: PaymentRequest) -> None:
    """Approve pending request: set plan and mark approved."""
    pr.status = "approved"
    pr.decided_at = datetime.utcnow()
    u = User.query.get(pr.user_id)
    if u:
        u.plan = pr.plan
        # Reset monthly counter immediately to avoid confusing limits
        u.quota_used_month = 0
        u.quota_month = ""
    db.session.commit()
