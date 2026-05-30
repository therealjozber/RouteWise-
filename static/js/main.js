/* RouteWise TZ — Map Engine
   OpenStreetMap via Leaflet with colored risk segments, custom icons, legends
   -----------------------------------------------------------------------
   Public API:
     initRouteMap(mapId, mapData)   — single route with colored segments
     initFullMap(mapId, allData)    — all Tanzania routes overview
     initHeroMap(mapId, allData)    — mini hero map (same as full, compact)
*/

(function (window) {
  "use strict";

  /* ── Color palette matching CSS variables ── */
  var STATUS_COLORS = {
    "Safe":      "#06d6a0",
    "Caution":   "#ffd166",
    "High Risk": "#ef476f",
    "Avoid":     "#c0392b",
  };

  var SEVERITY_COLORS = {
    "Low":      "#06d6a0",
    "Medium":   "#ffd166",
    "High":     "#ef476f",
    "Critical": "#c0392b",
  };

  var INCIDENT_ICONS = {
    "Accident":           { emoji: "💥", bg: "#ef476f" },
    "Flood":              { emoji: "🌊", bg: "#0096c7" },
    "Bad Road":           { emoji: "🚧", bg: "#ffd166", fg: "#1e293b" },
    "Traffic Jam":        { emoji: "🚦", bg: "#f4a261" },
    "Road Block":         { emoji: "⛔", bg: "#c0392b" },
    "Police Checkpoint":  { emoji: "👮", bg: "#457b9d" },
    "Fuel Shortage":      { emoji: "⛽", bg: "#ff9f1c", fg: "#1e293b" },
    "Theft Hotspot":      { emoji: "⚠️", bg: "#d62828" },
    "Vehicle Breakdown":  { emoji: "🔧", bg: "#64748b" },
  };

  /* ── OSM tile layer factory ── */
  function osmLayer() {
    return L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
      maxZoom: 18,
    });
  }

  /* ── Custom incident marker ── */
  function makeIncidentIcon(type, severity) {
    var info = INCIDENT_ICONS[type] || { emoji: "📍", bg: "#64748b" };
    var color = SEVERITY_COLORS[severity] || info.bg;
    var fg = info.fg || "#fff";
    var size = severity === "Critical" ? 34 : severity === "High" ? 30 : 26;
    var html = (
      '<div style="width:' + size + 'px;height:' + size + 'px;' +
      'background:' + color + ';border-radius:50%;' +
      'display:flex;align-items:center;justify-content:center;' +
      'font-size:' + (size * 0.52) + 'px;' +
      'box-shadow:0 2px 8px rgba(0,0,0,0.35),0 0 0 2px rgba(255,255,255,0.7);' +
      (severity === "Critical" ? "animation:rwPulse 1.6s infinite;" : "") +
      '">' + info.emoji + '</div>'
    );
    return L.divIcon({
      html: html,
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -(size / 2 + 4)],
    });
  }

  /* ── Waypoint circle marker ── */
  function makeWaypointMarker(wp, isEndpoint) {
    var color = STATUS_COLORS[wp.status] || "#0d3b66";
    return L.circleMarker([wp.lat, wp.lng], {
      radius: isEndpoint ? 10 : 7,
      fillColor: color,
      color: "#fff",
      weight: isEndpoint ? 3 : 2,
      fillOpacity: 1,
    });
  }

  /* ── Build popup HTML for a segment ── */
  function segmentPopup(seg) {
    var color = STATUS_COLORS[seg.status] || "#64748b";
    var badge = '<span class="popup-badge popup-' +
      (seg.status || "safe").toLowerCase().replace(" ", "-") +
      '">' + (seg.status || "Unknown") + '</span>';
    return (
      '<div class="popup-title">' + seg.from + ' → ' + seg.to + '</div>' +
      badge +
      (seg.risk_score ? ' <small style="color:#64748b">Risk: ' + seg.risk_score + '/100</small>' : '') +
      (seg.distance_km ? '<div style="color:#64748b;font-size:0.78rem;margin-top:4px">' + seg.distance_km + ' km · ' + (seg.estimated_time || '') + '</div>' : '')
    );
  }

  /* ── Build popup HTML for an incident ── */
  function incidentPopup(inc) {
    var sev = inc.severity || "Medium";
    var color = SEVERITY_COLORS[sev] || "#64748b";
    return (
      '<div class="popup-title" style="color:' + color + '">' +
      (INCIDENT_ICONS[inc.type] ? INCIDENT_ICONS[inc.type].emoji + ' ' : '') +
      (inc.type || "Incident") +
      '</div>' +
      '<div style="font-weight:600;margin-bottom:3px">' + (inc.location || '') + '</div>' +
      (inc.segment ? '<div style="font-style:italic;color:#64748b;font-size:0.78rem">' + inc.segment + '</div>' : '') +
      (inc.route ? '<div style="color:#64748b;font-size:0.78rem">' + inc.route + '</div>' : '') +
      (inc.description ? '<div style="margin-top:4px;color:#374151">' + inc.description + '</div>' : '') +
      '<div style="margin-top:6px"><span style="background:' + color + ';color:#fff;padding:1px 8px;border-radius:10px;font-size:0.72rem;font-weight:700">' + sev + '</span></div>'
    );
  }

  /* ── Add CSS animation for pulse ── */
  (function injectCSS() {
    if (document.getElementById("rw-map-styles")) return;
    var s = document.createElement("style");
    s.id = "rw-map-styles";
    s.textContent =
      "@keyframes rwPulse{0%,100%{box-shadow:0 2px 8px rgba(0,0,0,.35),0 0 0 2px rgba(255,255,255,.7),0 0 0 0 currentColor}50%{box-shadow:0 2px 8px rgba(0,0,0,.35),0 0 0 2px rgba(255,255,255,.7),0 0 0 8px transparent}}";
    document.head.appendChild(s);
  })();

  /* ── Add map legend control ── */
  function addLegend(map) {
    var LegendControl = L.Control.extend({
      options: { position: "bottomright" },
      onAdd: function () {
        var div = L.DomUtil.create("div", "map-legend");
        div.innerHTML =
          '<div class="map-legend-title">Road Status</div>' +
          '<div class="legend-item"><div class="legend-dot safe"></div>Safe</div>' +
          '<div class="legend-item"><div class="legend-dot caution"></div>Caution</div>' +
          '<div class="legend-item"><div class="legend-dot high"></div>High Risk</div>' +
          '<div class="legend-item"><div class="legend-dot avoid"></div>Avoid</div>';
        L.DomEvent.disableClickPropagation(div);
        return div;
      },
    });
    new LegendControl().addTo(map);
  }

  /* =================================================================
     initRouteMap — single route with colored segment polylines
     ================================================================= */
  window.initRouteMap = function (mapId, mapData) {
    var el = document.getElementById(mapId);
    if (!el || !mapData) return;

    var map = L.map(mapId, { zoomControl: true }).setView([-6.5, 36.5], 6);
    osmLayer().addTo(map);

    var bounds = [];

    /* Draw each segment as a colored polyline */
    var segs = mapData.segments || [];
    if (segs.length > 0) {
      segs.forEach(function (seg) {
        var color = STATUS_COLORS[seg.status] || "#0d3b66";
        var weight = (seg.status === "High Risk" || seg.status === "Avoid") ? 8 : 6;
        var opacity = (seg.status === "High Risk" || seg.status === "Avoid") ? 0.92 : 0.82;
        var line = L.polyline(seg.coords, {
          color: color,
          weight: weight,
          opacity: opacity,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(map);
        line.bindPopup(segmentPopup(seg));
        seg.coords.forEach(function (c) { bounds.push(c); });
      });
    } else if (mapData.path && mapData.path.length >= 2) {
      /* Fallback: single path in primary color */
      L.polyline(mapData.path, {
        color: "#0d3b66",
        weight: 5,
        opacity: 0.75,
        dashArray: "8 6",
      }).addTo(map);
      mapData.path.forEach(function (c) { bounds.push(c); });
    }

    /* Waypoint markers */
    var wps = mapData.waypoints || [];
    wps.forEach(function (wp, idx) {
      var isEnd = (idx === 0 || idx === wps.length - 1);
      var marker = makeWaypointMarker(wp, isEnd);
      marker.addTo(map);
      var popupHtml = '<div class="popup-title">' + wp.name + '</div>';
      if (wp.status) {
        popupHtml += '<span class="popup-badge popup-' +
          wp.status.toLowerCase().replace(" ", "-") + '">' + wp.status + '</span>';
      }
      marker.bindPopup(popupHtml);
      bounds.push([wp.lat, wp.lng]);
    });

    /* Incident markers */
    (mapData.incidents || []).forEach(function (inc) {
      var icon = makeIncidentIcon(inc.type, inc.severity);
      L.marker([inc.lat, inc.lng], { icon: icon })
        .addTo(map)
        .bindPopup(incidentPopup(inc));
      bounds.push([inc.lat, inc.lng]);
    });

    /* Fit map to content */
    if (bounds.length >= 2) {
      map.fitBounds(bounds, { padding: [40, 40] });
    } else if (bounds.length === 1) {
      map.setView(bounds[0], 10);
    }

    addLegend(map);
    return map;
  };

  /* =================================================================
     initFullMap / initHeroMap — Tanzania overview with all routes
     ================================================================= */
  function buildFullMap(mapId, allData, opts) {
    opts = opts || {};
    var el = document.getElementById(mapId);
    if (!el || !allData) return;

    var map = L.map(mapId, {
      zoomControl: !opts.noZoom,
      scrollWheelZoom: opts.scrollZoom !== false,
    }).setView([-6.3, 35.0], opts.zoom || 6);

    osmLayer().addTo(map);

    var routes = allData.routes || [];
    var allIncidents = [];
    var routeLayers = {};

    routes.forEach(function (route) {
      var segs = route.segments || [];
      var routeGroup = L.layerGroup().addTo(map);
      routeLayers[route.id] = routeGroup;

      segs.forEach(function (seg) {
        var color = STATUS_COLORS[seg.status] || "#94a3b8";
        var weight = (seg.status === "High Risk" || seg.status === "Avoid") ? 7 : 5;
        var opacity = (seg.status === "Avoid") ? 0.95 :
                      (seg.status === "High Risk") ? 0.88 : 0.78;

        var popupHtml =
          '<div class="popup-title">' + route.name + '</div>' +
          '<div style="color:#64748b;font-size:0.8rem;margin-bottom:4px">' +
          seg.from + ' → ' + seg.to + '</div>' +
          '<span class="popup-badge popup-' +
          (seg.status || "safe").toLowerCase().replace(" ", "-") + '">' +
          (seg.status || "Safe") + '</span>' +
          (seg.risk_score ? ' <small>Risk: ' + seg.risk_score + '/100</small>' : '') +
          (route.id ? '<div style="margin-top:6px"><a href="/routes/' + route.id +
          '/" style="color:#0096c7;font-weight:600;font-size:0.78rem">View route details →</a></div>' : '');

        var line = L.polyline(seg.coords, {
          color: color, weight: weight, opacity: opacity,
          lineCap: "round", lineJoin: "round",
        });
        line.bindPopup(popupHtml);
        routeGroup.addLayer(line);
      });

      (route.incidents || []).forEach(function (inc) {
        allIncidents.push(inc);
      });
    });

    /* Incident markers (high/critical only on overview) */
    allIncidents.forEach(function (inc) {
      if (!opts.allIncidents && inc.severity !== "High" && inc.severity !== "Critical") return;
      var icon = makeIncidentIcon(inc.type, inc.severity);
      L.marker([inc.lat, inc.lng], { icon: icon })
        .addTo(map)
        .bindPopup(incidentPopup(inc));
    });

    if (!opts.noLegend) addLegend(map);

    map._routeLayers = routeLayers;
    return map;
  }

  window.initFullMap = function (mapId, allData) {
    return buildFullMap(mapId, allData, { allIncidents: true, zoom: 6 });
  };

  window.initHeroMap = function (mapId, allData) {
    return buildFullMap(mapId, allData, {
      noZoom: false,
      scrollZoom: false,
      zoom: 6,
      noLegend: false,
    });
  };

  /* =================================================================
     Filter helper — show/hide routes by status
     ================================================================= */
  window.filterMapByStatus = function (map, statuses) {
    if (!map || !map._routeLayers) return;
    /* statuses = [] means show all */
    /* This works if routes are stored per-layer, but since we draw
       per-segment the simplest approach is to store full map ref and redraw. */
  };

  /* =================================================================
     Auto-init on DOMContentLoaded
     ================================================================= */
  document.addEventListener("DOMContentLoaded", function () {
    /* Route detail map */
    var scriptEl = document.getElementById("map-data");
    if (scriptEl && document.getElementById("route-map")) {
      try {
        var data = JSON.parse(scriptEl.textContent);
        initRouteMap("route-map", data);
      } catch (e) {
        console.warn("Route map data parse error", e);
      }
    }

    /* All-routes maps (dashboard, home, live map) */
    var allDataEl = document.getElementById("all-routes-data");
    if (allDataEl) {
      try {
        var allData = JSON.parse(allDataEl.textContent);
        if (document.getElementById("dashboard-map")) {
          initFullMap("dashboard-map", allData);
        }
        if (document.getElementById("full-map")) {
          initFullMap("full-map", allData);
        }
        if (document.getElementById("hero-map")) {
          initHeroMap("hero-map", allData);
        }
      } catch (e) {
        console.warn("All-routes map data parse error", e);
      }
    }
  });

})(window);
