const DATA_URL = "data/entries.min.json";
const SOURCE_PREFIX =
  "Source: Clinton Library, Clinton Presidential Records, National Security Council";
const INITIAL_RESULTS = 1000;
const RESULTS_BATCH = 1000;
const SCROLL_LOAD_MARGIN = 1400;

const state = {
  entries: [],
  matches: [],
  query: "",
  queryTerms: [],
  part: "all",
  office: "all",
  quality: "all",
  visible: [],
  renderedCount: 0,
  renderQueued: false,
};

const els = {
  entryCount: document.querySelector("#entryCount"),
  pageCount: document.querySelector("#pageCount"),
  restrictionCount: document.querySelector("#restrictionCount"),
  search: document.querySelector("#searchInput"),
  part: document.querySelector("#partFilter"),
  office: document.querySelector("#officeFilter"),
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
  return String(folder);
}

function sourceNote(entry) {
  if (entry.note) return entry.note;
  const source = `${SOURCE_PREFIX}, ${entry.office}, OA/ID ${entry.oa}, ${folderForSource(entry.folder)}`;
  return /[.?!]$/.test(source) ? source : `${source}.`;
}

function hasReviewFlag(entry) {
  return Array.isArray(entry.flags) && entry.flags.length > 0;
}

function populateOfficeFilter(entries) {
  const offices = [...new Set(entries.map((entry) => entry.office).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
  offices.forEach((office) => {
    const option = document.createElement("option");
    option.value = office;
    option.textContent = office;
    els.office.appendChild(option);
  });
}

function matchesQuality(entry) {
  if (state.quality === "all") return true;
  if (state.quality === "review") return hasReviewFlag(entry);
  if (state.quality === "no-office") return entry.office === "[office or series not legible in finding aid]";
  if (state.quality === "restriction") return Array.isArray(entry.rest) && entry.rest.length > 0;
  return true;
}

function matchesQuery(entry) {
  if (!state.queryTerms.length) return true;
  return state.queryTerms.every((term) => entry.haystack.includes(term));
}

function matchesPart(entry) {
  return state.part === "all" || String(entry.p) === state.part;
}

function matchesOffice(entry) {
  return state.office === "all" || entry.office === state.office;
}

function applyFilters() {
  state.matches = state.entries.filter(
    (entry) => matchesPart(entry) && matchesOffice(entry) && matchesQuality(entry) && matchesQuery(entry),
  );
  state.visible = [];
  state.renderedCount = 0;
  els.body.replaceChildren();
  appendResults(INITIAL_RESULTS);
}

function updateResultCount() {
  const totalMatches = state.matches.length;
  const shown = state.visible.length;
  const showingText = shown === totalMatches ? `showing all ${formatNumber(shown)}` : `showing ${formatNumber(shown)}`;
  els.resultCount.textContent = `${formatNumber(totalMatches)} matches; ${showingText}`;
}

function appendResults(count) {
  const totalMatches = state.matches.length;

  if (!totalMatches) {
    updateResultCount();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty";
    cell.textContent = "No matching entries.";
    row.appendChild(cell);
    els.body.appendChild(row);
    return;
  }

  const nextEntries = state.matches.slice(state.renderedCount, state.renderedCount + count);
  state.visible.push(...nextEntries);
  state.renderedCount += nextEntries.length;

  const fragment = document.createDocumentFragment();
  nextEntries.forEach((entry) => {
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
  updateResultCount();
  queueScrollCheck();
}

function hasMoreResults() {
  return state.renderedCount < state.matches.length;
}

function nearPageBottom() {
  const scrollBottom = window.scrollY + window.innerHeight;
  return document.documentElement.scrollHeight - scrollBottom < SCROLL_LOAD_MARGIN;
}

function queueScrollCheck() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  requestAnimationFrame(() => {
    state.renderQueued = false;
    if (hasMoreResults() && nearPageBottom()) {
      appendResults(RESULTS_BATCH);
    }
  });
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
    haystack:
      `${entry.note || ""} ${entry.oa} ${entry.office} ${entry.folder} ${entry.loc} ${
        entry.flags?.join(" ") || ""
      }`.toLowerCase(),
  }));

  els.entryCount.textContent = formatNumber(summary.entry_count || state.entries.length);
  els.pageCount.textContent = formatNumber(summary.pages_processed || 1290);
  els.restrictionCount.textContent = formatNumber(summary.entries_with_restriction_markers || 0);
  populateOfficeFilter(state.entries);
  applyFilters();
}

els.search.addEventListener(
  "input",
  debounce((event) => {
    state.query = event.target.value.trim().toLowerCase();
    state.queryTerms = state.query.split(/\s+/).filter(Boolean);
    applyFilters();
  }),
);

els.part.addEventListener("change", (event) => {
  state.part = event.target.value;
  applyFilters();
});

els.office.addEventListener("change", (event) => {
  state.office = event.target.value;
  applyFilters();
});

els.quality.addEventListener("change", (event) => {
  state.quality = event.target.value;
  applyFilters();
});

els.reset.addEventListener("click", () => {
  state.query = "";
  state.queryTerms = [];
  state.part = "all";
  state.office = "all";
  state.quality = "all";
  els.search.value = "";
  els.part.value = "all";
  els.office.value = "all";
  els.quality.value = "all";
  els.copyStatus.textContent = "";
  applyFilters();
});

window.addEventListener(
  "scroll",
  () => {
    if (hasMoreResults() && nearPageBottom()) {
      appendResults(RESULTS_BATCH);
    }
  },
  { passive: true },
);

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
