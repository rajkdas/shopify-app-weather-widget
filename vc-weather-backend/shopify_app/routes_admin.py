"""
Shopify embedded admin page.

Design: plain HTML. All colors via Polaris CSS tokens injected by the
Shopify admin iframe. Fallback values are taken directly from Shopify
admin DevTools computed styles so the button is never invisible.
App Bridge is loaded FIRST as required by Shopify.

SECURITY:
- GET  /shopify/home  → First load: thin bootstrap shell only (no shop data).
                        Second load: triggered by JS via fetch() with
                        Authorization: Bearer <session_token> header;
                        backend verifies JWT before returning real UI.
- POST /shopify/home  → Requires a valid session_token form field.
                        Token is refreshed by JS on every submit click
                        so it never goes stale (60 s Shopify expiry).
- JWT verification    → HS256, checks: signature, exp (+30 s clock skew),
                        nbf, iss/dest domain match, aud == API key.
                        Token never appears in URL or server logs.
- XSS                 → All user-supplied strings HTML-escaped before
                        being interpolated into the template.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings
from shopify_app.crud import decrypt, get_shop, mask, save_settings, save_vc_key

logger = logging.getLogger(__name__)
router = APIRouter()

_APP_BRIDGE_CDN = "https://cdn.shopify.com/shopifycloud/app-bridge.js"

# ---------------------------------------------------------------------------
# JWT / session-token verification
# ---------------------------------------------------------------------------

def _b64url_decode(data: str) -> bytes:
    """Decode a base64url string, adding padding as needed."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


async def _verify_session_token(token: str, expected_shop: str) -> dict:
    """
    Verify a Shopify App Bridge session token (HS256 JWT).

    Raises HTTPException(401) on any failure so callers can handle it
    uniformly without catching multiple exception types.
    """
    if not token or not expected_shop:
        raise HTTPException(status_code=401, detail="Missing session token or shop")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Malformed session token")

    header_b64, payload_b64, signature_b64 = parts

    # 1. Verify HMAC-SHA256 signature
    message = f"{header_b64}.{payload_b64}".encode()
    secret  = settings.SHOPIFY_API_SECRET.encode()
    expected_sig = (
        base64.urlsafe_b64encode(
            hmac.new(secret, message, hashlib.sha256).digest()
        )
        .decode()
        .rstrip("=")
    )
    if not hmac.compare_digest(expected_sig, signature_b64.rstrip("=")):
        raise HTTPException(status_code=401, detail="Invalid session token signature")

    # 2. Decode payload
    try:
        payload: dict = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=401, detail="Unreadable session token payload")

    now = time.time()

    # 3. Expiry — allow 30 s of clock skew between our server and Shopify
    exp = payload.get("exp")
    if not exp or now > (float(exp) + 30):
        raise HTTPException(status_code=401, detail="Session token expired")

    # 4. Not-before
    nbf = payload.get("nbf")
    if nbf and now < float(nbf):
        raise HTTPException(status_code=401, detail="Session token not yet valid")

    # 5. iss / dest must share the same domain (Shopify spec)
    def _domain(url: str) -> str:
        return url.split("//")[-1].split("/")[0].lower()

    iss_domain  = _domain(payload.get("iss",  ""))
    dest_domain = _domain(payload.get("dest", ""))

    if not iss_domain or iss_domain != dest_domain:
        raise HTTPException(status_code=401, detail="Session token domain mismatch")

    # 6. dest must match the shop we were called with
    if dest_domain != expected_shop.lower():
        raise HTTPException(status_code=401, detail="Session token shop mismatch")

    # 7. Audience must equal our API key
    if payload.get("aud") != settings.SHOPIFY_API_KEY:
        raise HTTPException(status_code=401, detail="Session token audience mismatch")

    return payload


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _e(value: str) -> str:
    """HTML-escape a string for safe interpolation into the template."""
    return html.escape(str(value), quote=True)


def _bootstrap_shell(shop: str) -> str:
    """
    Thin first-load shell.

    Contains App Bridge, the shopify-api-key meta tag, and a small JS
    snippet that:
      1. Obtains a fresh session token from App Bridge.
      2. Fetches /shopify/home?shop=... with Authorization: Bearer <token>.
      3. Replaces the document with the authenticated HTML response.

    No shop data is included here — the shell is safe to serve without
    session verification because it contains nothing sensitive.
    """
    safe_shop    = _e(shop)
    safe_api_key = _e(settings.SHOPIFY_API_KEY)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="shopify-api-key" content="{safe_api_key}">
  <title>Visual Crossing Weather</title>
  <!-- App Bridge MUST be the first script tag (Shopify requirement) -->
  <script src="{_APP_BRIDGE_CDN}"></script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px; display: flex; align-items: center;
      justify-content: center; min-height: 100vh; margin: 0;
      color: var(--p-color-text, #202223);
      background: var(--p-color-bg-app, #f1f1f1);
    }}
    .loading {{
      display: flex; flex-direction: column; align-items: center; gap: 12px;
    }}
    .spinner {{
      width: 28px; height: 28px;
      border: 3px solid var(--p-color-border, #e1e3e5);
      border-top-color: var(--p-color-bg-fill-brand, #303030);
      border-radius: 50%; animation: spin .7s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .error-msg {{
      color: #6b1117; background: #fff4f4; border: 1px solid #e0393e;
      border-radius: 8px; padding: 12px 16px; max-width: 420px;
      text-align: center; display: none;
    }}
  </style>
</head>
<body>
  <div class="loading" id="loading">
    <div class="spinner"></div>
    <span>Loading settings&hellip;</span>
  </div>
  <div class="error-msg" id="error-msg">
    Could not authenticate with Shopify.<br>
    Please reload this page from the Shopify admin.
  </div>

  <script>
    (async function () {{
      const shop = {json.dumps(shop)};
      try {{
        const token = await window.shopify.idToken();
        const res = await fetch(
          '/shopify/home?shop=' + encodeURIComponent(shop),
          {{ headers: {{ 'Authorization': 'Bearer ' + token }} }}
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const pageHtml = await res.text();
        document.open();
        document.write(pageHtml);
        document.close();
      }} catch (err) {{
        console.error('[VC Weather] Auth error:', err);
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error-msg').style.display = 'block';
      }}
    }})();
  </script>
</body>
</html>"""


def _render_home(
    shop: str,
    masked_key: str,
    home_location: str,
    unit_system: str,
    saved: bool = False,
    error: str = "",
) -> str:
    """
    Render the full authenticated settings page.

    All dynamic strings are HTML-escaped via _e() before interpolation.
    The session_token hidden field is populated by JS on every submit
    click (not once on load) so it is always fresh within Shopify's
    60-second token window.
    """
    safe_shop          = _e(shop)
    safe_masked        = _e(masked_key)
    safe_home_location = _e(home_location)
    safe_api_key       = _e(settings.SHOPIFY_API_KEY)

    # Banner
    banner_html = ""
    if saved:
        banner_html = """
      <div class="banner banner-success" role="status" aria-live="polite">
        <span class="banner-icon">&#10003;</span>
        Settings saved successfully.
      </div>"""
    elif error:
        banner_html = f"""
      <div class="banner banner-critical" role="alert">
        <span class="banner-icon">&#9888;</span>
        {_e(error)}
      </div>"""

    # API key status hint
    if masked_key:
        key_status_html = (
            f'<p class="hint">Current key: '
            f'<code class="masked-key">{safe_masked}</code></p>'
        )
    else:
        key_status_html = (
            '<p class="hint">No key saved yet. '
            '<a href="https://www.visualcrossing.com/weather-data-editions/" '
            'target="_blank" rel="noopener noreferrer">Get a free API key</a>.</p>'
        )

    unit_metric = "selected" if unit_system == "metric" else ""
    unit_us     = "selected" if unit_system == "us"     else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="shopify-api-key" content="{safe_api_key}">
  <title>Visual Crossing Weather &ndash; Settings</title>

  <!-- App Bridge MUST be the first script tag (Shopify requirement) -->
  <script src="{_APP_BRIDGE_CDN}"></script>

  <style>
    /* =================================================================
     * Colors use Polaris CSS tokens injected by the Shopify admin iframe.
     * Fallback values are taken directly from Shopify admin DevTools
     * computed styles (inspected on the native 'Create discount' button)
     * so UI is never invisible when tokens resolve asynchronously.
     *
     * Exception: .banner-success / .banner-critical use fixed semantic
     * colors per Polaris feedback color spec (green=success, red=critical).
     * ================================================================= */

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ font-size: 16px; }}

    body {{
      font-family: var(--p-font-family-sans,
                   -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
      font-size: 14px;
      line-height: 1.5;
      color: var(--p-color-text, #202223);
      background: var(--p-color-bg-app, #f1f1f1);
      -webkit-font-smoothing: antialiased;
    }}

    .page {{
      max-width: 860px;
      margin: 0 auto;
      padding: 24px 20px 48px;
    }}

    .page-title {{
      font-size: 20px;
      font-weight: 600;
      color: var(--p-color-text, #202223);
      margin: 0 0 4px;
    }}
    .page-subtitle {{
      font-size: 14px;
      color: var(--p-color-text-secondary, #6d7175);
      margin: 0 0 24px;
    }}

    /* Banners: intentionally fixed semantic colors per Polaris feedback spec */
    .banner {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 16px;
      border-radius: 8px;
      border: 1px solid;
      font-size: 14px;
      margin-bottom: 20px;
    }}
    .banner-icon {{ flex-shrink: 0; font-weight: 700; }}
    .banner-success {{
      background: #f1f8f5;
      border-color: #008060;
      color: #1a4a39;
    }}
    .banner-critical {{
      background: #fff4f4;
      border-color: #e0393e;
      color: #6b1117;
    }}

    .layout {{
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 24px;
      align-items: start;
    }}
    @media (max-width: 680px) {{
      .layout {{ grid-template-columns: 1fr; }}
    }}

    .annotation-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--p-color-text, #202223);
      margin: 0 0 4px;
    }}
    .annotation-desc {{
      font-size: 13px;
      color: var(--p-color-text-secondary, #6d7175);
      line-height: 1.5;
    }}

    .card {{
      background: var(--p-color-bg-surface, #ffffff);
      border: 1px solid var(--p-color-border, #e1e3e5);
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(26,26,26,.08);
      padding: 20px;
    }}

    .form-stack {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}

    .field-group {{ display: flex; flex-direction: column; gap: 4px; }}

    .field-label {{
      font-size: 14px;
      font-weight: 500;
      color: var(--p-color-text, #202223);
    }}

    .hint {{
      font-size: 13px;
      color: var(--p-color-text-secondary, #6d7175);
    }}
    .hint a {{
      color: var(--p-color-text-link, #2c6ecb);
      text-decoration: none;
    }}
    .hint a:hover {{ text-decoration: underline; }}

    .masked-key {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 12px;
      background: var(--p-color-bg-surface-secondary, #f6f6f7);
      border: 1px solid var(--p-color-border, #e1e3e5);
      border-radius: 4px;
      padding: 1px 6px;
      color: var(--p-color-text, #202223);
    }}

    .input {{
      display: block;
      width: 100%;
      padding: 8px 12px;
      font-size: 14px;
      font-family: inherit;
      color: var(--p-color-text, #202223);
      background: var(--p-color-bg-surface, #ffffff);
      border: 1px solid var(--p-color-border-input, #8c9196);
      border-radius: 6px;
      outline: none;
      transition: border-color .15s, box-shadow .15s;
    }}
    .input::placeholder {{ color: var(--p-color-text-disabled, #8c9196); }}
    .input:focus {{
      border-color: var(--p-color-border-focus, #458fff);
      box-shadow: 0 0 0 3px rgba(69,143,255,.25);
    }}

    .select-wrap {{ position: relative; }}
    .select-wrap::after {{
      content: "";
      position: absolute;
      right: 12px; top: 50%;
      transform: translateY(-50%);
      width: 0; height: 0;
      border-left: 4px solid transparent;
      border-right: 4px solid transparent;
      border-top: 5px solid var(--p-color-icon, #5c5f62);
      pointer-events: none;
    }}
    .select {{
      display: block;
      width: 100%;
      padding: 8px 36px 8px 12px;
      font-size: 14px;
      font-family: inherit;
      color: var(--p-color-text, #202223);
      background: var(--p-color-bg-surface, #ffffff);
      border: 1px solid var(--p-color-border-input, #8c9196);
      border-radius: 6px;
      -webkit-appearance: none;
      appearance: none;
      outline: none;
      cursor: pointer;
      transition: border-color .15s, box-shadow .15s;
    }}
    .select:focus {{
      border-color: var(--p-color-border-focus, #458fff);
      box-shadow: 0 0 0 3px rgba(69,143,255,.25);
    }}

    .divider {{
      border: none;
      border-top: 1px solid var(--p-color-border, #e1e3e5);
    }}

    /*
     * PRIMARY BUTTON
     * Token is the primary value. Fallback rgba() values are copied
     * directly from Shopify admin DevTools computed styles on the
     * native 'Create discount' primary button (Spring '26 admin).
     * This means: token wins when injected, fallback is pixel-perfect
     * Shopify-sourced — never our own invented color.
     */
    .btn-primary {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 8px 16px;
      font-size: 14px;
      font-weight: var(--p-font-weight-medium, 500);
      font-family: inherit;
      color: var(--p-color-text-brand-on-bg-fill, rgba(255,255,255,1));
      background: var(--p-color-bg-fill-brand, rgba(48,48,48,1));
      border: none;
      border-radius: var(--p-border-radius-200, 6px);
      cursor: pointer;
      min-height: 36px;
      transition: filter .15s;
    }}
    .btn-primary:hover  {{ filter: brightness(0.88); }}
    .btn-primary:active {{ filter: brightness(0.80); }}
    .btn-primary:focus-visible {{
      outline: 3px solid var(--p-color-border-focus, #458fff);
      outline-offset: 2px;
    }}
    .btn-primary:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
    }}

    .footer {{
      margin-top: 24px;
      font-size: 13px;
      color: var(--p-color-text-secondary, #6d7175);
    }}
    .footer a {{
      color: var(--p-color-text-link, #2c6ecb);
      text-decoration: none;
    }}
    .footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <main class="page" id="main-content">

    <h1 class="page-title">Visual Crossing Weather</h1>
    <p class="page-subtitle">
      Configure your Visual Crossing API key and display
      defaults for <strong>{safe_shop}</strong>.
    </p>

    {banner_html}

    <div class="layout">

      <div class="annotation">
        <p class="annotation-title">API credentials</p>
        <p class="annotation-desc">
          Enter your free Visual Crossing API key.
          The key is encrypted before storage and never
          exposed to storefront visitors.
        </p>
      </div>

      <div class="card">
        <form method="POST" action="/shopify/home" id="settings-form">
          <input type="hidden" name="shop"          value="{safe_shop}">
          <input type="hidden" name="session_token" id="session_token" value="">

          <div class="form-stack">

            <div class="field-group">
              <label class="field-label" for="vc_key">
                Visual Crossing API Key
              </label>
              <input
                id="vc_key"
                class="input"
                type="text"
                name="vc_key"
                placeholder="Paste your API key (leave blank to keep current)"
                autocomplete="off"
                spellcheck="false"
              >
              {key_status_html}
            </div>

            <hr class="divider">

            <div class="field-group">
              <label class="field-label" for="home_location">
                Default Location
              </label>
              <input
                id="home_location"
                class="input"
                type="text"
                name="home_location"
                value="{safe_home_location}"
                placeholder="e.g. London, UK or 10001"
              >
              <p class="hint">Used when a theme block has no location setting.</p>
            </div>

            <div class="field-group">
              <label class="field-label" for="unit_system">
                Unit System
              </label>
              <div class="select-wrap">
                <select id="unit_system" class="select" name="unit_system">
                  <option value="metric" {unit_metric}>Metric (&#176;C, km/h)</option>
                  <option value="us"     {unit_us}>US (&#176;F, mph)</option>
                </select>
              </div>
            </div>

            <div>
              <button type="submit" class="btn-primary" id="save-btn" disabled>
                Save settings
              </button>
            </div>

          </div>
        </form>
      </div>

    </div>

    <footer class="footer">
      Visual Crossing Weather API &mdash;
      <a href="https://www.visualcrossing.com/weather-api"
         target="_blank" rel="noopener noreferrer">Documentation</a>
      &nbsp;|&nbsp;
      <a href="https://www.visualcrossing.com/weather-data-editions/"
         target="_blank" rel="noopener noreferrer">Get a free API key</a>
    </footer>

  </main>

  <script>
    /*
     * Token strategy
     * --------------
     * We do NOT store the token in a variable and reuse it.
     * Shopify session tokens expire in ~60 seconds, so we call
     * window.shopify.idToken() fresh on every form submit.
     * This guarantees the POST always carries a valid token
     * regardless of how long the merchant spends on the page.
     */
    (async function () {{
      const form    = document.getElementById('settings-form');
      const saveBtn = document.getElementById('save-btn');

      try {{
        // Verify App Bridge is present (we are in embedded context)
        await window.shopify.idToken();
        saveBtn.disabled = false;
      }} catch (e) {{
        console.debug('[VC Weather] App Bridge not available:', e.message);
        saveBtn.disabled  = true;
        saveBtn.textContent = 'Reload from Shopify admin to save';
        return;
      }}

      form.addEventListener('submit', async function (ev) {{
        ev.preventDefault();
        saveBtn.disabled     = true;
        saveBtn.textContent  = 'Saving\u2026';

        try {{
          // Always fetch a FRESH token at submit time
          const freshToken = await window.shopify.idToken();
          document.getElementById('session_token').value = freshToken;
        }} catch (e) {{
          console.error('[VC Weather] Could not obtain session token:', e);
          saveBtn.disabled    = false;
          saveBtn.textContent = 'Save settings';
          alert('Authentication error. Please reload from Shopify admin.');
          return;
        }}

        form.submit();
      }});
    }})();
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# FastAPI route handlers
# ---------------------------------------------------------------------------

def _csp_response(html_content: str, status_code: int = 200) -> HTMLResponse:
    """Return an HTMLResponse with the required frame-ancestors CSP header."""
    response = HTMLResponse(content=html_content, status_code=status_code)
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors https://*.myshopify.com https://admin.shopify.com"
    )
    return response


@router.get("/home", response_class=HTMLResponse)
async def admin_home(request: Request):
    """
    Two-phase GET handler.

    Phase 1 (no Authorization header):
        Return the thin bootstrap shell.  Safe to serve without auth
        because it contains no shop data — just App Bridge + a JS
        snippet that obtains a token and re-fetches this same URL.

    Phase 2 (Authorization: Bearer <token> present):
        Verify the JWT. On success return the full settings UI.
        On failure return 401 — the JS bootstrap shell shows an error.
    """
    shop_domain = request.query_params.get("shop", "")
    if not shop_domain:
        return HTMLResponse("<h2>Missing shop parameter.</h2>", status_code=400)

    auth_header = request.headers.get("Authorization", "")

    # Phase 1 — no token yet, serve the bootstrap shell
    if not auth_header.startswith("Bearer "):
        return _csp_response(_bootstrap_shell(shop_domain))

    # Phase 2 — verify token; hard-fail on any error (no silent degradation)
    token = auth_header[len("Bearer "):]
    try:
        await _verify_session_token(token, shop_domain)
    except HTTPException as exc:
        logger.warning("GET /home session-token rejection for %s: %s", shop_domain, exc.detail)
        return _csp_response(
            f"<h2 style='font-family:sans-serif;padding:2rem'>"
            f"Authentication failed: {_e(exc.detail)}</h2>",
            status_code=401,
        )

    shop = await get_shop(shop_domain)
    if not shop:
        return RedirectResponse(
            f"{settings.APP_URL}/shopify/install?shop={shop_domain}"
        )

    raw = shop.get("encrypted_vc_key")
    try:
        masked_key = mask(decrypt(raw)) if raw else ""
    except Exception:
        masked_key = ""

    home_location = shop.get("home_location") or ""
    unit_system   = shop.get("unit_system") or "metric"

    return _csp_response(
        _render_home(shop_domain, masked_key, home_location, unit_system)
    )


@router.post("/home", response_class=HTMLResponse)
async def admin_home_post(
    request:       Request,
    shop:          str = Form(...),
    vc_key:        str = Form(default=""),
    home_location: str = Form(default=""),
    unit_system:   str = Form(default="metric"),
    session_token: str = Form(default=""),
):
    """
    POST handler — saves settings.

    Requires a valid App Bridge session token in the session_token
    form field (populated fresh at submit time by the JS above).
    Rejects without touching the database on missing or invalid token.
    """
    # 1. Token must be present
    if not session_token:
        return _csp_response(
            _render_home(
                shop, "", home_location, unit_system,
                error="Authentication required. Please reload the page from Shopify admin.",
            ),
            status_code=403,
        )

    # 2. Token must be valid
    try:
        await _verify_session_token(session_token, shop)
    except HTTPException as exc:
        logger.warning("POST /home session-token rejection for %s: %s", shop, exc.detail)
        return _csp_response(
            _render_home(
                shop, "", home_location, unit_system,
                error=f"Authentication failed: {exc.detail}",
            ),
            status_code=403,
        )

    # 3. Validate unit_system to a known safe value
    if unit_system not in ("metric", "us"):
        unit_system = "metric"

    # 4. Persist — only write vc_key if a new one was supplied
    if vc_key.strip():
        await save_vc_key(shop, vc_key.strip())

    await save_settings(shop, home_location.strip(), unit_system)
    logger.info("Settings updated for %s", shop)

    # 5. Re-read masked key to show current state after save
    shop_data = await get_shop(shop)
    raw = shop_data.get("encrypted_vc_key") if shop_data else None
    try:
        masked_key = mask(decrypt(raw)) if raw else ""
    except Exception:
        masked_key = ""

    return _csp_response(
        _render_home(shop, masked_key, home_location.strip(), unit_system, saved=True)
    )
