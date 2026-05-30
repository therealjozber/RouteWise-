/* RouteWise TZ — Leaflet maps with via-points and segment polylines */

function initRouteMap(mapId, mapData) {
  const el = document.getElementById(mapId);
  if (!el || !mapData) return;

  const map = L.map(mapId).setView([-6.5, 36.5], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);

  const bounds = [];
  const statusColors = {
    Safe: "#2a9d8f",
    Caution: "#f4a261",
    "High Risk": "#e76f51",
    Avoid: "#991b1b",
  };

  if (mapData.path && mapData.path.length >= 2) {
    L.polyline(mapData.path, {
      color: "#0d3b66",
      weight: 4,
      opacity: 0.75,
      dashArray: "8, 6",
    }).addTo(map);
  }

  (mapData.waypoints || []).forEach(function (wp, idx) {
    const color = wp.status ? statusColors[wp.status] || "#0d3b66" : "#0d3b66";
    const marker = L.circleMarker([wp.lat, wp.lng], {
      radius: idx === 0 || idx === mapData.waypoints.length - 1 ? 9 : 7,
      fillColor: color,
      color: "#fff",
      weight: 2,
      fillOpacity: 0.95,
    }).addTo(map);
    let popup = "<strong>" + wp.name + "</strong>";
    if (wp.status) popup += "<br>Section status: " + wp.status;
    marker.bindPopup(popup);
    bounds.push([wp.lat, wp.lng]);
  });

  const severityColors = {
    Low: "#2a9d8f",
    Medium: "#f4a261",
    High: "#e9c46a",
    Critical: "#e76f51",
  };

  (mapData.incidents || []).forEach(function (inc) {
    const color = severityColors[inc.severity] || "#64748b";
    L.marker([inc.lat, inc.lng], { opacity: 0.9 })
      .addTo(map)
      .bindPopup(
        "<strong>" + inc.type + "</strong><br>" + inc.location +
        (inc.segment ? "<br><em>" + inc.segment + "</em>" : "") +
        "<br><span class='badge'>" + inc.severity + "</span>"
      );
    bounds.push([inc.lat, inc.lng]);
  });

  if (bounds.length >= 2) {
    map.fitBounds(bounds, { padding: [50, 50] });
  } else if (bounds.length === 1) {
    map.setView(bounds[0], 9);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const scriptEl = document.getElementById("map-data");
  if (scriptEl && document.getElementById("route-map")) {
    try {
      const data = JSON.parse(scriptEl.textContent);
      initRouteMap("route-map", data);
    } catch (e) {
      console.warn("Map data parse error", e);
    }
  }
});
