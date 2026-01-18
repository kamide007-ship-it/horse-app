from __future__ import annotations

import os

import stripe
from flask import Response, abort, current_app, request

from extensions import db
from models import User


def _stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY")) and bool(os.environ.get("STRIPE_WEBHOOK_SECRET"))


def _price_id_for(plan: str) -> str | None:
    if plan == "starter":
        return os.environ.get("STRIPE_PRICE_STARTER")
    if plan == "pro":
        return os.environ.get("STRIPE_PRICE_PRO")
    if plan == "enterprise":
        return os.environ.get("STRIPE_PRICE_ENTERPRISE")
    return None


def create_checkout_session(plan: str, user: User):
    """Create Stripe Checkout session for subscriptions. Returns session object or None if not configured."""
    if not _stripe_configured():
        return None

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    price_id = _price_id_for(plan)
    if not price_id:
        return None

    # If a customer exists, reuse
    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email)
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        db.session.commit()

    domain = os.environ.get("APP_BASE_URL")
    if not domain:
        # Render provides RENDER_EXTERNAL_URL (optional). If not set, Stripe will still redirect to success/cancel relative.
        domain = request.host_url.rstrip("/")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{domain}/?checkout=success",
        cancel_url=f"{domain}/pricing?checkout=cancel",
        metadata={"user_id": str(user.id), "plan": plan},
    )
    return session


def handle_webhook(req) -> Response:
    if not _stripe_configured():
        return Response("Stripe not configured", status=200)

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    endpoint_secret = os.environ["STRIPE_WEBHOOK_SECRET"]

    payload = req.get_data(as_text=False)
    sig_header = req.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        abort(400)

    # Handle events
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = (session.get("metadata") or {}).get("user_id")
        plan = (session.get("metadata") or {}).get("plan")
        if user_id and plan:
            user = db.session.get(User, int(user_id))
            if user:
                user.plan = plan
                user.stripe_subscription_id = session.get("subscription")
                # reset monthly count upon upgrade
                user.refresh_monthly_counter()
                user.quota_used_month = 0
                db.session.commit()

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        if customer_id:
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                status = sub.get("status")
                if status in ("canceled", "unpaid", "incomplete_expired"):
                    user.plan = "free"
                    db.session.commit()

    return Response("ok", status=200)
