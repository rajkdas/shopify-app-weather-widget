"""GET /shopify/weather – secure proxy to Visual Crossing Timeline API."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from urllib.parse import quote

import aiohttp
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from config import settings
from shopify_app.crud import get_shop, get_vc_key

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Simple in-process per-shop rate limiter (60 req / 60 s) ───────────────
_rate: dict[str, list[float]] = defaultdict(list)
RATE_WINDOW = 60
RATE_MAX    = 60


def _check_rate(shop: str) -> None:
    now  = time.monotonic()
    hits = _rate[shop]
    _rate[shop] = [t for t in hits if now - t < RATE_WINDOW]
    if len(_rate[shop]) >= RATE_MAX:
        raise HTTPException(429, detail="Rate limit exceeded. Please slow down.")
    _rate[shop].append(now)


# ── VC Timeline API call ──────────────────────────────────────────────

async def _call_vc(
    api_key:  str,
    location: str,
    days:     int,
    units:    str,
    include:  str,
) -> dict:
    location_enc = quote(location.strip(), safe="")
    url = f"{settings.VC_BASE_URL}/{location_enc}"
    params = {
        "key":         api_key,
        "unitGroup":   units,
        "include":     include,
        "contentType": "json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, params=params, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 401:
                raise HTTPException(403, detail="Invalid Visual Crossing API key.")
            if resp.status == 400:
                text = await resp.text()
                raise HTTPException(422, detail=f"Bad VC request: {text[:200]}")
            if resp.status == 429:
                raise HTTPException(429, detail="Visual Crossing rate limit reached.")
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(502, detail=f"VC API error {resp.status}: {text[:200]}")
            data = await resp.json()

    # Trim to requested days to control payload size
    if "days" in data:
        data["days"] = data["days"][:days]
    return data


# ── Endpoint ─────────────────────────────────────────────────────────────

@router.get("/weather")
async def weather(
    request:  Request,
    shop:     str = Query(...,  description="myshopify.com domain"),
    location: str = Query("",   description="City, zip, or lat,lon. Empty = use app default."),
    days:     int = Query(7,    ge=1, le=15),
    units:    str = Query("metric"),
    include:  str = Query("current,days"),
):
    # Validate units
    if units not in ("metric", "us", "uk", "base"):
        units = "metric"

    # Rate limit
    _check_rate(shop)

    # Fetch shop record
    shop_data = await get_shop(shop)
    if not shop_data:
        raise HTTPException(401, detail="Shop not installed or not found.")

    # Get decrypted VC API key
    api_key = await get_vc_key(shop)
    if not api_key:
        raise HTTPException(403, detail="No Visual Crossing API key configured. Please open the app settings.")

    # Resolve location: block setting → app default → error
    resolved_location = location.strip()
    if not resolved_location:
        resolved_location = (shop_data.get("home_location") or "").strip()
    if not resolved_location:
        raise HTTPException(422, detail="No location provided and no default set in app settings.")

    # Resolve units: block setting → app default
    if not units:
        units = shop_data.get("unit_system") or "metric"

    # Call VC
    data = await _call_vc(api_key, resolved_location, days, units, include)

    return JSONResponse(content=data, headers={
        "Cache-Control": "public, max-age=600",   # 10-min CDN cache
        "Access-Control-Allow-Origin": "*",
    })
