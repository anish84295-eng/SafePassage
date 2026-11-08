const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
const map = L.map("map", { preferCanvas: true, zoomControl: false, maxBoundsViscosity: 0.85 }).setView([19.12, 72.845], 12);
L.control.zoom({ position: "topright" }).addTo(map);

const state = {
  meta: null, origin: null, destination: null, originLabel: "", destinationLabel: "",
  scenario: "normal", rainEnabled: false, closuresEnabled: false, plannerCollapsed: false, algorithm: "astar",
  closures: [], routeLayers: [], routeHighlights: [], markers: [], floodLayers: [], hospitalLayers: [], activeHospitalLayers: [], hospitalData: [], dots: null,
  compare: null, selectedRoute: 0, placing: "origin", requestController: null,
  theme: "dark", animation: null, currentTile: null, originalBounds: null, tileConfig: null,
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function showToast(message) {
  const toast = $("#toast"); toast.textContent = message; toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2300);
}
function clearError() { $("#error-card").classList.add("hidden"); }
function setPlannerCollapsed(collapsed) {
  state.plannerCollapsed = collapsed;
  $("#planner-controls").classList.toggle("hidden", collapsed);
  $("#planner-collapse").setAttribute("aria-expanded", String(!collapsed));
  $("#planner-collapse").textContent = collapsed ? "Show controls" : "Hide controls";
}
function refreshConditionControls() {
  state.scenario = state.rainEnabled ? "heavy_rain" : state.closuresEnabled ? "road_closed" : "normal";
  $("#rain-toggle").checked = state.rainEnabled;
  $("#closures-toggle").checked = state.closuresEnabled;
  $("#closure-tools").classList.toggle("hidden", !state.closuresEnabled);
  map.getContainer().style.transition = "filter .35s";
  map.getContainer().style.filter = state.rainEnabled ? "saturate(.72)" : "none";
}
function refreshPresetSelection() {
  const selected = state.rainEnabled && !state.closuresEnabled ? "heavy_rain"
    : state.closuresEnabled && !state.rainEnabled ? "road_closed"
      : !state.rainEnabled && !state.closuresEnabled ? "normal" : null;
  document.querySelectorAll("[data-preset]").forEach((button) => button.classList.toggle("selected", button.dataset.preset === selected));
}
async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(data?.error?.message || `Request failed (${response.status})`); error.code = data?.error?.code; throw error; }
  return data;
}
function tileUrl() {
  const template = state.tileConfig?.url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  return template.replaceAll("{api_key}", encodeURIComponent(state.tileConfig?.api_key || ""));
}
function refreshTiles() {
  if (state.currentTile) map.removeLayer(state.currentTile);
  const tileTemplate = state.tileConfig?.url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const isDarkFallback = state.theme === "dark" && tileTemplate.includes("tile.openstreetmap.org");
  state.currentTile = L.tileLayer(tileUrl(), {
    subdomains: state.tileConfig?.url?.includes("{s}") ? "abcd" : "", maxZoom: 19,
    className: isDarkFallback ? "dark-osm-tiles" : "",
    attribution: state.tileConfig?.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  }).addTo(map);
}
function setTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  refreshTiles();
  try { localStorage.setItem("safepassage-theme", theme); } catch { /* Storage may be disabled. */ }
}
function errorMessage(error) {
  if (error?.name === "AbortError") return;
  showToast(error?.message || "Something went wrong. Please try again.");
}
function pointFromEvent(event) { return { lat: event.latlng.lat, lng: event.latlng.lng }; }
function fmtMeters(value) { return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${Math.round(value)} m`; }
function markerIcon(kind) {
  return L.divIcon({ className: "", html: `<span class="route-pin ${kind}"></span>`, iconSize: [18, 18], iconAnchor: [9, 9] });
}
function clearRouteLayers() {
  state.routeLayers.forEach((layer) => map.removeLayer(layer)); state.routeLayers = [];
  state.routeHighlights = [];
  state.markers.forEach((layer) => map.removeLayer(layer)); state.markers = [];
  state.activeHospitalLayers.forEach((layer) => map.removeLayer(layer)); state.activeHospitalLayers = [];
  if (state.dotLayers) { state.dotLayers.forEach((layer) => map.removeLayer(layer)); state.dotLayers = []; }
  if (state.dots) { map.removeLayer(state.dots); state.dots = null; }
  if (state.animation) { cancelAnimationFrame(state.animation); clearTimeout(state.animation); }
}
function updatePlaceLabels() {
  $("#origin-label").textContent = state.origin ? `${state.origin.lat.toFixed(5)}, ${state.origin.lng.toFixed(5)}${state.originLabel ? ` · near ${state.originLabel}` : ""}` : "Click the map to choose";
  $("#destination-label").textContent = state.destination ? `${state.destination.lat.toFixed(5)}, ${state.destination.lng.toFixed(5)}${state.destinationLabel ? ` · near ${state.destinationLabel}` : ""}` : "Click the map to choose";
  $("#route-button").disabled = !(state.origin && state.destination);
  const routeReady = Boolean(state.origin && state.destination);
  const routeHint = routeReady ? "Start and destination are set. Ready to find a route." : "Set a start and destination on the map";
  $("#route-hint").textContent = routeHint;
  $("#route-button").title = routeHint;
  $("#route-button").setAttribute("aria-label", `Find safest route. ${routeHint}`);
  $("#empty-hint").classList.toggle("hidden", Boolean(state.origin));
  [state.origin, state.destination].forEach((point, index) => {
    if (!point) return;
    const pin = L.marker([point.lat, point.lng], { draggable: true, icon: markerIcon(index ? "dest-pin" : "origin-pin"), keyboard: true, title: index ? "Destination" : "Origin" }).addTo(map);
    pin.on("dragend", (event) => {
      const p = event.target.getLatLng();
      if (index) { state.destination = { lat: p.lat, lng: p.lng }; state.destinationLabel = ""; }
      else { state.origin = { lat: p.lat, lng: p.lng }; state.originLabel = ""; }
      updatePlaceLabels();
      drawClosures();
    });
    state.markers.push(pin);
  });
}
function setPlace(which, point) {
  if (which === "origin") { state.origin = point; state.originLabel = ""; }
  else { state.destination = point; state.destinationLabel = ""; }
  clearRouteLayers(); updatePlaceLabels(); drawClosures();
}
function drawClosures() {
  if (state.closureLayer) map.removeLayer(state.closureLayer);
  state.closureLayer = L.layerGroup(state.closures.map((closure, index) => {
    const circle = L.circle([closure.lat, closure.lng], { radius: closure.radius_m, color: "#ff6675", fillColor: "#ff6675", fillOpacity: .15, weight: 2, className: "pulse" });
    return circle.bindTooltip(`Closure ${index + 1}: ${closure.radius_m} m`);
  })).addTo(map);
  const warnings = state.closures.flatMap((closure, index) => {
    const includes = (point) => point && L.latLng(closure.lat, closure.lng).distanceTo(L.latLng(point.lat, point.lng)) <= closure.radius_m;
    return [includes(state.origin) ? `Closure ${index + 1} contains the start point.` : "", includes(state.destination) ? `Closure ${index + 1} contains the destination.` : ""].filter(Boolean);
  });
  $("#closure-list").innerHTML = state.closures.map((closure, index) => `<div class="closure-item"><span>Closure ${index + 1} · ${closure.radius_m} m</span><button data-remove-closure="${index}" aria-label="Remove closure ${index + 1}">×</button></div>`).join("") + warnings.map((warning) => `<p class="closure-warning">${warning}</p>`).join("");
}
function drawZones(zones) {
  state.floodLayers.forEach((layer) => map.removeLayer(layer)); state.floodLayers = [];
  zones.forEach((zone) => {
    const circle = L.circle([zone.lat, zone.lng], { radius: zone.radius_m, color: "#ff6675", fillColor: "#ff6675", fillOpacity: .13, weight: 1.5, dashArray: "5 5" }).bindTooltip(`${zone.name} · illustrative zone`);
    state.floodLayers.push(circle);
  });
  if ($("#flood-toggle").checked) state.floodLayers.forEach((layer) => layer.addTo(map));
}
function clearHospitals() { state.hospitalLayers.forEach((layer) => map.removeLayer(layer)); state.hospitalLayers = []; }
function hospitalIcon() {
  return L.divIcon({ className: "", html: '<span class="hospital-marker" aria-label="Hospital">✚</span>', iconSize: [27, 27], iconAnchor: [13, 13] });
}
function renderHospitalMarkers() {
  clearHospitals();
  if (!$("#hospital-toggle").checked) return;
  const detailed = map.getZoom() >= 14;
  state.hospitalData.forEach((hospital) => {
    let marker;
    if (detailed) {
      marker = L.marker([hospital.lat, hospital.lng], { icon: hospitalIcon(), title: hospital.name });
    } else {
      marker = L.circleMarker([hospital.lat, hospital.lng], { radius: 3.5, color: "#fff", weight: 1, fillColor: "#d64755", fillOpacity: 1, title: hospital.name });
    }
    marker.bindTooltip(escapeHtml(hospital.name), { direction: "top", sticky: !detailed });
    marker.bindPopup(`<strong>${escapeHtml(hospital.name)}</strong>`);
    state.hospitalLayers.push(marker.addTo(map));
  });
}
async function toggleHospitals() {
  if (!$("#hospital-toggle").checked) { clearHospitals(); return; }
  try {
    if (!state.hospitalData.length) state.hospitalData = await api("/api/hospitals");
    renderHospitalMarkers();
  } catch (error) { errorMessage(error); }
}
function showActiveHospital(hospital) {
  const marker = L.marker([hospital.lat, hospital.lng], { icon: hospitalIcon(), title: hospital.name, zIndexOffset: 1000 })
    .bindTooltip(escapeHtml(hospital.name), { direction: "top" })
    .bindPopup(`<strong>${escapeHtml(hospital.name)}</strong>`)
    .addTo(map);
  state.activeHospitalLayers.push(marker);
}
function animateLine(line) {
  if (reducedMotion) return;
  const path = line.getLatLngs();
  if (path.length < 2) return;
  let startTime = null;
  const duration = 700;
  const traveler = L.circleMarker(path[0], { radius: 5, color: "white", weight: 2, fillColor: "#47d7b1", fillOpacity: 1 }).addTo(map);
  state.markers.push(traveler);
  const revealStart = path.slice(0, 2);
  line.setLatLngs(revealStart);
  if (line._casing) line._casing.setLatLngs(revealStart);
  const tick = (time) => {
    if (startTime === null) startTime = time;
    const progress = Math.min(1, (time - startTime) / duration);
    const segmentPosition = progress * (path.length - 1);
    const segment = Math.min(path.length - 2, Math.floor(segmentPosition));
    const fraction = segmentPosition - segment;
    const from = path[segment], to = path[segment + 1];
    traveler.setLatLng([from.lat + (to.lat - from.lat) * fraction, from.lng + (to.lng - from.lng) * fraction]);
    const visibleCount = Math.max(2, Math.ceil(progress * path.length));
    const visiblePath = progress >= 1 ? path : path.slice(0, visibleCount);
    line.setLatLngs(visiblePath);
    if (line._casing) line._casing.setLatLngs(visiblePath);
    if (progress >= 1) { line.setLatLngs(path); line.setStyle({ dashArray: null }); if (line._casing) line._casing.setLatLngs(path); traveler.remove(); return; }
    state.animation = requestAnimationFrame(tick);
  };
  state.animation = requestAnimationFrame(tick);
}
function fitRoute(line) {
  if (window.innerWidth <= 760) {
    const algorithmBottom = document.querySelector(".algorithm-panel").getBoundingClientRect().bottom;
    const panelTop = document.querySelector(".control-panel").getBoundingClientRect().top;
    map.fitBounds(line.getBounds(), {
      paddingTopLeft: [16, Math.ceil(algorithmBottom + 28)],
      paddingBottomRight: [16, Math.ceil(window.innerHeight - panelTop + 28)],
      maxZoom: 15,
    });
    return;
  }
  map.fitBounds(line.getBounds(), { padding: [70, 70], maxZoom: 15 });
}
function renderRoute(route, style, fit = false) {
  if (!route?.path?.length) return null;
  let casing = null;
  if (style.casing) {
    casing = L.polyline(route.path, { color: "#fff", weight: (style.weight || 6) + 4, opacity: .92, lineCap: "round", lineJoin: "round" }).addTo(map);
    state.routeLayers.push(casing);
  }
  const line = L.polyline(route.path, { color: style.color, weight: style.weight || 5, opacity: style.opacity || .88, dashArray: style.dash || null, lineCap: "round", lineJoin: "round" }).addTo(map);
  line._casing = casing;
  line.on("mouseover", () => line.setStyle({ weight: 8, opacity: 1 }));
  line.on("mouseout", () => line.setStyle({ weight: style.weight || 5, opacity: style.opacity || .88 }));
  state.routeLayers.push(line);
  state.routeHighlights.push(line);
  if (fit) fitRoute(line);
  return line;
}
function renderRouteResult(data) {
  clearRouteLayers();
  setPlannerCollapsed(true);
  state.originLabel = data.snapped_origin_label || "";
  state.destinationLabel = data.snapped_destination_label || "";
  updatePlaceLabels();
  const route = data.route;
  if (!route) { $("#result-card").innerHTML = `<div class="result-title">No route found</div><p class="result-explain">${data.message || "Try another destination or scenario."}</p>`; $("#result-card").classList.remove("hidden"); return; }
  const line = renderRoute(route, { color: "#35d5ad", weight: 6, casing: true });
  if (line) animateLine(line);
  const alternatives = data.alternatives || [];
  if (route.path.length) {
    [[route.path[0], "A"], [route.path[route.path.length - 1], "B"]].forEach(([point, label]) => {
      const endpoint = L.marker(point, { icon: L.divIcon({ className: "", html: `<span class="route-end-label">${label}</span>`, iconSize: [24, 24], iconAnchor: [12, 12] }), interactive: false });
      state.markers.push(endpoint.addTo(map));
    });
  }
  const explanation = Number.isFinite(data.normal_route_flooded_edges)
    ? `${state.rainEnabled ? "The normal route would cross" : "Normal route crosses"} ${data.normal_route_flooded_edges} flood-marked edges${state.rainEnabled ? `; this route crosses ${route.flooded_edges} flooded edges` : " under heavy rain"}.`
    : "Route optimized for the selected scenario.";
  $("#result-card").innerHTML = `<div class="result-title"><span>Recommended route</span><span class="eyebrow">${data.algorithm.toUpperCase()}</span></div>
    <div class="result-grid"><div class="metric"><strong>${fmtMeters(route.distance_m)}</strong><span>Distance</span></div><div class="metric"><strong>${Math.round(route.duration_s / 60)} min</strong><span>Est. ETA</span></div><div class="metric"><strong>${route.safety_score}</strong><span>Safety / 100</span></div></div>
    <p id="route-explanation" class="result-explain">${explanation} · ${data.nodes_explored} explored · ${data.compute_ms} ms</p>
    <div id="alternative-list" class="alternative-list">${alternatives.length ? "" : "<p class=\"result-explain\">Loading alternatives…</p>"}</div>`;
  $("#result-card").classList.remove("hidden");
  renderAlternativeControls(alternatives);
  if (line) fitRoute(line);
}
function renderAlternativeControls(alternatives) {
  if (!$("#alternative-list")) return;
  state.latestRoute.alternatives = alternatives;
  const host = $("#alternative-list");
  host.innerHTML = alternatives.length ? alternatives.map((item, index) => `<button class="alternative-button" data-route-index="${index + 1}">Alternative ${index + 1} · ${fmtMeters(item.distance_m)} · ${Math.round(item.duration_s / 60)} min</button>`).join("") : '<p class="result-explain">No distinct alternatives found.</p>';
  alternatives.forEach((alternative) => renderRoute(alternative, { color: "#f6b94c", weight: 4, opacity: .8, dash: "8 7" }));
  host.querySelectorAll("[data-route-index]").forEach((button) => {
    const index = Number(button.dataset.routeIndex);
    button.addEventListener("mouseenter", () => state.routeHighlights[index + 1]?.setStyle({ weight: 6, opacity: 1 }));
    button.addEventListener("mouseleave", () => state.routeHighlights[index + 1]?.setStyle({ weight: 4, opacity: .8 }));
    button.addEventListener("click", () => {
      const chosen = state.latestRoute.alternatives[index - 1]; clearRouteLayers();
      const chosenLine = renderRoute(chosen, { color: "#35d5ad", weight: 6, casing: true }, true); if (chosenLine) animateLine(chosenLine);
    });
  });
}
async function findRoute() {
  state.latestRoute = null;
  clearError(); $("#route-button").disabled = true; $("#route-button").innerHTML = '<span class="button-spinner" aria-hidden="true"></span> Calculating…';
  $("#result-card").innerHTML = '<div class="skeleton-line"></div><div class="skeleton-line short"></div><div class="skeleton-line"></div>';
  $("#result-card").classList.remove("hidden");
  if (state.requestController) state.requestController.abort();
  const controller = new AbortController(); state.requestController = controller;
  try {
    const data = await api("/api/route", { method: "POST", signal: controller.signal, body: JSON.stringify({ origin: state.origin, destination: state.destination, scenario: state.scenario, algorithm: "astar", alternatives: 0, include_normal_comparison: false, closures: state.closuresEnabled ? state.closures : [] }) });
    state.latestRoute = data; renderRouteResult(data);
    if (data.route) loadAlternatives(data);
    if ($("#algorithm-toggle").getAttribute("aria-checked") === "true") runCompare();
  } catch (error) {
    if (error.name !== "AbortError") {
      if (["origin_cut_off", "destination_cut_off", "no_path"].includes(error.code)) showClosureToast(error.message); else errorMessage(error);
      if (state.requestController === controller) {
        $("#result-card").textContent = error.message || "Route could not be calculated.";
      }
    }
  }
  finally {
    if (state.requestController === controller) {
      state.requestController = null;
      $("#route-button").disabled = !(state.origin && state.destination);
      $("#route-button").innerHTML = '<svg class="button-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19 9 5l6 14 5-14"/><circle cx="9" cy="5" r="2"/><circle cx="15" cy="19" r="2"/></svg> Find safest route';
    }
  }
}
async function loadAlternatives(routeData) {
  try {
    const data = await api("/api/alternatives", { method: "POST", body: JSON.stringify({ origin: state.origin, destination: state.destination, scenario: state.scenario, alternatives: 2, closures: state.closuresEnabled ? state.closures : [] }) });
    if (state.latestRoute !== routeData) return;
    routeData.normal_route_flooded_edges = data.normal_route_flooded_edges;
    const normalText = data.normal_route_flooded_edges
      ? `${state.rainEnabled ? "The normal route would cross" : "Normal route crosses"} ${data.normal_route_flooded_edges} flood-marked edges${state.rainEnabled ? `; this route crosses ${routeData.route.flooded_edges} flooded edges` : " under heavy rain"}.`
      : "Route optimized for the selected scenario.";
    const explanation = $("#route-explanation"); if (explanation) explanation.textContent = `${normalText} · ${routeData.nodes_explored} explored · ${routeData.compute_ms} ms`;
    renderAlternativeControls(data.alternatives || []);
  } catch (error) { if (state.latestRoute === routeData) showToast(`Route found; alternatives could not be loaded. ${error.message}`); }
}
async function findNearest() {
  if (!state.origin) { showToast("Choose an origin on the map first."); return; }
  const button = $("#nearest-button"); button.disabled = true;
  try {
    const data = await api("/api/nearest-hospitals", { method: "POST", body: JSON.stringify({ origin: state.origin, scenario: state.scenario, k: 3, closures: state.closuresEnabled ? state.closures : [] }) });
    clearRouteLayers();
    setPlannerCollapsed(true);
    updatePlaceLabels();
    const colors = ["#47d7b1", "#f6b94c", "#61a9ff"];
    data.hospitals.forEach((hospital, index) => {
      renderRoute({ path: hospital.path, distance_m: hospital.distance_m }, index ? { color: "#f6b94c", dash: "8 7", weight: 4 } : { color: "#35d5ad", weight: 6, casing: true }, index === 0);
      showActiveHospital(hospital);
    });
    $("#result-card").innerHTML = data.hospitals.length ? `<div class="result-title">Nearest hospitals${data.cut_off ? " · cut-off warning" : ""}</div>${data.hospitals.map((item) => `<p class="result-explain"><b>${escapeHtml(item.name)}</b> · ${fmtMeters(item.distance_m)} · ${Math.round(item.duration_s / 60)} min</p>`).join("")}` : `<p class="result-explain">No hospital can be reached from this road node.</p>`;
    $("#result-card").classList.remove("hidden");
  } catch (error) { errorMessage(error); }
  finally { button.disabled = false; }
}
function placeAlgorithmDots(result, count = result.visited_order.length) {
  if (state.dotLayers) { state.dotLayers.forEach((layer) => map.removeLayer(layer)); state.dotLayers = []; }
  if (state.dots) map.removeLayer(state.dots);
  const points = result.visited_order.slice(0, count).map((point) => L.latLng(point));
  state.dots = L.canvas({ padding: .5, pane: "searchPane" });
  state.dotLayers = points.map((point, index) => {
    const progress = points.length <= 1 ? 1 : index / (points.length - 1);
    const color = `hsl(190 100% ${Math.round(92 - progress * 42)}%)`;
    return L.circleMarker(point, { renderer: state.dots, radius: 3, color: "#07131a", weight: 1, fillColor: color, fillOpacity: .98 }).addTo(map);
  });
  state.dots.addTo(map);
  drawComparePath(result);
}
function drawComparePath(result) {
  if (state.comparePath) { map.removeLayer(state.comparePath); state.routeLayers = state.routeLayers.filter((layer) => layer !== state.comparePath); }
  if (!result?.final_path?.length) return;
  state.comparePath = L.polyline(result.final_path, { pane: "overlayPane", color: "#ff2f91", weight: 2.5, opacity: .95, dashArray: "5 6", interactive: false }).addTo(map);
  state.routeLayers.push(state.comparePath);
}
function selectedCompareResult() { return state.compare?.results?.[state.algorithm]; }
function replayDots() {
  if (!state.compare) return;
  const result = selectedCompareResult();
  if (!result) return;
  const reduced = reducedMotion;
  const delay = Math.max(8, 105 - Number($("#speed-slider").value) * 9);
  let index = reduced ? result.visited_order.length : 0;
  if (state.animation) { cancelAnimationFrame(state.animation); clearTimeout(state.animation); }
  if (reduced) { placeAlgorithmDots(result); return; }
  const drawFrame = () => {
    const batch = Math.max(1, Math.round((11 - Number($("#speed-slider").value)) * 3));
    index = Math.min(index + batch, result.visited_order.length);
    placeAlgorithmDots(result, index);
    if (index < result.visited_order.length) state.animation = window.setTimeout(drawFrame, delay);
  };
  drawFrame();
}
async function runCompare() {
  if (!state.origin || !state.destination) { showToast("Set both route points first."); return; }
  try {
    state.compare = await api("/api/compare", { method: "POST", body: JSON.stringify({ origin: state.origin, destination: state.destination, scenario: state.scenario, closures: state.closuresEnabled ? state.closures : [] }) });
    updateAlgorithmStats(); replayDots();
  } catch (error) { errorMessage(error); }
}
function updateAlgorithmStats() {
  const item = selectedCompareResult();
  if (!item) return;
  const explanation = { astar: "Guided by distance to the target", dijkstra: "Explores by cost from the start", bfs: "Fewest road segments; ignores flooding and road length" }[state.algorithm];
  const flooded = item.flooded_edges ? ` · crosses ${item.flooded_edges} flooded edges` : "";
  $("#algorithm-stats").innerHTML = `<span>${escapeHtml(explanation)}</span><b>${item.nodes_explored.toLocaleString()} nodes · ${item.compute_ms} ms · ${fmtMeters(item.distance_m)}${flooded}</b>`;
}
function showClosureToast(message) {
  const toast = $("#toast"); toast.innerHTML = `${escapeHtml(message)} <button type="button" id="remove-last-closure">Remove last closure</button>`; toast.classList.add("show");
  $("#remove-last-closure").addEventListener("click", () => { state.closures.pop(); drawClosures(); toast.classList.remove("show"); });
  window.setTimeout(() => toast.classList.remove("show"), 5000);
}
function resetAll() {
  state.origin = null; state.destination = null; state.originLabel = ""; state.destinationLabel = ""; state.latestRoute = null;
  clearRouteLayers(); updatePlaceLabels(); $("#result-card").classList.add("hidden"); clearError(); setPlannerCollapsed(false);
}
map.on("click", (event) => {
  const point = pointFromEvent(event);
  if (state.closuresEnabled) {
    if (state.closures.length >= 5) { showToast("You can add up to 5 closures."); return; }
    state.closures.push({ ...point, radius_m: Number($("#closure-radius").value) }); drawClosures(); return;
  }
  setPlace(state.placing, point);
  if (state.placing === "origin") state.placing = "destination";
});
map.createPane("searchPane"); map.getPane("searchPane").style.zIndex = 350;
map.on("zoomend", () => { if ($("#hospital-toggle").checked) renderHospitalMarkers(); });
$("#set-origin").addEventListener("click", () => { state.placing = "origin"; showToast("Click the map to set the origin."); });
$("#set-destination").addEventListener("click", () => { state.placing = "destination"; showToast("Click the map to set the destination."); });
$("#origin-label").addEventListener("click", () => { state.placing = "origin"; showToast("Click the map to set the origin."); });
$("#destination-label").addEventListener("click", () => { state.placing = "destination"; showToast("Click the map to set the destination."); });
$("#route-button").addEventListener("click", findRoute);
$("#recenter-button").addEventListener("click", () => {
  if (state.originalBounds) map.fitBounds(state.originalBounds);
});
$("#nearest-button").addEventListener("click", findNearest);
$("#example-button").addEventListener("click", () => {
  if (state.requestController) state.requestController.abort();
  state.origin = { lat: 19.1597, lng: 72.8399 };
  state.destination = { lat: 19.1105, lng: 72.8420 };
  state.originLabel = ""; state.destinationLabel = "";
  state.rainEnabled = true; state.closuresEnabled = false;
  refreshConditionControls(); refreshPresetSelection(); clearRouteLayers(); updatePlaceLabels(); drawClosures();
  findRoute();
});
$("#clear-button").addEventListener("click", () => { resetAll(); state.closures = []; drawClosures(); });
$("#planner-collapse").addEventListener("click", () => setPlannerCollapsed(!state.plannerCollapsed));
$("#rain-toggle").addEventListener("change", (event) => { state.rainEnabled = event.target.checked; refreshConditionControls(); refreshPresetSelection(); });
$("#closures-toggle").addEventListener("change", (event) => { state.closuresEnabled = event.target.checked; refreshConditionControls(); refreshPresetSelection(); });
$("#closure-radius").addEventListener("input", (event) => { $("#radius-output").value = `${event.target.value} m`; });
$("#closure-list").addEventListener("click", (event) => { const index = event.target.dataset.removeClosure; if (index !== undefined) { state.closures.splice(Number(index), 1); drawClosures(); } });
document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => {
  const preset = button.dataset.preset;
  state.rainEnabled = preset === "heavy_rain";
  state.closuresEnabled = preset === "road_closed";
  refreshConditionControls();
  refreshPresetSelection();
}));
$("#flood-toggle").addEventListener("change", (event) => state.floodLayers.forEach((layer) => event.target.checked ? layer.addTo(map) : map.removeLayer(layer)));
$("#hospital-toggle").addEventListener("change", toggleHospitals);
$("#theme-toggle").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
$("#algorithm-toggle").addEventListener("click", async (event) => {
  const enabled = event.currentTarget.getAttribute("aria-checked") !== "true";
  event.currentTarget.setAttribute("aria-checked", String(enabled)); $("#algorithm-content").classList.toggle("hidden", !enabled);
  if (enabled) await runCompare(); else {
    if (state.animation) { cancelAnimationFrame(state.animation); clearTimeout(state.animation); state.animation = null; }
    if (state.dotLayers) { state.dotLayers.forEach((layer) => map.removeLayer(layer)); state.dotLayers = []; }
    if (state.dots) { map.removeLayer(state.dots); state.dots = null; }
    if (state.comparePath) { map.removeLayer(state.comparePath); state.comparePath = null; }
  }
});
document.querySelectorAll("[data-algorithm]").forEach((button) => button.addEventListener("click", () => {
  document.querySelector("[data-algorithm].selected")?.classList.remove("selected"); button.classList.add("selected");
  state.algorithm = button.dataset.algorithm; updateAlgorithmStats(); replayDots();
}));
$("#legend-toggle").addEventListener("click", (event) => {
  const expanded = event.currentTarget.getAttribute("aria-expanded") !== "true";
  event.currentTarget.setAttribute("aria-expanded", String(expanded));
  $(".mobile-legend").classList.toggle("hidden", !expanded);
});
$("#play-button").addEventListener("click", replayDots);
$("#replay-button").addEventListener("click", replayDots);
$("#speed-slider").addEventListener("input", (event) => { $("#speed-label").textContent = `${event.target.value / 5}×`; });

let searchTimer;
let searchController;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    if (searchController) searchController.abort();
    searchController = new AbortController();
    try {
      const items = await api(`/api/search?q=${encodeURIComponent($("#search").value)}&limit=8`, { signal: searchController.signal });
      $("#suggestions").innerHTML = items.map((item) => `<button role="option" data-lat="${item.lat}" data-lng="${item.lng}">${escapeHtml(item.name)}</button>`).join("");
    } catch (error) { errorMessage(error); }
  }, 220);
});
$("#suggestions").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-lat]"); if (!button) return;
  const point = { lat: Number(button.dataset.lat), lng: Number(button.dataset.lng) };
  setPlace(state.placing, point); map.flyTo([point.lat, point.lng], 16); $("#suggestions").replaceChildren(); $("#search").value = button.textContent;
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape") $("#suggestions").replaceChildren(); });

async function initialize() {
  let savedTheme;
  try { savedTheme = localStorage.getItem("safepassage-theme"); } catch { /* Storage may be disabled. */ }
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(savedTheme || (prefersDark ? "dark" : "light"));
  try {
    const [meta, zones] = await Promise.all([api("/api/meta"), api("/api/flood-zones")]);
    state.meta = meta;
    state.tileConfig = meta.tiles || null;
    const { south, west, north, east } = meta.bbox;
    state.originalBounds = L.latLngBounds([south, west], [north, east]);
    const margin = 0.15;
    map.setMaxBounds(L.latLngBounds([south - margin, west - margin], [north + margin, east + margin]));
    map.setMinZoom(11);
    map.on("drag", () => map.panInsideBounds(map.options.maxBounds, { animate: false }));
    map.fitBounds(state.originalBounds);
    refreshTiles();
    $("#empty-hint").classList.toggle("hidden", Boolean(state.origin));
    $("#attribution").textContent = meta.data_attribution; drawZones(zones.zones);
  } catch (error) { errorMessage(error); }
}
initialize();
