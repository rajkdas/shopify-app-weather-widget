# Visual Crossing Weather — Full-Stack Shopify App & OS 2.0 Theme Extension

[![Shopify API](https://img.shields.io/badge/Shopify%20API-2026--07-blue.svg)](https://shopify.dev/docs/api)
[![Online Store 2.0](https://img.shields.io/badge/Online%20Store%202.0-App%20Blocks-success.svg)](https://shopify.dev/docs/apps/online-store/theme-app-extensions)
[![Backend Framework](https://img.shields.io/badge/Backend-FastAPI%20%2F%20Uvicorn-009688.svg)](https://fastapi.tiangolo.com/)
[![Database](https://img.shields.io/badge/Database-SQLite%20(aiosqlite)-003B57.svg)](https://github.com/omnilib/aiosqlite)
[![Security](https://img.shields.io/badge/Security-Fernet%20Encryption-critical.svg)](https://cryptography.io/)
[![Visualization](https://img.shields.io/badge/D3.js-v4%2B%20(Self--Contained)-F9A03C.svg)](https://d3js.org/)

An enterprise-ready, full-stack Shopify application and Online Store 2.0 Theme App Extension delivering real-time meteorological conditions and multi-day forecasts.

Engineered to satisfy strict Shopify App Store review standards, this repository pairs an asynchronous Python backend proxy with a decoupled, zero-theme-code frontend extension. The architecture ensures zero core theme pollution, complete API key protection via authenticated backend proxying, conditional frontend bundle execution, and full GDPR compliance webhook coverage.

---

## 🏛️ System Architecture

~~~text
┌────────────────────────────────────────────────────────────────────────┐
│                          SHOPIFY STOREFRONT                            │
│                                                                        │
│   Theme App Block (blocks/weather-forecast.liquid)                     │
│   ├── Simple Mode  ──> weather-forecast-widget-simple.js (~3KB)        │
│   └── D3 Mode      ──> d3.min.js + weather-forecast-widget-d3.js       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Public GET Request
                                    │ (?shop=...&location=...&units=...)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND PROXY                           │
│                      (vc-weather-backend/main.py)                      │
│                                                                        │
│   ├── SecurityHeadersMiddleware                                        │
│   │   └── nosniff, Referrer-Policy, restrictive Permissions-Policy     │
│   ├── WeatherCORSMiddleware                                            │
│   │   └── Public wildcard (*) access strictly for /shopify/weather     │
│   ├── CORSMiddleware                                                   │
│   │   └── Origin-locked to admin.shopify.com & registered app domain   │
│   │                                                                    │
│   ├── SQLite Storage (aiosqlite + shops table)                         │
│   │   └── Fernet-encrypted Visual Crossing API keys stored at rest     │
│   │                                                                    │
│   └── Outbound Service Client (services/visualcrossing.py)             │
│       └── Decrypts merchant key & routes timeline query server-side    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Authenticated Outbound Request
                                    │ (API key attached server-side)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              					                         │
└────────────────────────────────────────────────────────────────────────┘
~~~

---

## ⚡ Technical Highlights

### 1. Storefront Security & API Proxy Pattern
* **Zero Credential Exposure:** Raw Visual Crossing API keys are never rendered in Liquid markup or transmitted in client-side bundles.
* **Encrypted Storage at Rest:** Merchant API keys are stored as symmetric `cryptography.fernet` tokens in the SQLite database (`shops` table). The backend service queries the database asynchronously via `aiosqlite`, decrypts the merchant token in-memory, and proxies the query to the upstream Timeline API.
* **Storefront Identity:** Requests validate the calling merchant via Shopify's permanent domain (`shop.permanent_domain`).

### 2. Dual-Layer CORS Strategy & Compliance Middleware
* **Public Storefront Proxy (`WeatherCORSMiddleware`):** The `/shopify/weather` endpoint accepts cross-origin GET and OPTIONS preflights from any merchant domain (`*`) with a `600s` `Access-Control-Max-Age` cache.
* **Admin Origin Lock (`CORSMiddleware`):** Embedded admin and authentication routes (`/shopify/auth`, `/shopify/admin`) are restricted strictly to `https://admin.shopify.com` and the verified application domain.
* **Hardened Security Headers (`SecurityHeadersMiddleware`):** Injects production-grade headers across every response:
  * `X-Content-Type-Options: nosniff`
  * `X-XSS-Protection: 0`
  * `Referrer-Policy: strict-origin-when-cross-origin`
  * `Permissions-Policy: geolocation=(), microphone=(), camera=()`

### 3. Conditional Frontend Bundling & Performance
* **Zero Unnecessary JavaScript:** Liquid templates evaluate merchant block settings prior to loading scripts:
  * **Simple Mode:** Loads only `weather-forecast-widget-simple.js` (~3KB) and component CSS.
  * **D3 Mode:** Conditionally defers execution of vendor `d3.min.js` and charting logic (`weather-forecast-widget-d3.js`) strictly when animated visual charts are active.
* **Zero External CDN Dependencies:** The D3 runtime is self-contained in `/assets`, eliminating third-party latency, blocking scripts, and Content Security Policy conflicts.

### 4. DOM Isolation & Resilient Lifecycle Management
* **Collision-Free SVG Defs:** D3 chart instances dynamically derive unique identifiers (`uidFromSelector`) from Shopify block IDs (`vc-weather-{{ block.id }}`), preventing collisions across `<clipPath>` and `<linearGradient>` definitions.
* **Re-Execution Guard:** Both client scripts use an execution lock (`_vcwLoaded`) to prevent duplicate initialization when theme sections dynamically re-render.
* **Silent Merchant Configuration Fallback:** Stores lacking configured API keys or location parameters (HTTP `401`, `403`, `422`) hide the widget cleanly (`display: none`) on live storefronts, while presenting diagnostic configuration guidance inside the Shopify Theme Editor (`request.design_mode`).

---

## 📊 Dual Display Engines

| Feature | Simple Mode (`weather-forecast-widget-simple.js`) | D3 Mode (`weather-forecast-widget-d3.js`) |
| :--- | :--- | :--- |
| **Payload Size** | Minimal footprint (~3KB JS + CSS) | Full visualization engine (Local D3 bundle) |
| **View Modes** | Static multi-day forecast grid (1–15 days) | Interactive Daily and Hourly switching |
| **Visuals** | Clean vector SVG status icons | Catmull-Rom temperature curves with Turbo color gradient stops |
| **Precipitation** | Daily condition metrics | Dynamic precipitation bar chart with dedicated secondary Y-axis |
| **Interactivity** | Fluid responsive flex layout | Pan/zoom boundaries (`d3.zoom`) and inline location selector |
| **Responsiveness** | Pure CSS grid / flexbox | Re-renders dynamically via `ResizeObserver` |

---

## 📂 Repository Layout

~~~text
shopify-app-vc-weather/
├── .gitignore                                 # Git exclusion rules (.env, *.db, venv, node_modules)
├── README.md                                  # Architecture and setup documentation
│
├── vc-weather-backend/                        # Asynchronous Python FastAPI Backend
│   ├── services/
│   │   ├── __init__.py
│   │   └── visualcrossing.py                  # Upstream Visual Crossing Timeline API client
│   ├── shopify_app/
│   │   ├── __init__.py
│   │   ├── crud.py                            # Async database CRUD operations
│   │   ├── models.py                          # SQLite database schema, triggers & lifespan init
│   │   ├── routes_admin.py                    # Embedded merchant admin dashboard
│   │   ├── routes_auth.py                     # Shopify OAuth handshake & token exchange
│   │   ├── routes_weather.py                  # Public storefront weather proxy route
│   │   └── routes_webhooks.py                 # Mandatory Shopify GDPR compliance webhooks
│   ├── config.py                              # Typed settings loaded from .env
│   ├── main.py                                # ASGI app entry point, middlewares & route mounting
│   ├── Procfile                               # Process runner for deployment
│   ├── requirements.txt                       # Backend Python dependencies
│   ├── vc-weather-backend.service             # Linux systemd production service definition
│   └── .env.example                           # Template environment variables
│
└── vc-weather-widget/                         # Shopify App CLI & Theme App Extension
    ├── extensions/
    │   └── visual-crossing-weather/
    │       ├── assets/
    │       │   ├── d3.min.js                  # Standalone D3.js runtime (ISC License)
    │       │   ├── weather-forecast-widget-d3.js      # Advanced D3 interactive charting engine
    │       │   ├── weather-forecast-widget-simple.js  # Featherweight standard widget renderer
    │       │   └── weather-forecast.css       # Unified storefront component styling
    │       ├── blocks/
    │       │   └── weather-forecast.liquid    # OS 2.0 App Block schema & conditional asset loader
    │       ├── locales/
    │       │   └── en.default.json            # Theme Editor internationalization dictionary
    │       └── shopify.extension.toml         # Extension target registration & handle
    ├── package.json                           # NPM workspace configuration & CLI scripts
    ├── package-lock.json                      # Deterministic lockfile
    ├── shopify.app.toml                       # Shopify App manifest & webhook subscriptions
    └── SECURITY.md                            # Responsible vulnerability disclosure policy
~~~

---

## ⚙️ Configuration Reference

### Storefront App Block Settings (`blocks/weather-forecast.liquid`)

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `location` | `text` | `""` | Target city, postal code, or `lat,lng`. Falls back to backend default if empty. |
| `mode` | `select` | `"simple"` | Toggle between `"simple"` (lightweight) or `"d3"` (animated interactive chart). |
| `forecast_days`| `range` | `7` | Configurable timeframe spanning 1 to 15 forecast days. |
| `unit_group` | `select` | `"metric"` | Unit system: Metric (`°C, km/h`) or US Customary (`°F, mph`). |
| `widget_title` | `text` | `""` | Optional display heading; defaults to resolved geographic address when blank. |
| `show_title` | `checkbox`| `true` | Show or hide the top header element. |

### Backend Environment Configuration (`vc-weather-backend/.env`)

~~~env
SHOPIFY_API_KEY=your_shopify_api_key_here
SHOPIFY_API_SECRET=your_shopify_api_secret_here
ENCRYPTION_KEY=your_fernet_32_byte_key_here
DATABASE_URL=vc_shopify.db
PORT=8000
DEBUG=false
APP_URL=https://apps.visualcrossing.com
~~~

---

## 🔒 Mandatory GDPR Compliance Webhooks

In compliance with Shopify Partner Program specifications (API Version `2026-07`), the backend verifies incoming HMAC SHA-256 signatures for mandatory compliance topics:

* **`customers/data_request`**: Retrieves customer-specific data logs associated with a shop.
* **`customers/redact`**: Purges cached customer profile identifiers.
* **`shop/redact`**: Executes a 48-hour data purging sequence upon app uninstallation.

Requests with invalid or missing HMAC headers return immediate `401 Unauthorized` responses.

---

## 🚀 Setup & Local Development

### 1. Backend Service (`vc-weather-backend`)

~~~bash
cd vc-weather-backend

# Initialize and activate Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
copy .env.example .env

# Run FastAPI development server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
~~~

### 2. Shopify Extension Workspace (`vc-weather-widget`)

~~~bash
cd ../vc-weather-widget

# Install CLI dependencies
npm install

# Authenticate with Shopify Partner account
npm run shopify login

# Start local tunnel and preview on your development store
npm run dev

# Deploy extension updates
npm run deploy
~~~

---

## 📜 Licensing & Attributions

* **Application Logic & Extension:** Custom implementation for Visual Crossing Weather.
* **Data Visualization Library:** [D3.js](https://d3js.org/) (licensed under the ISC License).