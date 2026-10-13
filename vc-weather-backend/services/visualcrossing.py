"""Standalone Visual Crossing Timeline API client (async, aiohttp).

This module is self-contained – no dependency on the Telegram bot.
Used by routes_weather.py for direct service-level calls if needed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from config import settings

logger = logging.getLogger(__name__)


class VCError(Exception):
    """General Visual Crossing API error."""

class VCAuthError(VCError):
    """Invalid or unauthorised API key."""

class VCLocationError(VCError):
    """Location not found."""


async def _get(
    session:  aiohttp.ClientSession,
    path:     str,
    api_key:  str,
    params:   Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    url = f"{settings.VC_BASE_URL}{path}"
    base = {"key": api_key, "contentType": "json"}
    if params:
        base.update(params)
    async with session.get(url, params=base, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status == 401:
            raise VCAuthError("Invalid or unauthorised API key.")
        if resp.status == 400:
            text = await resp.text()
            if "location" in text.lower() or "address" in text.lower():
                raise VCLocationError("Location not found.")
            raise VCError(f"Bad request: {text[:200]}")
        if resp.status == 429:
            raise VCError("VC API rate limit reached.")
        if resp.status != 200:
            text = await resp.text()
            raise VCError(f"VC API error {resp.status}: {text[:200]}")
        return await resp.json()


async def validate_key(session: aiohttp.ClientSession, api_key: str) -> bool:
    try:
        await _get(session, "/" + quote("London", safe=""), api_key,
                   {"include": "current", "elements": "temp"})
        return True
    except VCAuthError:
        return False


async def get_forecast(
    session: aiohttp.ClientSession, api_key: str,
    location: str, unit_system: str = "metric", days: int = 7,
) -> dict[str, Any]:
    loc = quote(location.strip(), safe="")
    data = await _get(session, f"/{loc}", api_key, {
        "unitGroup": unit_system, "include": "current,days",
    })
    if "days" in data:
        data["days"] = data["days"][:days]
    return data


async def get_current(
    session: aiohttp.ClientSession, api_key: str,
    location: str, unit_system: str = "metric",
) -> dict[str, Any]:
    loc = quote(location.strip(), safe="")
    return await _get(session, f"/{loc}/today", api_key, {
        "unitGroup": unit_system, "include": "current,days,alerts",
    })


async def get_hourly(
    session: aiohttp.ClientSession, api_key: str,
    location: str, unit_system: str = "metric",
) -> dict[str, Any]:
    loc = quote(location.strip(), safe="")
    return await _get(session, f"/{loc}/today", api_key, {
        "unitGroup": unit_system, "include": "hours",
    })
