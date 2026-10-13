"""Database schema for Shopify shops table."""
from __future__ import annotations

import aiosqlite
from config import settings

CREATE_SHOPS = """
CREATE TABLE IF NOT EXISTS shops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_domain     TEXT UNIQUE NOT NULL,
    access_token    TEXT,
    encrypted_vc_key TEXT,
    home_location   TEXT,
    unit_system     TEXT NOT NULL DEFAULT 'metric',
    installed_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS shops_updated_at
AFTER UPDATE ON shops
BEGIN
    UPDATE shops SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END
"""


async def init_db() -> None:
    """Create tables. Safe to call on every startup."""
    async with aiosqlite.connect(settings.DATABASE_URL) as db:
        await db.execute(CREATE_SHOPS)
        await db.execute(UPDATE_TRIGGER)
        await db.commit()
