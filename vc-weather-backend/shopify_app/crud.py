"""CRUD helpers for the shops table + Fernet key encryption."""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger(__name__)

_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


# ── Encryption helpers ─────────────────────────────────────────────────

def encrypt(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt(enc: str) -> str:
    return _fernet.decrypt(enc.encode()).decode()


def mask(raw: str) -> str:
    if len(raw) <= 7:
        return "\u00b7" * len(raw)
    return raw[:4] + "\u00b7\u00b7\u00b7\u00b7\u00b7" + raw[-3:]


# ── Shop helpers ───────────────────────────────────────────────────────

async def get_or_create_shop(shop_domain: str) -> dict:
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO shops (shop_domain) VALUES (?)",
            (shop_domain,),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM shops WHERE shop_domain = ?", (shop_domain,))
        row = await cur.fetchone()
        return dict(row)


async def get_shop(shop_domain: str) -> Optional[dict]:
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM shops WHERE shop_domain = ?", (shop_domain,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def save_access_token(shop_domain: str, access_token: str) -> None:
    enc = encrypt(access_token)
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        await db.execute(
            "UPDATE shops SET access_token = ? WHERE shop_domain = ?",
            (enc, shop_domain),
        )
        await db.commit()
    logger.info("Access token saved for %s", shop_domain)


async def get_access_token(shop_domain: str) -> Optional[str]:
    shop = await get_shop(shop_domain)
    if not shop or not shop.get("access_token"):
        return None
    try:
        return decrypt(shop["access_token"])
    except InvalidToken:
        logger.warning("Corrupted access token for %s", shop_domain)
        return None


async def save_vc_key(shop_domain: str, raw_key: str) -> None:
    enc = encrypt(raw_key)
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        await db.execute(
            """
            INSERT INTO shops (shop_domain, encrypted_vc_key)
            VALUES (?, ?)
            ON CONFLICT(shop_domain) DO UPDATE
                SET encrypted_vc_key = excluded.encrypted_vc_key
            """,
            (shop_domain, enc),
        )
        await db.commit()
    logger.info("VC API key saved for %s", shop_domain)


async def get_vc_key(shop_domain: str) -> Optional[str]:
    shop = await get_shop(shop_domain)
    if not shop or not shop.get("encrypted_vc_key"):
        return None
    try:
        return decrypt(shop["encrypted_vc_key"])
    except InvalidToken:
        logger.warning("Corrupted VC key for %s \u2014 treating as missing", shop_domain)
        return None


async def save_settings(shop_domain: str, home_location: str, unit_system: str) -> None:
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        await db.execute(
            """
            INSERT INTO shops (shop_domain, home_location, unit_system)
            VALUES (?, ?, ?)
            ON CONFLICT(shop_domain) DO UPDATE
                SET home_location = excluded.home_location,
                    unit_system   = excluded.unit_system
            """,
            (shop_domain, home_location, unit_system),
        )
        await db.commit()


async def delete_shop(shop_domain: str) -> None:
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        await db.execute("DELETE FROM shops WHERE shop_domain = ?", (shop_domain,))
        await db.commit()
    logger.info("Shop record deleted: %s", shop_domain)
