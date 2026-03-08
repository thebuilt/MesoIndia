const CONFIG = {
  casesUrl: "./data/meso_cases.geojson",
  statesUrl: "./data/india-states-simplified.geojson",
  issueRepoUrl: "https://github.com/thebuilt/MesoIndia",
};

const state = {
  features: [],
  filtered: [],
  showCatchment: false,
  markers: null,
  circles: null,
  statesLayer: null,
  map: null,
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
  sourceFilter: document.getElementById("source-filter"),
  mesoFilter: document.getElementById("meso-filter"),
  minYear: document.getElementById("min-year"),
  records: document.getElementById("records"),
  toggleCatchment: document.getElementById("toggle-catchment"),
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

function pointMatches(feature) {
  const p = feature.properties || {};
  const search = norm(dom.search.value);
  const stateFilter = norm(dom.stateFilter.value);
  const sourceFilter = norm(dom.sourceFilter.value);
  const mesoFilter = norm(dom.mesoFilter.value);
  const minYear = Number(dom.minYear.value || "0");

  if (sourceFilter && norm(p.source_type) !== sourceFilter) return false;
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
  if (state.circles) state.circles.clearLayers();

  state.filtered.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const color = sourceColor(p.source_type);

    const marker = L.circleMarker([lat, lon], {
      radius: 6,
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 1,
    }).bindPopup(popupHtml(p));

    marker.addTo(state.markers);

    if (state.showCatchment && Number(p.catchment_km) > 0) {
      L.circle([lat, lon], {
        radius: Number(p.catchment_km) * 1000,
        color,
        fillOpacity: 0.06,
        weight: 1,
      }).addTo(state.circles);
    }
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

function buildStateCounts() {
  const counts = {};
  state.filtered.forEach((f) => {
    const s = f.properties.state || "Unknown";
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
    const sName = layer.feature?.properties?.st_nm || layer.feature?.properties?.name || "";
    const val = counts[sName] || 0;
    layer.setStyle({
      fillColor: val > 200 ? "#6a040f" : val > 50 ? "#dc2f02" : val > 10 ? "#f48c06" : val > 0 ? "#ffba08" : "#dce8ec",
      fillOpacity: 0.35,
      color: "#6e8d9a",
      weight: 0.8,
    });
    layer.bindTooltip(`${sName}: ${val} visible cases`);
  });
}

async function initMap() {
  state.map = L.map("map", { zoomControl: true }).setView([22.8, 79.6], 5);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(state.map);

  state.markers = L.layerGroup().addTo(state.map);
  state.circles = L.layerGroup().addTo(state.map);

  const [casesRes, statesRes] = await Promise.all([fetch(CONFIG.casesUrl), fetch(CONFIG.statesUrl)]);
  const casesJson = await casesRes.json();
  const statesGeo = await statesRes.json();

  state.features = casesJson.features || [];
  dom.kpiUpdated.textContent = formatDate(casesJson.meta?.generated_at);

  state.statesLayer = L.geoJSON(statesGeo, {
    style: {
      fillColor: "#dce8ec",
      fillOpacity: 0.35,
      color: "#6e8d9a",
      weight: 0.8,
    },
  }).addTo(state.map);

  fillStateFilter();
  refresh();
}

function initEvents() {
  [dom.search, dom.stateFilter, dom.sourceFilter, dom.mesoFilter, dom.minYear].forEach((el) => {
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });

  dom.toggleCatchment.addEventListener("click", () => {
    state.showCatchment = !state.showCatchment;
    dom.toggleCatchment.textContent = state.showCatchment ? "Hide Catchment" : "Show Catchment";
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
