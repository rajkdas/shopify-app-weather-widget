# Visual Crossing Weather Shopify App

A Shopify app and theme app extension for displaying Visual Crossing weather forecasts on storefront pages.

## Theme app extension assets

The storefront widget uses a Shopify theme app extension with the following assets:

- `weather-forecast.css`
- `weather-forecast-widget-simple.js`
- `weather-forecast-widget-d3.js`
- `d3.min.js`
- `blocks/weather-forecast.liquid`

## D3 mode loading policy

To keep storefront performance tighter and reduce unnecessary JavaScript execution, the D3 library and D3 widget script should load **only** when the merchant selects `mode == 'd3'` in the block settings. The simple widget should load only its own lightweight script.

Recommended Liquid pattern:

```liquid
{{ 'weather-forecast.css' | asset_url | stylesheet_tag }}

{%- if mode == 'd3' -%}
  <script src="{{ 'd3.min.js' | asset_url }}" defer></script>
  <script src="{{ 'weather-forecast-widget-d3.js' | asset_url }}" defer></script>
{%- else -%}
  <script src="{{ 'weather-forecast-widget-simple.js' | asset_url }}" defer></script>
{%- endif -%}
```

This ensures that:

- D3 is not downloaded for the simple widget mode.
- The simple widget avoids the extra D3 payload.
- The D3 widget remains self-contained inside the theme app extension.
- No third-party CDN dependency is required for storefront rendering.

## Open-source notice

This project includes a local copy of D3.js for the animated chart mode.

- Library: D3.js
- Website: https://d3js.org/
- Repository: https://github.com/d3/d3
- License: ISC

D3.js is licensed under the ISC License. If this repository distributes a bundled copy of `d3.min.js`, the original copyright and license notice for the included D3 version should be preserved in project notices or distribution materials.

## Submission and review notes

For Shopify App Store review, the important storefront checks are:

- The widget loads only the assets required for the selected mode.
- The storefront never exposes the raw Visual Crossing API key.
- The widget fails gracefully when no location or API key is configured.
- The extension does not rely on external CDN scripts to function.
- The widget renders without console errors on supported Shopify themes.

## GDPR webhook validation

The app also implements the required Shopify compliance webhooks:

- `customers/data_request`
- `customers/redact`
- `shop/redact`

These should return:

- `2xx` for valid HMAC-signed requests
- `401` for invalid HMAC signatures
- `401` for missing HMAC headers