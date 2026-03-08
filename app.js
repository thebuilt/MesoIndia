const CONFIG = {
  casesUrl: "./data/meso_cases.geojson",
  statesUrl: "./data/india-states-simplified.geojson",
  districtsUrl: "./data/india-districts-simplified.geojson",
  issueRepoUrl: "https://github.com/thebuilt/MesoIndia",
};

const state = {
  features: [],
  filtered: [],
  markers: null,
  statesLayer: null,
  districtsLayer: null,
  showDistricts: false,
  heatLayer: null,
  showHeatmap: true,
  map: null,
};

const STATE_ALIASES = {
  "j&k-ut": "Jammu and Kashmir",
  "delhi-ut": "Delhi",
  "nct of delhi": "Delhi",
  "orissa": "Odisha",
};

const colorBySource = {
  "Hospital Registry": "#d2552f",
  "PBCR": "#7a4cc2",
  "NCBI Literature": "#1c7ed6",
  "Community Verified": "#2b8a3e",
};

const dom = {
  kpiCases: document.getElementById("kpi-cases"),
  kpiSites: document.getElementById("kpi-sites"),
  kpiStates: document.getElementById("kpi-states"),
  kpiUpdated: document.getElementById("kpi-updated"),
  search: document.getElementById("search"),
  stateFilter: document.getElementById("state-filter"),
  srcToggles: Array.from(document.querySelectorAll(".src-toggle")),
  mesoFilter: document.getElementById("meso-filter"),
  minYear: document.getElementById("min-year"),
  records: document.getElementById("records"),
  toggleDistricts: document.getElementById("toggle-districts"),
  toggleHeatmap: document.getElementById("toggle-heatmap"),
  heatSourceFilter: document.getElementById("heat-source-filter"),
  loadbox: document.getElementById("loadbox"),
  loadtext: document.getElementById("loadtext"),
  loadfill: document.getElementById("loadfill"),
  submitReport: document.getElementById("submit-report"),
  rHospital: document.getElementById("r-hospital"),
  rCity: document.getElementById("r-city"),
  rState: document.getElementById("r-state"),
  rYear: document.getElementById("r-year"),
  rCount: document.getElementById("r-count"),
  rLink: document.getElementById("r-link"),
};

function norm(v) {
  return String(v || "").toLowerCase().trim();
}

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

function sourceColor(src) {
  return colorBySource[src] || "#4e6875";
}

function setLoading(visible, text = "Loading...", pct = null) {
  if (!dom.loadbox) return;
  dom.loadbox.classList.toggle("visible", !!visible);
  dom.loadtext.textContent = text;
  if (typeof pct === "number") {
    const x = Math.max(0, Math.min(100, pct));
    dom.loadfill.style.width = `${x}%`;
  } else if (!visible) {
    dom.loadfill.style.width = "0%";
  }
}

function canonicalStateName(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const low = v.toLowerCase();
  return STATE_ALIASES[low] || v;
}

function enabledSources() {
  const active = new Set();
  dom.srcToggles.forEach((cb) => {
    if (cb.checked) active.add(cb.value);
  });
  return active;
}

function pointMatches(feature) {
  const p = feature.properties || {};
  const search = norm(dom.search.value);
  const stateFilter = norm(dom.stateFilter.value);
  const mesoFilter = norm(dom.mesoFilter.value);
  const minYear = Number(dom.minYear.value || "0");
  const sources = enabledSources();

  if (sources.size && !sources.has(p.source_type)) return false;
  if (stateFilter && norm(p.state) !== stateFilter) return false;
  if (mesoFilter && norm(p.meso_type) !== mesoFilter) return false;
  if ((Number(p.year_end) || 0) < minYear) return false;

  if (!search) return true;
  const blob = [
    p.hospital,
    p.city,
    p.state,
    p.study_or_registry,
    p.title,
    p.pmid,
    p.pmcid,
    p.notes,
  ].map(norm).join(" ");

  return blob.includes(search);
}

function refresh() {
  state.filtered = state.features.filter(pointMatches);
  renderMarkers();
  renderHeatmap();
  renderList();
  renderKpis();
  updateStateChoropleth();
}

function renderKpis() {
  const uniqueSites = new Set(state.filtered.map((f) => f.properties.hospital || f.properties.record_id));
  const uniqueStates = new Set(state.filtered.map((f) => f.properties.state).filter(Boolean));
  const caseSum = state.filtered.reduce((acc, f) => acc + (Number(f.properties.case_count) || 0), 0);

  dom.kpiCases.textContent = caseSum.toLocaleString();
  dom.kpiSites.textContent = uniqueSites.size.toLocaleString();
  dom.kpiStates.textContent = uniqueStates.size.toLocaleString();
}

function popupHtml(p) {
  return `
    <strong>${p.hospital || "Unknown hospital"}</strong><br>
    ${p.city || ""}${p.city && p.state ? ", " : ""}${p.state || ""}<br>
    <small>${p.source_type || "Unknown source"} | Cases: ${p.case_count || 1} | ${p.year_start || "-"}-${p.year_end || "-"}</small><br>
    <small>Meso type: ${p.meso_type || "All"} | ICD-10: ${p.icd10 || "C45"}</small><br>
    ${p.provenance_url ? `<a href="${p.provenance_url}" target="_blank" rel="noopener">Source</a>` : ""}
  `;
}

function renderMarkers() {
  if (state.markers) state.markers.clearLayers();

  state.filtered.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const color = sourceColor(p.source_type);
    const caseCount = Number(p.case_count) || 1;
    const radius = Math.min(22, Math.max(5, 4 + Math.log1p(caseCount) * 2.6));

    const marker = L.circleMarker([lat, lon], {
      radius,
      color,
      fillColor: color,
      fillOpacity: 0.75,
      weight: 1,
    }).bindPopup(popupHtml(p));

    marker.addTo(state.markers);
  });
}

function renderList() {
  dom.records.innerHTML = "";
  if (!state.filtered.length) {
    dom.records.innerHTML = "<li>No records match the current filters.</li>";
    return;
  }

  const frag = document.createDocumentFragment();
  state.filtered
    .sort((a, b) => (Number(b.properties.case_count) || 0) - (Number(a.properties.case_count) || 0))
    .forEach((f) => {
      const p = f.properties;
      const li = document.createElement("li");
      li.innerHTML = `
        <strong>${p.hospital || "Unknown hospital"}</strong>
        <div class="meta">${p.city || ""}${p.city && p.state ? ", " : ""}${p.state || ""} | ${p.source_type || "Unknown"}</div>
        <div class="meta">Cases: ${p.case_count || 1} | ${p.year_start || "-"}-${p.year_end || "-"} | ${p.meso_type || "All"}</div>
      `;
      li.addEventListener("click", () => {
        const [lon, lat] = f.geometry.coordinates;
        state.map.setView([lat, lon], 8);
      });
      frag.appendChild(li);
    });
  dom.records.appendChild(frag);
}

function renderHeatmap() {
  if (!state.heatLayer) return;
  if (!state.showHeatmap) {
    state.map.removeLayer(state.heatLayer);
    return;
  }

  const heatSource = dom.heatSourceFilter?.value || "all";
  const points = [];
  state.filtered
    .filter((f) => heatSource === "all" || (f.properties?.source_type === heatSource))
    .forEach((f) => {
      const [lon, lat] = f.geometry.coordinates;
      const c = Number(f.properties.case_count) || 1;
      const intensity = Math.min(1, Math.max(0.35, Math.log1p(c) / Math.log(60)));
      const repeats = Math.min(60, Math.max(3, Math.ceil(Math.sqrt(c) * 1.8)));
      const spread = Math.min(0.18, 0.03 + Math.log1p(c) * 0.02);
      for (let i = 0; i < repeats; i += 1) {
        const ang = (i / repeats) * Math.PI * 2;
        const dLat = spread * Math.sin(ang);
        const dLon = (spread * Math.cos(ang)) / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
        points.push([lat + dLat, lon + dLon, intensity]);
      }
    });

  state.heatLayer.setLatLngs(points);
  if (!state.map.hasLayer(state.heatLayer)) state.heatLayer.addTo(state.map);
}

function buildStateCounts() {
  const counts = {};
  state.filtered.forEach((f) => {
    const s = canonicalStateName(f.properties.state);
    if (!s) return;
    counts[s] = (counts[s] || 0) + (Number(f.properties.case_count) || 0);
  });
  return counts;
}

function fillStateFilter() {
  const states = [...new Set(state.features.map((f) => f.properties.state).filter(Boolean))].sort();
  dom.stateFilter.innerHTML = `<option value="">All</option>${states.map((s) => `<option value="${s}">${s}</option>`).join("")}`;
}

function updateStateChoropleth() {
  if (!state.statesLayer) return;
  const counts = buildStateCounts();

  state.statesLayer.eachLayer((layer) => {
    const rawName = layer.feature?.properties?.NAME_1 || layer.feature?.properties?.STATE || layer.feature?.properties?.st_nm || layer.feature?.properties?.name || layer.feature?.properties?.STATE_RAW || "";
    const sName = canonicalStateName(rawName) || "Unknown region";
    const val = counts[sName] || 0;
    layer.setStyle({
      fillColor: val > 200 ? "#6a040f" : val > 50 ? "#dc2f02" : val > 10 ? "#f48c06" : val > 0 ? "#ffba08" : "#dce8ec",
      fillOpacity: 0.42,
      color: "#4f6b77",
      weight: 1.1,
    });
    layer.bindTooltip(`${sName}: ${val} visible cases`);
  });
}

async function initMap() {
  setLoading(true, "Initializing map...", 8);
  state.map = L.map("map", {
    zoomControl: true,
    minZoom: 4,
    maxZoom: 10,
    maxBoundsViscosity: 1.0,
  }).setView([22.8, 79.6], 5);

  state.markers = L.layerGroup().addTo(state.map);
  state.map.createPane("heatPane");
  state.map.getPane("heatPane").style.zIndex = "420";
  if (typeof L.heatLayer === "function") {
    state.heatLayer = L.heatLayer([], {
      pane: "heatPane",
      radius: 46,
      blur: 32,
      maxZoom: 9,
      minOpacity: 0.72,
      gradient: {
        0.15: "#1d4ed8",
        0.35: "#16a34a",
        0.58: "#f59e0b",
        0.82: "#ef4444",
        1.0: "#7f1d1d",
      },
    });
  }

  setLoading(true, "Loading mesothelioma records...", 28);
  const [casesRes, statesRes] = await Promise.all([fetch(CONFIG.casesUrl), fetch(CONFIG.statesUrl)]);
  setLoading(true, "Parsing boundary layers...", 62);
  const casesJson = await casesRes.json();
  const statesGeo = await statesRes.json();

  state.features = casesJson.features || [];
  dom.kpiUpdated.textContent = formatDate(casesJson.meta?.generated_at);

  state.statesLayer = L.geoJSON(statesGeo, {
    style: {
      fillColor: "#eef4f7",
      fillOpacity: 0.82,
      color: "#4f6b77",
      weight: 1.2,
    },
  }).addTo(state.map);

  const indiaBounds = state.statesLayer.getBounds();
  state.map.fitBounds(indiaBounds, { padding: [12, 12] });
  state.map.setMaxBounds(indiaBounds.pad(0.2));

  fillStateFilter();
  dom.toggleHeatmap.textContent = state.showHeatmap ? "Hide Heatmap" : "Show Heatmap";
  setLoading(true, "Rendering layers...", 90);
  refresh();
  setLoading(false, "Ready", 100);
}

async function toggleDistrictLayer() {
  state.showDistricts = !state.showDistricts;
  dom.toggleDistricts.textContent = state.showDistricts ? "Hide Districts" : "Show Districts";

  if (!state.showDistricts) {
    if (state.districtsLayer) state.map.removeLayer(state.districtsLayer);
    return;
  }

  if (!state.districtsLayer) {
    setLoading(true, "Loading district boundaries...", 35);
    const res = await fetch(CONFIG.districtsUrl);
    setLoading(true, "Parsing district boundaries...", 68);
    const geo = await res.json();
    state.districtsLayer = L.geoJSON(geo, {
      style: {
        color: "#7f8f99",
        weight: 0.45,
        opacity: 0.8,
        fillOpacity: 0,
      },
      interactive: false,
    });
    setLoading(true, "Rendering district boundaries...", 92);
  }
  state.districtsLayer.addTo(state.map);
  setLoading(false, "Ready", 100);
}

function initEvents() {
  [dom.search, dom.stateFilter, dom.mesoFilter, dom.minYear, dom.heatSourceFilter].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });
  dom.srcToggles.forEach((cb) => {
    cb.addEventListener("change", refresh);
  });

  dom.toggleDistricts.addEventListener("click", () => {
    toggleDistrictLayer().catch((err) => console.error("district layer failed", err));
  });

  dom.toggleHeatmap.addEventListener("click", () => {
    state.showHeatmap = !state.showHeatmap;
    dom.toggleHeatmap.textContent = state.showHeatmap ? "Hide Heatmap" : "Show Heatmap";
    refresh();
  });

  dom.submitReport.addEventListener("click", () => {
    const title = `[Community Meso Site] ${dom.rHospital.value || "Unknown hospital"} - ${dom.rCity.value || "Unknown city"}`;
    const body = [
      "## Community Mesothelioma Site Report",
      `- Hospital: ${dom.rHospital.value || ""}`,
      `- City: ${dom.rCity.value || ""}`,
      `- State: ${dom.rState.value || ""}`,
      `- Year: ${dom.rYear.value || ""}`,
      `- Approx case count: ${dom.rCount.value || "1"}`,
      `- ICD-10: C45`,
      `- Evidence link: ${dom.rLink.value || ""}`,
      "- Notes:"
    ].join("\n");

    const issueUrl = `${CONFIG.issueRepoUrl}/issues/new?labels=community-case,needs-review&title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
    window.open(issueUrl, "_blank", "noopener");
  });
}

initEvents();
initMap().catch((err) => {
  console.error(err);
  dom.records.innerHTML = `<li>Failed to load dataset: ${String(err)}</li>`;
});
