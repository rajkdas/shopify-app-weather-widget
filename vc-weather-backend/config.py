"""Centralised settings loaded from .env"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ValueError(
            f"Missing required environment variable: {key}\n"
            "Copy .env.example → .env and fill in all values."
        )
    return val


@dataclass(frozen=True)
class Settings:
    SHOPIFY_API_KEY:    str = field(default_factory=lambda: _req("SHOPIFY_API_KEY"))
    SHOPIFY_API_SECRET: str = field(default_factory=lambda: _req("SHOPIFY_API_SECRET"))
    ENCRYPTION_KEY:     str = field(default_factory=lambda: _req("ENCRYPTION_KEY"))
    DATABASE_URL:       str = field(default_factory=lambda: os.getenv("DATABASE_URL", "vc_shopify.db"))
    PORT:               int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    DEBUG:              bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    APP_URL:            str = field(default_factory=lambda: os.getenv("APP_URL", "https://apps.visualcrossing.com"))

    VC_BASE_URL: str = field(default_factory=lambda: (
        "https://weather.visualcrossing.com"
        "/VisualCrossingWebServices/rest/services/timeline"
    ))


settings = Settings()
