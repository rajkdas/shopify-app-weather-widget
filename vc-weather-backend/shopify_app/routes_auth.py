"""Shopify OAuth: /shopify/install  and  /shopify/callback"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import urllib.parse
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from config import settings
from shopify_app.crud import get_or_create_shop, save_access_token

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory nonce store (single-process; replace with Redis for multi-worker)
_nonces: set[str] = set()

SHOPIFY_SCOPES = ""


# ────────────────────────────────────────────────────────────────────────

def _validate_hmac(params: dict) -> bool:
    """Verify Shopify HMAC on install/callback query params."""
    received_hmac = params.pop("hmac", "")
    sorted_params = "&".join(
        f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}"
        for k, v in sorted(params.items())
    )
    computed = hmac.new(
        settings.SHOPIFY_API_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, received_hmac)


def _valid_shop_domain(shop: str) -> bool:
    import re
    return bool(re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.myshopify\.com$", shop))


# ── GET /shopify/install ──────────────────────────────────────────────────

@router.get("/install")
async def install(request: Request):
    """Redirect the merchant to Shopify OAuth authorisation page."""
    params = dict(request.query_params)
    shop   = params.get("shop", "")

    if not shop or not _valid_shop_domain(shop):
        raise HTTPException(400, detail="Missing or invalid shop parameter.")

    nonce = secrets.token_hex(16)
    _nonces.add(nonce)

    redirect_uri = f"{settings.APP_URL}/shopify/callback"
    auth_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={settings.SHOPIFY_API_KEY}"
        f"&scope={SHOPIFY_SCOPES}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&state={nonce}"
        f"&grant_options[]="
    )
    return RedirectResponse(auth_url)


# ── GET /shopify/callback ─────────────────────────────────────────────────

@router.get("/callback")
async def callback(request: Request):
    """Handle OAuth callback: exchange code for access token, store shop."""
    params = dict(request.query_params)
    shop   = params.get("shop", "")
    code   = params.get("code", "")
    state  = params.get("state", "")

    # 1. Validate shop domain
    if not shop or not _valid_shop_domain(shop):
        raise HTTPException(400, detail="Invalid shop parameter.")

    # 2. Validate nonce (CSRF)
    if state not in _nonces:
        raise HTTPException(403, detail="Invalid state parameter.")
    _nonces.discard(state)

    # 3. Validate HMAC
    hmac_params = dict(params)  # copy before pop
    if not _validate_hmac(hmac_params):
        raise HTTPException(403, detail="HMAC validation failed.")

    # 4. Exchange code for access token
    token_url = f"https://{shop}/admin/oauth/access_token"
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, json={
            "client_id":     settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "code":          code,
        })
    if resp.status_code != 200:
        logger.error("Token exchange failed for %s: %s", shop, resp.text)
        raise HTTPException(500, detail="Failed to obtain access token from Shopify.")

    token_data   = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(500, detail="No access_token in Shopify response.")

    # 5. Persist shop
    await get_or_create_shop(shop)
    await save_access_token(shop, access_token)
    logger.info("Shop installed: %s", shop)

    # 6. Redirect to embedded app home
    return RedirectResponse(
        f"https://{shop}/admin/apps/{settings.SHOPIFY_API_KEY}"
    )
