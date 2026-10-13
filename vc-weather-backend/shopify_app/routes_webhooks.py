"""Mandatory Shopify GDPR webhooks."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from shopify_app.crud import delete_shop

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify_hmac(request: Request, shopify_hmac: Optional[str]) -> None:
    """Verify the X-Shopify-Hmac-Sha256 header on incoming webhooks."""
    if not shopify_hmac:
        logger.warning("Webhook missing X-Shopify-Hmac-Sha256 header")
        raise HTTPException(401, detail="Missing HMAC signature.")

    body = await request.body()
    computed = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(),
        body,
        hashlib.sha256,
    ).digest()
    computed_b64 = base64.b64encode(computed).decode()
    if not hmac.compare_digest(computed_b64, shopify_hmac):
        logger.warning("Webhook HMAC mismatch")
        raise HTTPException(401, detail="HMAC verification failed.")


# ── customers/data_request ───────────────────────────────────────────

@router.post("/customers_data_request")
async def customers_data_request(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
):
    await _verify_hmac(request, x_shopify_hmac_sha256)
    payload = await request.json()
    shop_domain = payload.get("shop_domain", "")
    # This app does not store any customer PII.
    # The only data stored is: shop domain, encrypted Shopify access token,
    # encrypted VC API key, and location/unit preferences.
    # None of these are customer personal data.
    logger.info("customers/data_request received for %s – no customer data held", shop_domain)
    return JSONResponse({"status": "ok"})


# ── customers/redact ────────────────────────────────────────

@router.post("/customers_redact")
async def customers_redact(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
):
    await _verify_hmac(request, x_shopify_hmac_sha256)
    payload = await request.json()
    shop_domain = payload.get("shop_domain", "")
    logger.info("customers/redact received for %s – no customer data held", shop_domain)
    return JSONResponse({"status": "ok"})


# ── shop/redact ───────────────────────────────────────────

@router.post("/shop_redact")
async def shop_redact(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(default=None),
):
    await _verify_hmac(request, x_shopify_hmac_sha256)
    payload = await request.json()
    shop_domain = payload.get("shop_domain", "")
    if shop_domain:
        await delete_shop(shop_domain)
        logger.info("shop/redact: deleted all data for %s", shop_domain)
    return JSONResponse({"status": "ok"})
