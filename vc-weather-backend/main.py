"""VC Weather – Shopify Backend Entry Point"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from shopify_app.models import init_db
from shopify_app.routes_auth     import router as auth_router
from shopify_app.routes_admin    import router as admin_router
from shopify_app.routes_weather  import router as weather_router
from shopify_app.routes_webhooks import router as webhooks_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialised.")
    yield


app = FastAPI(
    title="VC Weather Shopify Backend",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
# Adds security headers on every response that are required or recommended
# for Shopify App Store compliance:
#   - X-Content-Type-Options: nosniff  (prevents MIME-sniffing attacks)
#   - X-XSS-Protection: 0             (modern browsers rely on CSP instead)
#   - Referrer-Policy                  (controls referrer leakage)
#   - Permissions-Policy              (deny unnecessary browser features)
#
# Note: Content-Security-Policy frame-ancestors is set per-route in
#       routes_admin.py because only the embedded admin page needs it.
#       A blanket CSP header here would conflict with that.
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-XSS-Protection", "0")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        return response


# ---------------------------------------------------------------------------
# CORS strategy
# ---------------------------------------------------------------------------
# Two policies are needed:
#   1. /shopify/weather  -> public GET/OPTIONS, allowed from ANY origin (*)
#      so storefront themes on any merchant domain can call it.
#   2. All other /shopify/* routes -> restricted to admin.shopify.com + APP_URL
#      (Shopify admin iframe + server-to-server calls).
#
# Middleware registration order (Starlette applies in REVERSE order added):
#   add_middleware(SecurityHeadersMiddleware) -- innermost, sees response last
#   add_middleware(WeatherCORSMiddleware)     -- inner
#   add_middleware(CORSMiddleware)            -- outermost, sees request first
#
# Request flow: browser -> CORSMiddleware -> WeatherCORSMiddleware
#                       -> SecurityHeadersMiddleware -> route
# ---------------------------------------------------------------------------

class WeatherCORSMiddleware(BaseHTTPMiddleware):
    """Handle CORS for the public /shopify/weather endpoint."""

    WEATHER_PATH = "/shopify/weather"

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(self.WEATHER_PATH):
            return await call_next(request)

        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin":  "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age":       "600",
                },
            )

        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(WeatherCORSMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://admin.shopify.com", settings.APP_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(auth_router,     prefix="/shopify")
app.include_router(admin_router,    prefix="/shopify")
app.include_router(weather_router,  prefix="/shopify")
app.include_router(webhooks_router, prefix="/shopify/webhooks")


@app.get("/health")
async def health():
    return {"status": "ok"}
