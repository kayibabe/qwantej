"""Authenticated Flutterwave checkout and verified Pro subscription events."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
import hmac
import logging
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_authenticated_user
from app.config import settings
from app.database import get_db
from app.models import BillingOrder, BillingPayment, BillingSubscription, User


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])
FLUTTERWAVE_API = "https://api.flutterwave.com/v3"
FLUTTERWAVE_CHECKOUT_HOST = "checkout.flutterwave.com"
CURRENCY = "MWK"


def _checkout_is_configured() -> bool:
    return bool(
        settings.flutterwave_secret_key
        and settings.flutterwave_secret_hash
        and settings.flutterwave_pro_monthly_plan_id.isdigit()
        and settings.flutterwave_pro_monthly_price_mwk > 0
    )


def _expected_amount() -> Decimal:
    return Decimal(settings.flutterwave_pro_monthly_price_mwk).quantize(Decimal("0.01"))


def _offer() -> dict:
    return {
        "price": str(_expected_amount()),
        "currency": CURRENCY,
        "interval": "monthly",
        "checkout_enabled": _checkout_is_configured(),
    }


def _provider_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.flutterwave_secret_key}", "Content-Type": "application/json"}


def _return_url(request: Request, tx_ref: str) -> str:
    base = settings.public_app_base_url.strip().rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/upgrade?billing=return&tx_ref={quote(tx_ref)}"


async def _verify_by_id(transaction_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{FLUTTERWAVE_API}/transactions/{quote(transaction_id, safe='')}/verify",
            headers=_provider_headers(),
        )
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else None


async def _verify_by_reference(tx_ref: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{FLUTTERWAVE_API}/transactions/verify_by_reference",
            params={"tx_ref": tx_ref},
            headers=_provider_headers(),
        )
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else None


def _matches_expected_transaction(transaction: dict, tx_ref: str) -> bool:
    try:
        amount = Decimal(str(transaction.get("amount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (
        transaction.get("status") == "successful"
        and str(transaction.get("tx_ref", "")) == tx_ref
        and str(transaction.get("currency", "")).upper() == CURRENCY
        and amount == _expected_amount()
        and str(transaction.get("payment_type", "")).lower() == "card"
    )


async def _activate_from_verified_payment(
    db: AsyncSession,
    *,
    user: User,
    order: BillingOrder | None,
    transaction: dict,
) -> None:
    provider_transaction_id = str(transaction.get("id", ""))
    tx_ref = str(transaction.get("tx_ref", ""))
    if not provider_transaction_id or not tx_ref:
        return

    payment = await db.scalar(
        select(BillingPayment).where(BillingPayment.provider_transaction_id == provider_transaction_id)
    )
    if payment is None:
        try:
            amount = Decimal(str(transaction["amount"])).quantize(Decimal("0.01"))
        except (InvalidOperation, KeyError, TypeError, ValueError):
            return
        db.add(
            BillingPayment(
                user_id=user.id,
                order_id=order.id if order else None,
                provider_transaction_id=provider_transaction_id,
                tx_ref=tx_ref[:64],
                amount=amount,
                currency=CURRENCY,
                payment_type=str(transaction.get("payment_type", "card"))[:32],
            )
        )

    now = datetime.now(timezone.utc)
    if order is not None:
        order.status = "paid"
        order.completed_at = now
        order.checkout_url = None

    subscription = await db.scalar(
        select(BillingSubscription).where(
            BillingSubscription.user_id == user.id,
            BillingSubscription.provider == "flutterwave",
        )
    )
    if subscription is None:
        customer = transaction.get("customer") if isinstance(transaction.get("customer"), dict) else {}
        subscription = BillingSubscription(
            user_id=user.id,
            provider="flutterwave",
            provider_plan_id=settings.flutterwave_pro_monthly_plan_id,
            provider_customer_id=str(customer.get("id"))[:80] if customer.get("id") is not None else None,
            status="active",
            started_at=now,
            last_paid_at=now,
        )
        db.add(subscription)
    else:
        customer = transaction.get("customer") if isinstance(transaction.get("customer"), dict) else {}
        subscription.provider_plan_id = settings.flutterwave_pro_monthly_plan_id
        if customer.get("id") is not None:
            subscription.provider_customer_id = str(customer.get("id"))[:80]
        subscription.status = "active"
        subscription.last_paid_at = now
        subscription.cancelled_at = None

    user.plan = "pro"
    user.plan_source = "flutterwave"


@router.get("/offer")
async def get_pro_offer():
    return _offer()


@router.post("/checkout")
async def create_checkout(
    request: Request,
    user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "admin" or user.plan == "pro":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pro access is already active")
    if not _checkout_is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Pro checkout is not configured")

    pending = await db.scalar(
        select(BillingOrder)
        .where(BillingOrder.user_id == user.id, BillingOrder.status.in_(["initiating", "pending"]))
        .order_by(BillingOrder.id.desc())
    )
    if pending:
        if pending.checkout_url:
            return {"tx_ref": pending.tx_ref, "checkout_url": pending.checkout_url, "status": pending.status}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A checkout is already being prepared")

    tx_ref = f"qw-{user.id}-{uuid4().hex}"
    amount = _expected_amount()
    order = BillingOrder(user_id=user.id, tx_ref=tx_ref, amount=amount, currency=CURRENCY, status="initiating")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    payload = {
        "tx_ref": tx_ref,
        "amount": int(amount),
        "currency": CURRENCY,
        "payment_plan": int(settings.flutterwave_pro_monthly_plan_id),
        "redirect_url": _return_url(request, tx_ref),
        "customer": {"email": user.email, "name": user.username},
        "customizations": {
            "title": "Qwantej Pro",
            "description": f"Monthly Pro access (MWK {amount:,.2f})",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{FLUTTERWAVE_API}/payments", json=payload, headers=_provider_headers())
        try:
            body = response.json()
        except ValueError:
            body = None
        data = body.get("data") if isinstance(body, dict) else None
        checkout_url = data.get("link") if isinstance(data, dict) else None
        if not isinstance(body, dict) or response.status_code >= 400 or body.get("status") != "success" or not isinstance(checkout_url, str):
            order.status = "failed"
            order.checkout_url = None
            await db.commit()
            logger.warning("Flutterwave checkout creation failed with status %s", response.status_code)
            raise HTTPException(status_code=502, detail="Unable to start checkout. Please try again.")
        if not checkout_url.startswith(f"https://{FLUTTERWAVE_CHECKOUT_HOST}/"):
            order.status = "failed"
            await db.commit()
            raise HTTPException(status_code=502, detail="Payment provider returned an invalid checkout link")
        order.status = "pending"
        order.checkout_url = checkout_url
        await db.commit()
        return {"tx_ref": tx_ref, "checkout_url": checkout_url, "status": "pending"}
    except httpx.HTTPError as exc:
        order.status = "failed"
        order.checkout_url = None
        await db.commit()
        logger.warning("Flutterwave checkout request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Unable to reach checkout. Please try again.") from exc


@router.get("/checkout/{tx_ref}")
async def check_checkout(
    tx_ref: str,
    user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(BillingOrder).where(BillingOrder.tx_ref == tx_ref, BillingOrder.user_id == user.id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout was not found")
    if order.status == "paid":
        return {"status": "paid", "plan": "pro"}
    if order.status == "failed":
        return {"status": "failed", "plan": user.plan}
    if not _checkout_is_configured():
        return {"status": "pending", "plan": user.plan}

    try:
        transaction = await _verify_by_reference(tx_ref)
    except httpx.HTTPError as exc:
        logger.warning("Flutterwave return verification failed: %s", type(exc).__name__)
        return {"status": "pending", "plan": user.plan}
    if transaction is None:
        return {"status": "pending", "plan": user.plan}
    if _matches_expected_transaction(transaction, tx_ref):
        await _activate_from_verified_payment(db, user=user, order=order, transaction=transaction)
        await db.commit()
        return {"status": "paid", "plan": "pro"}
    if transaction.get("status") in {"failed", "cancelled", "canceled"}:
        order.status = "failed"
        order.checkout_url = None
        await db.commit()
        return {"status": "failed", "plan": user.plan}
    return {"status": "pending", "plan": user.plan}


@router.post("/webhook")
async def flutterwave_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    signature = request.headers.get("verif-hash", "")
    if not settings.flutterwave_secret_hash or not hmac.compare_digest(signature, settings.flutterwave_secret_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    payload = await request.json()
    if not isinstance(payload, dict):
        return {"received": True}
    event = payload.get("event")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    if event == "subscription.cancelled":
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        email = str(customer.get("email", "")).strip().lower()
        customer_id = str(customer.get("id", ""))
        plan_id = str(plan.get("id", ""))
        if (email or customer_id) and plan_id == settings.flutterwave_pro_monthly_plan_id:
            subscription = None
            if customer_id:
                subscription = await db.scalar(
                    select(BillingSubscription).where(
                        BillingSubscription.provider == "flutterwave",
                        BillingSubscription.provider_plan_id == plan_id,
                        BillingSubscription.provider_customer_id == customer_id,
                        BillingSubscription.status == "active",
                    )
                )
            if subscription is None and email:
                user_by_email = await db.scalar(select(User).where(User.email == email))
                if user_by_email:
                    subscription = await db.scalar(
                        select(BillingSubscription).where(
                            BillingSubscription.user_id == user_by_email.id,
                            BillingSubscription.provider == "flutterwave",
                            BillingSubscription.provider_plan_id == plan_id,
                            BillingSubscription.status == "active",
                        )
                    )
            if subscription:
                user = await db.get(User, subscription.user_id)
                now = datetime.now(timezone.utc)
                subscription.status = "cancelled"
                subscription.cancelled_at = now
                if user and user.plan_source == "flutterwave":
                    user.plan = "free"
                    user.plan_source = "manual"
                await db.commit()
        return {"received": True}

    if event != "charge.completed" or str(data.get("status", "")).lower() != "successful":
        return {"received": True}

    transaction_id = str(data.get("id", ""))
    if not transaction_id or not _checkout_is_configured():
        return {"received": True}
    try:
        transaction = await _verify_by_id(transaction_id)
    except httpx.HTTPError as exc:
        logger.warning("Flutterwave webhook verification failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Payment verification is temporarily unavailable") from exc
    if not isinstance(transaction, dict):
        raise HTTPException(status_code=503, detail="Payment verification is temporarily unavailable")

    tx_ref = str(transaction.get("tx_ref", ""))
    if not tx_ref or not _matches_expected_transaction(transaction, tx_ref):
        logger.warning("Flutterwave transaction did not match the configured Pro offer")
        return {"received": True}
    order = await db.scalar(select(BillingOrder).where(BillingOrder.tx_ref == tx_ref))
    if order:
        user = await db.get(User, order.user_id)
    else:
        customer = transaction.get("customer") if isinstance(transaction.get("customer"), dict) else {}
        email = str(customer.get("email", "")).strip().lower()
        customer_id = str(customer.get("id", ""))
        active_subscription = None
        if customer_id:
            active_subscription = await db.scalar(
                select(BillingSubscription).where(
                    BillingSubscription.provider == "flutterwave",
                    BillingSubscription.provider_plan_id == settings.flutterwave_pro_monthly_plan_id,
                    BillingSubscription.provider_customer_id == customer_id,
                    BillingSubscription.status == "active",
                )
            )
        if active_subscription is None and email:
            user_by_email = await db.scalar(select(User).where(User.email == email))
            if user_by_email:
                active_subscription = await db.scalar(
                    select(BillingSubscription).where(
                        BillingSubscription.user_id == user_by_email.id,
                        BillingSubscription.provider == "flutterwave",
                        BillingSubscription.provider_plan_id == settings.flutterwave_pro_monthly_plan_id,
                        BillingSubscription.status == "active",
                    )
                )
        user = await db.get(User, active_subscription.user_id) if active_subscription else None
    if user is None:
        logger.warning("Flutterwave transaction had no matching Qwantej order or active subscription")
        return {"received": True}

    await _activate_from_verified_payment(db, user=user, order=order, transaction=transaction)
    await db.commit()
    return {"received": True}
