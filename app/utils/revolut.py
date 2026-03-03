"""
Revolut Merchant API integration for TOWT.

Hosted Checkout Page approach:
1. Backend creates order via Merchant API → gets checkout_url
2. Customer is redirected to checkout_url (Revolut-hosted page)
3. Revolut webhook notifies us of payment status changes
4. We update PassengerPayment accordingly

API version: 2025-12-04
Docs: https://developer.revolut.com/docs/merchant/merchant-api
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("revolut")

settings = get_settings()

# ── API config ──────────────────────────────────────────
REVOLUT_API_VERSION = "2025-12-04"


def _base_url() -> str:
    """Return sandbox or production base URL."""
    if getattr(settings, "REVOLUT_SANDBOX", False):
        return "https://sandbox-merchant.revolut.com/api"
    return "https://merchant.revolut.com/api"


def _headers() -> dict:
    """Standard headers for Merchant API calls."""
    sk = getattr(settings, "REVOLUT_SECRET_KEY", "")
    return {
        "Authorization": f"Bearer {sk}",
        "Content-Type": "application/json",
        "Revolut-Api-Version": REVOLUT_API_VERSION,
    }


# ── Create Order ────────────────────────────────────────
async def create_order(
    amount_cents: int,
    currency: str = "EUR",
    description: str = "",
    customer_email: Optional[str] = None,
    merchant_reference: Optional[str] = None,
    redirect_url: Optional[str] = None,
) -> dict:
    """
    Create a Revolut Merchant order (Hosted Checkout Page).

    Args:
        amount_cents: Amount in minor units (e.g. 7034 = €70.34)
        currency: ISO 4217 currency code (EUR, USD, GBP)
        description: Shown on checkout page
        customer_email: For receipt sending
        merchant_reference: Internal reference for correlation
        redirect_url: Custom URL after successful payment

    Returns:
        dict with keys: id, token, checkout_url, state, amount, currency, ...

    Raises:
        httpx.HTTPStatusError on API errors
    """
    payload = {
        "amount": amount_cents,
        "currency": currency.upper(),
    }
    if description:
        payload["description"] = description
    if customer_email:
        payload["customer"] = {"email": customer_email}
    if merchant_reference:
        payload["merchant_order_data"] = {"reference": merchant_reference}
    if redirect_url:
        payload["redirect_url"] = redirect_url

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base_url()}/orders",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Revolut order created: {data.get('id')} — {amount_cents/100:.2f} {currency}")
        return data


# ── Retrieve Order ──────────────────────────────────────
async def get_order(order_id: str) -> dict:
    """Retrieve order details from Revolut."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_base_url()}/orders/{order_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


# ── Refund Order ────────────────────────────────────────
async def refund_order(order_id: str, amount_cents: Optional[int] = None, currency: str = "EUR") -> dict:
    """
    Refund a completed order (full or partial).
    If amount_cents is None, refunds the full amount.
    """
    payload = {}
    if amount_cents is not None:
        payload["amount"] = amount_cents
        payload["currency"] = currency.upper()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base_url()}/orders/{order_id}/refund",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Revolut refund for order {order_id}: {data.get('state')}")
        return data


# ── Webhook Signature Verification ─────────────────────
def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify Revolut webhook signature using HMAC-SHA256.
    The signing secret is provided in the Revolut Business dashboard.

    signature_header format: "v1=<hex_digest>"
    """
    signing_secret = getattr(settings, "REVOLUT_WEBHOOK_SECRET", "")
    if not signing_secret:
        logger.warning("REVOLUT_WEBHOOK_SECRET not configured — skipping verification")
        return True  # Allow in dev/test

    expected_sig = hmac.new(
        signing_secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    # signature_header is "v1=abc123..."
    parts = signature_header.split("=", 1)
    if len(parts) != 2:
        return False
    received_sig = parts[1]

    return hmac.compare_digest(expected_sig, received_sig)


# ── Map Revolut state to our payment status ─────────────
def map_revolut_state(revolut_state: str) -> str:
    """Map Revolut order state to PassengerPayment status."""
    mapping = {
        "pending": "pending",
        "processing": "pending",
        "authorised": "pending",
        "completed": "received",
        "cancelled": "failed",
        "failed": "failed",
    }
    return mapping.get(revolut_state, "pending")
