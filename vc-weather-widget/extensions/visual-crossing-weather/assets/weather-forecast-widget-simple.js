(function () {
  "use strict";

  var GENERIC_ERROR = "Weather unavailable right now.";

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function isSetupStatus(status) {
    // These mean the merchant hasn't finished configuring the app — not something
    // a shopper can do anything about, so we hide the widget for them entirely
    // rather than showing setup instructions on a live storefront.
    return status === 401 || status === 403 || status === 422;
  }

  function iconSvg(conditions) {
    var c = (conditions || "").toLowerCase();
    if (c.indexOf("snow") >= 0 || c.indexOf("blizzard") >= 0)
      return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40"><path d="M10 24 Q6 24 6 20 Q6 16 10.5 16 Q11 11.5 16 11.5 Q21 11.5 22.5 16 Q26.5 16 27 20 Q27.5 24 23 24 Z" fill="#c8dce8"/><g fill="#9ec9e8"><circle cx="13" cy="29" r="1.5"/><circle cx="18" cy="32" r="1.5"/><circle cx="23" cy="29" r="1.5"/></g></svg>';
    if (c.indexOf("rain") >= 0 || c.indexOf("drizzle") >= 0 || c.indexOf("shower") >= 0)
      return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40"><path d="M10 24 Q6 24 6 20 Q6 16 10.5 16 Q11 11.5 16 11.5 Q21 11.5 22.5 16 Q26.5 16 27 20 Q27.5 24 23 24 Z" fill="#aac5d9"/><g stroke="#5ba3e0" stroke-width="2" stroke-linecap="round"><line x1="13" y1="27" x2="11" y2="32"/><line x1="18" y1="27" x2="16" y2="32"/><line x1="23" y1="27" x2="21" y2="32"/></g></svg>';
    if (c.indexOf("overcast") >= 0)
      return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40"><path d="M10 28 Q6 28 6 23.5 Q6 19 10.5 19 Q11 14 16 14 Q21 14 22.5 18.5 Q26.5 18.5 27 23 Q27.5 28 23 28 Z" fill="#c8dce8"/></svg>';
    if (c.indexOf("cloudy") >= 0 || c.indexOf("partly") >= 0)
      return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40"><circle cx="16" cy="18" r="6" fill="#FFD700"/><g stroke="#FFD700" stroke-width="2" stroke-linecap="round"><line x1="16" y1="6" x2="16" y2="9"/><line x1="6" y1="18" x2="9" y2="18"/><line x1="8.5" y1="10.5" x2="10.6" y2="12.6"/><line x1="23.5" y1="10.5" x2="21.4" y2="12.6"/></g><path d="M14 27 Q10 27 10 23 Q10 19 14 19 Q14.5 15.5 18 15.5 Q22 15.5 23 19 Q26 19 26 23 Q26 27 22 27 Z" fill="#e0edf7"/></svg>';
    return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40"><circle cx="20" cy="20" r="8" fill="#FFD700"/><g stroke="#FFD700" stroke-width="2.5" stroke-linecap="round"><line x1="20" y1="4" x2="20" y2="8"/><line x1="20" y1="32" x2="20" y2="36"/><line x1="4" y1="20" x2="8" y2="20"/><line x1="32" y1="20" x2="36" y2="20"/><line x1="7.9" y1="7.9" x2="10.8" y2="10.8"/><line x1="29.2" y1="29.2" x2="32.1" y2="32.1"/><line x1="32.1" y1="7.9" x2="29.2" y2="10.8"/><line x1="10.8" y1="29.2" x2="7.9" y2="32.1"/></g></svg>';
  }

  function friendlyError(status, detail) {
    var d = (detail || "").toLowerCase();
    if (status === 401) return "Weather app not installed. Please install from the Shopify App Store.";
    if (status === 403) {
      if (d.indexOf("invalid") >= 0 || d.indexOf("expired") >= 0)
        return "Your Visual Crossing API key is invalid or expired.";
      return "No Visual Crossing API key configured \u2014 please open the app settings.";
    }
    if (status === 422) return "No location set \u2014 please add a location in the widget or app settings.";
    if (status === 429) return "Too many requests \u2014 please wait a moment and refresh.";
    if (status >= 500) return "Weather service temporarily unavailable \u2014 please try again shortly.";
    return detail || "Could not load weather data.";
  }

  function formatDay(date) {
    return ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][date.getDay()];
  }

  function renderWidget(el, data, config) {
    var tu   = config.unitGroup === "us" ? "F" : "C";
    var days = (data.days || []).filter(function (d) { return d.temp != null; });
    if (!days.length) return;

    var today  = days[0];
    var offset = new Date().getTimezoneOffset() * 60000;

    // Day cards: label + icon + plain number (no unit) in red — matches original exactly
    var dayCards = days.map(function (d, i) {
      var dt  = new Date(new Date(d.datetime).getTime() + offset);
      var lbl = i === 0 ? "Today" : formatDay(dt);
      var temp = Math.round(d.tempmax != null ? d.tempmax : d.temp);
      return "<div class='vcw-day" + (i === 0 ? " vcw-day-today" : "") + "'>" +
        "<div class='vcw-day-date'>" + lbl + "</div>" +
        "<div class='vcw-day-icon'>" + iconSvg(d.conditions) + "</div>" +
        "<div class='vcw-day-temp'>" + temp + "</div>" +
        "</div>";
    }).join("");

    var title = (config.showTitle && config.title)
      ? "<div class='vcw-title'>" + escapeHtml(config.title) + "</div>"
      : "";

    // Current panel: icon and temp side-by-side on same row (horizontal, not stacked)
    // Shows: [icon] [temp+unit] — e.g. ☀ 23C
    el.innerHTML =
      title +
      "<div class='vcw-body'>" +
        "<div class='vcw-current'>" +
          "<div class='vcw-current-icon'>" + iconSvg(today.conditions) + "</div>" +
          "<div class='vcw-current-temp'>" + Math.round(today.temp) + tu + "</div>" +
        "</div>" +
        "<div class='vcw-forecast'>" + dayCards + "</div>" +
      "</div>" +
      "<div class='vcw-credit'><a href='https://www.visualcrossing.com/weather-api' target='_blank' rel='noopener'>Visual Crossing Weather</a></div>";
  }

  function loadWidget(config) {
    // The theme can render this app block more than once on a page, and each
    // instance's own <script src> tag re-executes this whole file, re-processing
    // every entry in window.weatherWidgetConfig — including ones already loaded
    // by an earlier execution. Guard against that here.
    if (config._vcwLoaded) return;
    config._vcwLoaded = true;

    var el = document.querySelector(config.selector);
    if (!el) { console.warn("[VC Weather Simple] selector not found:", config.selector); return; }

    el.classList.add("vcw-simple");
    el.innerHTML = "<div class='vcw-loading'>Loading weather\u2026</div>";

    var designMode = !!config.designMode;

    function showError(message, isSetupIssue) {
      if (!designMode && isSetupIssue) {
        // Merchant hasn't finished setup — don't show that to shoppers, just hide it.
        el.style.display = "none";
        el.innerHTML = "";
        return;
      }
      el.innerHTML = "<div class='vcw-error'>" + escapeHtml(designMode ? message : GENERIC_ERROR) + "</div>";
    }

    var backendUrl = (config.backendUrl || "https://apps.visualcrossing.com").replace(/\/$/, "");
    var params = new URLSearchParams({
      shop:     config.shop || "",
      location: config.location || "_auto_",
      days:     config.forecastDays || 7,
      units:    config.unitGroup || "metric",
      include:  "days"
    });

    var xhr = new XMLHttpRequest();
    xhr.open("GET", backendUrl + "/shopify/weather?" + params.toString());
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        var json;
        try { json = JSON.parse(xhr.responseText); } catch (e) {
          showError("Invalid response from weather service.", false);
          return;
        }
        if (json.error) {
          showError(json.error, false);
        } else {
          renderWidget(el, json, config);
        }
      } else {
        var detail = "";
        try { detail = JSON.parse(xhr.responseText).detail || ""; } catch (e) {}
        showError(friendlyError(xhr.status, detail), isSetupStatus(xhr.status));
      }
    };
    xhr.onerror = function () {
      showError("Could not connect to weather service.", false);
    };
    xhr.send();
  }

  if (!window.weatherWidgetConfig) {
    console.warn("[VC Weather Simple] No widget configuration found.");
  } else {
    window.weatherWidgetConfig.forEach(function (cfg) { loadWidget(cfg); });
  }
}());
