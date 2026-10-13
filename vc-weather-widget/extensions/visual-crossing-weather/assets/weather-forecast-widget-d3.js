var WeatherForecastDisplay = (function () {
  "use strict";

  var GENERIC_ERROR = "Weather unavailable right now.";

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function isSetupStatus(status) {
    // Merchant-configuration problems — nothing a shopper can act on, so these
    // stay hidden on a live storefront and only show in the theme editor.
    return status === 401 || status === 403 || status === 422;
  }

  // Derive a DOM-safe id fragment from the block's own selector (already
  // globally unique per block instance) so multiple widgets on one page never
  // collide on a shared <clipPath>/<linearGradient> id.
  function uidFromSelector(selector) {
    var clean = String(selector || "").replace(/[^a-zA-Z0-9_-]/g, "");
    return clean || ("vcw" + Math.random().toString(36).slice(2));
  }

  // The location-editor "click outside to close" behavior used to be bound
  // per-instance on document.body with a shared ".vcw" namespace, so each new
  // widget on the page silently replaced the previous one's handler. Bind it
  // once, globally, and let it close whichever instance is open.
  function ensureBodyClickHandler() {
    if (window.__vcwBodyClickBound) return;
    window.__vcwBodyClickBound = true;
    document.addEventListener("click", function () {
      document.querySelectorAll(".location.edit").forEach(function (el) {
        el.classList.remove("edit");
      });
    });
  }

  function WeatherForecastWidget(initConfig) {
    this.rawSelector = initConfig.selector;
    this.backendUrl  = (initConfig.backendUrl || "https://apps.visualcrossing.com").replace(/\/$/, "");
    this.shop        = initConfig.shop || "";
    this.uid         = uidFromSelector(initConfig.selector);
    this.designMode  = !!initConfig.designMode;
    this.error       = null;
    this.errorIsSetupIssue = false;
    var me = this;

    this.config = {
      location:     initConfig.location    || "",
      unitGroup:    initConfig.unitGroup   || "metric",
      forecastDays: initConfig.forecastDays || 15,
      hourly:       false,
      title:        initConfig.title       || "",
      showTitle:    !!initConfig.showTitle
    };

    this.dailydata  = null;
    this.hourlydata = null;

    this._buildUrl = function (hourly) {
      var params = new URLSearchParams({
        shop:     me.shop,
        location: me.config.location || "_auto_",
        days:     me.config.forecastDays,
        units:    me.config.unitGroup,
        include:  hourly ? "hours" : "days"
      });
      return me.backendUrl + "/shopify/weather?" + params.toString();
    };

    this.setLocation = function (location) {
      me.config.location = location || "";
      me.dailydata  = null;
      me.hourlydata = null;
      me.loadForecastData();
    };

    this._friendlyError = function (status, detail) {
      var d = (detail || "").toLowerCase();
      if (status === 401) return "Weather app not installed. Please install it from the Shopify App Store.";
      if (status === 403) {
        if (d.indexOf("invalid") >= 0 || d.indexOf("expired") >= 0)
          return "Your Visual Crossing API key is invalid or expired \u2014 please update it in the app settings.";
        return "No Visual Crossing API key configured \u2014 please open the app settings to add one.";
      }
      if (status === 422) return "No location set \u2014 please add a location in the widget settings or app settings.";
      if (status === 429) return "Too many requests \u2014 please wait a moment and refresh the page.";
      if (status >= 500) return "Weather service temporarily unavailable \u2014 please try again shortly.";
      return detail || "Could not load weather data.";
    };

    this.loadForecastData = function () {
      if (me.error) return;
      var alreadyLoaded = me.config.hourly ? me.hourlydata : me.dailydata;
      if (alreadyLoaded) { me.refresh(); return; }

      d3.json(me._buildUrl(me.config.hourly), function (err, rawResult) {
        if (err) {
          var status = err.target ? err.target.status : (err.status || 0);
          var detail = "";
          try {
            var body = JSON.parse(err.target ? err.target.responseText : (err.responseText || ""));
            detail = body.detail || "";
          } catch (e) {}
          me.error = status === 0
            ? "Could not connect to weather service \u2014 please check your connection."
            : me._friendlyError(status, detail);
          me.errorIsSetupIssue = isSetupStatus(status);
          console.error("[VC Weather D3] HTTP " + status + ":", detail || err);
        } else if (!rawResult || rawResult.error) {
          me.error = rawResult && rawResult.error ? rawResult.error : "Empty response from weather service.";
          me.errorIsSetupIssue = false;
          console.error("[VC Weather D3] bad response:", rawResult);
        } else {
          me._processValues(rawResult);
          if (me.config.hourly) me.hourlydata = rawResult;
          else me.dailydata = rawResult;
        }
        me.refresh();
      });
    };

    this._getForecastValues = function (data) {
      if (!data) return null;
      if (me.config.hourly) {
        var hours = [];
        (data.days || []).forEach(function (day) {
          (day.hours || []).forEach(function (h) {
            h._date = day.datetime;
            h._isoDatetime = day.datetime + "T" + h.datetime;
            hours.push(h);
          });
        });
        return hours.filter(function (h) { return h.temp != null; });
      }
      return (data.days || []).filter(function (d) { return d.temp != null; });
    };

    this._processValues = function (data) {
      var values = me._getForecastValues(data);
      if (!values) return;
      var offset = new Date().getTimezoneOffset() * 60000;
      values.forEach(function (d) {
        if (d.datetime instanceof Date) return;
        if (me.config.hourly) {
          d.datetime = new Date(d._isoDatetime);
        } else {
          d.datetime = new Date(new Date(d.datetime).getTime() + offset);
        }
      });
    };

    // ── SVG weather icons ───────────────────────────────────────
    this._iconSvg = function (conditions) {
      var c = (conditions || "").toLowerCase();
      if (c.indexOf("snow") >= 0 || c.indexOf("blizzard") >= 0)
        return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40" class="vcw-svg-icon"><path d="M10 24 Q6 24 6 20 Q6 16 10.5 16 Q11 11.5 16 11.5 Q21 11.5 22.5 16 Q26.5 16 27 20 Q27.5 24 23 24 Z" fill="#c8dce8"/><g fill="#9ec9e8"><circle cx="13" cy="29" r="1.5"/><circle cx="18" cy="32" r="1.5"/><circle cx="23" cy="29" r="1.5"/></g></svg>';
      if (c.indexOf("rain") >= 0 || c.indexOf("drizzle") >= 0 || c.indexOf("shower") >= 0)
        return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40" class="vcw-svg-icon"><path d="M10 24 Q6 24 6 20 Q6 16 10.5 16 Q11 11.5 16 11.5 Q21 11.5 22.5 16 Q26.5 16 27 20 Q27.5 24 23 24 Z" fill="#aac5d9"/><g stroke="#5ba3e0" stroke-width="2" stroke-linecap="round"><line x1="13" y1="27" x2="11" y2="32"/><line x1="18" y1="27" x2="16" y2="32"/><line x1="23" y1="27" x2="21" y2="32"/></g></svg>';
      if (c.indexOf("overcast") >= 0)
        return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40" class="vcw-svg-icon"><path d="M10 28 Q6 28 6 23.5 Q6 19 10.5 19 Q11 14 16 14 Q21 14 22.5 18.5 Q26.5 18.5 27 23 Q27.5 28 23 28 Z" fill="#c8dce8"/></svg>';
      if (c.indexOf("cloudy") >= 0 || c.indexOf("partly") >= 0)
        return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40" class="vcw-svg-icon"><circle cx="16" cy="18" r="6" fill="#FFD700"/><g stroke="#FFD700" stroke-width="2" stroke-linecap="round"><line x1="16" y1="6" x2="16" y2="9"/><line x1="6" y1="18" x2="9" y2="18"/><line x1="8.5" y1="10.5" x2="10.6" y2="12.6"/><line x1="23.5" y1="10.5" x2="21.4" y2="12.6"/></g><path d="M14 27 Q10 27 10 23 Q10 19 14 19 Q14.5 15.5 18 15.5 Q22 15.5 23 19 Q26 19 26 23 Q26 27 22 27 Z" fill="#e0edf7"/></svg>';
      return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 40 40" class="vcw-svg-icon"><circle cx="20" cy="20" r="8" fill="#FFD700"/><g stroke="#FFD700" stroke-width="2.5" stroke-linecap="round"><line x1="20" y1="4" x2="20" y2="8"/><line x1="20" y1="32" x2="20" y2="36"/><line x1="4" y1="20" x2="8" y2="20"/><line x1="32" y1="20" x2="36" y2="20"/><line x1="7.9" y1="7.9" x2="10.8" y2="10.8"/><line x1="29.2" y1="29.2" x2="32.1" y2="32.1"/><line x1="32.1" y1="7.9" x2="29.2" y2="10.8"/><line x1="10.8" y1="29.2" x2="7.9" y2="32.1"/></g></svg>';
    };

    this.refresh = function () {
      var root = d3.select(me.rawSelector);

      if (me.error) {
        if (!me.designMode && me.errorIsSetupIssue) {
          // Merchant hasn't finished setup — don't show that to shoppers.
          root.html("");
          return;
        }
        var displayError = me.designMode ? me.error : GENERIC_ERROR;
        root.html("<div class='vcw-error'>" +
          "<strong>\u26a0 Weather unavailable</strong><br>" + escapeHtml(displayError) + "</div>");
        return;
      }

      var data   = me.config.hourly ? me.hourlydata : me.dailydata;
      var values = me._getForecastValues(data);
      if (!values || !values.length) return;

      var tu = me.config.unitGroup === "us" ? "\u00b0F" : "\u00b0C";

      root.classed("forecastwidget", true);

      if (root.select(".location").empty()) {
        var titleHtml = (me.config.showTitle && me.config.title)
          ? "<div class='vcw-title'>" + escapeHtml(me.config.title) + "</div>"
          : "";
        root.html(
          titleHtml +
          "<div class='location'><span class='value'>-</span>" +
          "<input type='text' class='editor' value=''>" +
          "<div class='viewchooser day selected' title='Daily'>Daily</div>" +
          "<div class='viewchooser hour' title='Hourly'>Hourly</div>" +
          "</div>" +
          "<div class='days noselect'></div>" +
          "<svg class='chart'></svg>" +
          "<div class='footer'>" +
          "<a href='https://www.visualcrossing.com/weather-api' target='_blank' rel='noopener'>Visual Crossing Weather</a>" +
          "</div>"
        );

        if (window.ResizeObserver) {
          new ResizeObserver(function () { me.refresh(); }).observe(root.node());
        }
      }

      var locLabel = (data && data.resolvedAddress) || me.config.location || "";
      root.select(".location .value").html(escapeHtml(locLabel));

      root.selectAll(".viewchooser")
        .classed("selected", function () {
          return (d3.select(this).classed("day") && !me.config.hourly) ||
                 (d3.select(this).classed("hour") && me.config.hourly);
        })
        .on("click", function () {
          me.config.hourly = d3.select(this).classed("hour");
          me.dailydata  = me.config.hourly ? me.dailydata  : null;
          me.hourlydata = me.config.hourly ? null : me.hourlydata;
          me.loadForecastData();
        });

      var locEditor = root.select(".location .editor");
      locEditor.attr("value", me.config.location);
      locEditor.on("keypress", function (event) {
        if (event.keyCode === 13) {
          root.select(".location").classed("edit", false);
          me.setLocation(locEditor.node().value);
        }
      });

      root.select(".location .value").on("click", function (event) {
        root.select(".location").classed("edit", !root.select(".location").classed("edit"));
        event.stopPropagation();
      });

      // ── Layout metrics ─────────────────────────────────────────
      var rect      = root.node().getBoundingClientRect();
      var margin    = { top: 0, right: 20, bottom: 0, left: 20 };
      var width     = rect.width - margin.left - margin.right;
      var minWidth  = me.config.hourly ? 60 : 70;
      var extent    = d3.extent(values, function (d) { return d.datetime; });
      var periods   = me.config.hourly
        ? d3.timeHour.count(extent[0], extent[1])
        : d3.timeDay.count(extent[0], extent[1]);
      var periodWidth = Math.max(width / (periods || 1), minWidth);

      var x = d3.scaleTime().range([0, periods * periodWidth]).domain(extent);

      // ── Day cards ──────────────────────────────────────────────
      var daysContainer = root.select(".days")
        .style("width", width + "px")
        .style("left", margin.left + "px")
        .selectAll(".day").data(values);

      daysContainer.exit().remove();

      var entered = daysContainer.enter().append("div").attr("class", "day")
        .html("<div class='date'></div><div class='icon-wrap'></div>" +
              "<div class='maxt'></div><div class='mint'></div>" +
              "<div class='temp'></div><div class='precip'></div><div class='conditions'></div>");

      daysContainer = daysContainer.merge(entered);

      daysContainer
        .style("top", "5px")
        .transition()
        .style("left", function (d) { return x(d.datetime) + "px"; })
        .style("width", periodWidth + "px");

      daysContainer.select(".date").html(function (d) {
        if (!me.config.hourly || +d3.timeDay.floor(d.datetime) === +d.datetime) {
          return d3.timeFormat("%b %d")(d.datetime);
        }
        return d3.timeFormat("%H:%M")(d.datetime);
      });

      daysContainer.select(".icon-wrap").html(function (d) {
        return me._iconSvg(d.conditions || "");
      });

      daysContainer.select(".maxt").classed("hidden", me.config.hourly)
        .html(function (d) { return d.tempmax != null ? Math.round(d.tempmax) + tu : ""; });
      daysContainer.select(".mint").classed("hidden", me.config.hourly)
        .html(function (d) { return d.tempmin != null ? Math.round(d.tempmin) + tu : ""; });

      daysContainer.select(".temp").classed("hidden", !me.config.hourly)
        .html(function (d) { return d.temp != null ? Math.round(d.temp) + tu : ""; });

      daysContainer.select(".precip").classed("hidden", me.config.hourly)
        .html(function (d) {
          return (!me.config.hourly && d.precip > 0) ? d.precip.toFixed(1) : "";
        });

      daysContainer.select(".conditions").html(function (d) { return escapeHtml(d.conditions || ""); });

      // ── Chart ──────────────────────────────────────────────────
      var chartContainer = root.select(".chart");
      var crect  = chartContainer.node().getBoundingClientRect();
      var height = crect.height - margin.top - margin.bottom;

      var tempMinVal = d3.min(values, function (d) { return (me.config.hourly ? d.temp : d.tempmin) - 5; });
      var tempMaxVal = d3.max(values, function (d) { return (me.config.hourly ? d.temp : d.tempmax); });

      var y = d3.scaleLinear().range([height, 0]).domain([tempMinVal, tempMaxVal]);

      var precipMax = d3.max(values, function (d) { return d.precip || 0; }) || 1;
      var yPrecip = d3.scaleLinear().range([0, height * 0.25]).domain([0, precipMax]);

      var area = d3.area()
        .x(function (d, i) {
          if (i === 0) return x(d.datetime);
          if (i === values.length - 1) return x(d3.timeHour.offset(d.datetime, me.config.hourly ? 1 : 24));
          return x(d3.timeHour.offset(d.datetime, me.config.hourly ? 0.5 : 12));
        })
        .y0(height)
        .y1(function (d) { return y(me.config.hourly ? d.temp : d.tempmax); })
        .curve(d3.curveCatmullRom);

      var chartDrawing;
      if (chartContainer.select("g").empty()) {
        var chartRoot = chartContainer;
        chartRoot.append("clipPath").attr("id", "vcw-clip-" + me.uid)
          .append("rect").attr("x", 0).attr("y", 0).attr("width", 0).attr("height", 0);
        chartRoot = chartRoot.append("g")
          .attr("transform", "translate(" + margin.left + "," + margin.top + ")")
          .attr("clip-path", "url(#vcw-clip-" + me.uid + ")");
        chartDrawing = chartRoot.append("g").attr("class", "container");
        chartDrawing.append("path").attr("class", "line")
          .style("fill", "url(#vcw-temp-grad-" + me.uid + ")");
        chartDrawing.append("linearGradient").attr("id", "vcw-temp-grad-" + me.uid).attr("gradientUnits", "userSpaceOnUse");
        chartDrawing.append("g").attr("class", "precipbars");
        chartDrawing.append("g").attr("class", "grid");
      } else {
        chartDrawing = chartContainer.select(".container");
      }

      chartContainer.select("#vcw-clip-" + me.uid + " rect")
        .attr("x", -margin.left).attr("width", crect.width).attr("height", crect.height);

      chartDrawing.attr("transform", null);

      var stops = d3.range(0, 11).map(function (i) {
        return { offset: (i * 10) + "%", t: 1 - (i / 10) };
      });
      var stopsEl = chartDrawing.select("#vcw-temp-grad-" + me.uid)
        .attr("x1", 0).attr("y1", 0)
        .attr("x2", 0).attr("y2", height)
        .selectAll("stop").data(stops);
      stopsEl.exit().remove();
      stopsEl = stopsEl.merge(stopsEl.enter().append("stop"));
      stopsEl.attr("offset", function (d) { return d.offset; })
        .attr("stop-color", function (d) { return _turbo(d.t); })
        .attr("stop-opacity", 0.85);

      chartDrawing.select(".line").datum(values).transition().attr("d", area);

      var precipData = me.config.hourly ? [] : values.filter(function (d) { return d.precip > 0; });
      var bars = chartDrawing.select(".precipbars").selectAll(".precipbar").data(precipData);
      bars.exit().remove();
      bars = bars.merge(bars.enter().append("rect").attr("class", "precipbar"));
      bars
        .attr("x", function (d) {
          return x(d3.timeHour.offset(d.datetime, 12)) - Math.max(periodWidth * 0.18, 3);
        })
        .attr("width", Math.max(periodWidth * 0.36, 6))
        .attr("y", function (d) { return height - yPrecip(d.precip); })
        .attr("height", function (d) { return yPrecip(d.precip); });

      chartDrawing.select(".grid")
        .attr("transform", "translate(0," + height + ")")
        .call(d3.axisBottom(x).ticks(periods).tickSize(-height).tickFormat(""));

      // ── Pan / scroll ───────────────────────────────────────────
      var zoom = d3.zoom()
        .scaleExtent([1, 1])
        .translateExtent([[0, 0], [(periods + 2) * periodWidth, 0]])
        .on("zoom", function (event) {
          var t = event.transform; t.k = 1; t.y = 0;
          root.select(".days").style("left", (margin.left + t.x) + "px");
          chartDrawing.attr("transform", t);
        });
      root.call(zoom);
    };
  }

  function _turbo(t) {
    t = Math.max(0, Math.min(1, t));
    return "rgb(" +
      Math.max(0,Math.min(255,Math.round(34.61  + t*(1172.33  - t*(10793.56 - t*(33300.12 - t*(38394.49 - t*14825.05))))))) + "," +
      Math.max(0,Math.min(255,Math.round(23.31  + t*(557.33   + t*(1225.33  - t*(3574.96  - t*(1073.77  + t*707.56))))))) + "," +
      Math.max(0,Math.min(255,Math.round(27.2   + t*(3211.1   - t*(15327.97 - t*(27814    - t*(22569.18 - t*6838.66))))))) +
    ")";
  }

  function attach(config) {
    // The theme can render this app block more than once on a page, and each
    // instance's own <script src> tag re-executes this whole file, re-processing
    // every entry in window.weatherWidgetConfig — including ones already attached
    // by an earlier execution. Guard against that here.
    if (config._vcwLoaded) return null;
    config._vcwLoaded = true;

    ensureBodyClickHandler();
    var instance = new WeatherForecastWidget(config);
    instance.loadForecastData();
    return instance;
  }

  if (!window.weatherWidgetConfig) {
    console.warn("[VC Weather D3] No widget configuration found.");
  } else {
    window.weatherWidgetConfig.forEach(function (config) { attach(config); });
  }

  return {};
}());
