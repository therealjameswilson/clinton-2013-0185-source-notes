const DATA_URL = "data/entries.min.json";
const SOURCE_PREFIX =
  "Source: William J. Clinton Presidential Library, Clinton Presidential Records, National Security Council, 2013-0185-M";
const MAX_RESULTS = 250;

const state = {
  entries: [],
  query: "",
  part: "all",
  quality: "all",
  visible: [],
};

const els = {
  entryCount: document.querySelector("#entryCount"),
  pageCount: document.querySelector("#pageCount"),
  restrictionCount: document.querySelector("#restrictionCount"),
  search: document.querySelector("#searchInput"),
  part: document.querySelector("#partFilter"),
  quality: document.querySelector("#qualityFilter"),
  reset: document.querySelector("#resetFilters"),
  copyVisible: document.querySelector("#copyVisible"),
  copyStatus: document.querySelector("#copyStatus"),
  resultCount: document.querySelector("#resultCount"),
  body: document.querySelector("#resultsBody"),
  rowTemplate: document.querySelector("#rowTemplate"),
};

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function folderForSource(folder) {
  if (folder === "[folder title withheld in finding aid]") return "folder title withheld in finding aid";
  return `folder "${String(folder).replaceAll('"', "'")}"`;
}

function sourceNote(entry) {
  const base = `${SOURCE_PREFIX}, ${entry.office}, OA/ID ${entry.oa}, ${folderForSource(entry.folder)}.`;
  if (!entry.rest || !entry.rest.length) return base;
  return `${base} Finding aid restriction marker: ${entry.rest.join("; ")}.`;
}

function hasReviewFlag(entry) {
  return Array.isArray(entry.flags) && entry.flags.length > 0;
}

function matchesQuality(entry) {
  if (state.quality === "all") return true;
  if (state.quality === "review") return hasReviewFlag(entry);
  if (state.quality === "no-office") return entry.office === "[office or series not legible in finding aid]";
  if (state.quality === "restriction") return Array.isArray(entry.rest) && entry.rest.length > 0;
  return true;
}

function matchesQuery(entry) {
  if (!state.query) return true;
  return entry.haystack.includes(state.query);
}

function matchesPart(entry) {
  return state.part === "all" || String(entry.p) === state.part;
}

function applyFilters() {
  const matches = state.entries.filter((entry) => matchesPart(entry) && matchesQuality(entry) && matchesQuery(entry));
  state.visible = matches.slice(0, MAX_RESULTS);
  renderResults(matches.length);
}

function renderResults(totalMatches) {
  els.body.replaceChildren();
  els.resultCount.textContent = `${formatNumber(totalMatches)} matches; showing ${formatNumber(state.visible.length)}`;

  if (!state.visible.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty";
    cell.textContent = "No matching entries.";
    row.appendChild(cell);
    els.body.appendChild(row);
    return;
  }

  const fragment = document.createDocumentFragment();
  state.visible.forEach((entry) => {
    const row = els.rowTemplate.content.firstElementChild.cloneNode(true);
    const note = sourceNote(entry);
    row.querySelector(".source-note").textContent = note;
    row.querySelector(".oa-cell").textContent = entry.oa;
    row.querySelector(".part-cell").textContent = `Part ${entry.p}`;
    row.querySelector(".page-cell").textContent = entry.pg;

    const meta = row.querySelector(".row-meta");
    meta.textContent = `${entry.loc}.`;
    if (hasReviewFlag(entry)) {
      const flags = document.createElement("strong");
      flags.textContent = ` Review: ${entry.flags.join(", ")}.`;
      meta.appendChild(flags);
    }
    if (entry.rest && entry.rest.length) {
      meta.append(` Restrictions: ${entry.rest.join("; ")}.`);
    }

    row.querySelector(".copy-row").addEventListener("click", () => {
      copyText(note, "Copied one source note.");
    });
    fragment.appendChild(row);
  });
  els.body.appendChild(fragment);
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    els.copyStatus.textContent = successMessage;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    els.copyStatus.textContent = successMessage;
  }
}

function debounce(fn, delay = 120) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function loadData() {
  const response = await fetch(DATA_URL);
  if (!response.ok) throw new Error(`Could not load ${DATA_URL}`);
  const payload = await response.json();
  const summary = payload.summary || {};
  state.entries = (payload.entries || []).map((entry) => ({
    ...entry,
    haystack: `${entry.oa} ${entry.office} ${entry.folder} ${entry.loc} ${entry.flags?.join(" ") || ""}`.toLowerCase(),
  }));

  els.entryCount.textContent = formatNumber(summary.entry_count || state.entries.length);
  els.pageCount.textContent = formatNumber(summary.pages_processed || 1290);
  els.restrictionCount.textContent = formatNumber(summary.entries_with_restriction_markers || 0);
  applyFilters();
}

els.search.addEventListener(
  "input",
  debounce((event) => {
    state.query = event.target.value.trim().toLowerCase();
    applyFilters();
  }),
);

els.part.addEventListener("change", (event) => {
  state.part = event.target.value;
  applyFilters();
});

els.quality.addEventListener("change", (event) => {
  state.quality = event.target.value;
  applyFilters();
});

els.reset.addEventListener("click", () => {
  state.query = "";
  state.part = "all";
  state.quality = "all";
  els.search.value = "";
  els.part.value = "all";
  els.quality.value = "all";
  els.copyStatus.textContent = "";
  applyFilters();
});

els.copyVisible.addEventListener("click", () => {
  const notes = state.visible.map(sourceNote).join("\n");
  if (!notes) return;
  copyText(notes, `Copied ${formatNumber(state.visible.length)} source notes.`);
});

loadData().catch((error) => {
  els.resultCount.textContent = "Unable to load entries.";
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.className = "empty";
  cell.textContent = error.message;
  row.appendChild(cell);
  els.body.appendChild(row);
});
