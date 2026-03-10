const state = {
  kaseya: { page: 1, pageSize: 8, search: "", totalPages: 1, coverageFilter: "all", lastUpdatedBefore: "" },
  revnue: { page: 1, pageSize: 8, search: "", totalPages: 1 },
  selectedIdentifiers: new Set(),
  onlyMissing: false,
  logs: { notifications: [], messages: [], unreadCount: 0 },
  coverage: { items: [], staleDays: 7 },
  dryRun: { previewViewed: false, previewSyncReady: false, identifiers: [], selectionKey: "" },
  assetDetail: { open: false, identifier: "" },
};

const COVERAGE_CARD_META = {
  total: { valueId: "coverage-total-value", subId: "coverage-total-sub" },
  synced: { valueId: "coverage-synced-value", subId: "coverage-synced-sub" },
  missing: { valueId: "coverage-missing-value", subId: "coverage-missing-sub" },
  stale: { valueId: "coverage-stale-value", subId: "coverage-stale-sub" },
  failed: { valueId: "coverage-failed-value", subId: "coverage-failed-sub" },
};

let coverageFetchPromise = null;

const $ = (id) => document.getElementById(id);

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function setLoading(show) {
  $("loading-overlay").classList.toggle("show", show);
}

function notify(message, type = "info") {
  const root = $("toast-root");
  if (!root) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  root.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 2800);
}

function setButtonBusy(button, busy) {
  if (!button) return;
  button.classList.toggle("is-busy", busy);
}

function formatDate(isoDate) {
  if (!isoDate) return "-";
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed.toLocaleString();
}

function formatStatusLabel(value) {
  if (!value) return "Unknown";
  const normalized = String(value).trim().toLowerCase();
  if (normalized === "partial") return "Needs review";
  if (normalized === "failed" || normalized === "error") return "Failed";
  if (normalized === "warning") return "Warning";
  if (normalized === "info") return "Info";
  if (normalized === "success") return "Success";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

const HEALTH_DOT_VARIANTS = ["health-dot--healthy", "health-dot--degraded", "health-dot--critical", "health-dot--unknown"];

function circuitState(snapshot) {
  if (snapshot && typeof snapshot === "object") {
    if (snapshot.circuit_open === true) return "open";
    if (snapshot.circuit_open === false) return "closed";
    const state = String(snapshot.state || snapshot.status || "").toLowerCase();
    if (state.includes("open")) return "open";
    if (state.includes("close")) return "closed";
    if (state) return state;
  }
  return "unknown";
}

function resilienceEntries(payload) {
  const raw = payload?.resilience || payload?.checks?.circuit_breakers || payload?.checks?.resilience || {};
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw).map(([service, snapshot]) => ({
    service,
    state: circuitState(snapshot),
  }));
}

function setHealthDotVariant(variant, titleText) {
  const dot = $("health-dot");
  if (!dot) return;
  dot.classList.remove(...HEALTH_DOT_VARIANTS);
  dot.classList.add(`health-dot--${variant}`);
  dot.setAttribute("title", titleText);
}

async function updateHealthDot() {
  try {
    const payload = await apiFetch("/api/health");
    const circuits = resilienceEntries(payload);
    if (!circuits.length) {
      setHealthDotVariant("unknown", "No circuit breaker data available.");
      return;
    }
    const openCount = circuits.filter((entry) => entry.state === "open").length;
    const variant =
      openCount === 0 ? "healthy" : openCount === circuits.length ? "critical" : "degraded";
    const titleText = circuits.map((entry) => `${entry.service}: ${entry.state}`).join(" | ");
    setHealthDotVariant(variant, titleText);
  } catch (error) {
    setHealthDotVariant("critical", `Health check failed: ${error.message}`);
  }
}

function setAutosyncButton(enabled) {
  const button = $("autosync-navbar-toggle");
  if (!button) return;
  const label = button.querySelector(".topbar-label");
  if (label) {
    label.textContent = `Auto Sync: ${enabled ? "On" : "Off"}`;
  }
  button.classList.toggle("is-on", enabled);
  button.setAttribute("aria-pressed", enabled ? "true" : "false");
}

function setSyncRunStatus(message) {
  const status = $("sync-run-status");
  if (!status) return;
  status.textContent = message;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setSelectionValidation(message = "") {
  const element = $("selection-validation-message");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("text-danger", !!message);
}

function currentSelectionIdentifiers() {
  return Array.from(state.selectedIdentifiers).sort();
}

function selectionKey(identifiers) {
  return identifiers.join("|");
}

function resetDryRunState() {
  state.dryRun.previewViewed = false;
  state.dryRun.previewSyncReady = false;
  state.dryRun.identifiers = [];
  state.dryRun.selectionKey = "";
}

function refreshDryRunSelectionState() {
  const currentKey = selectionKey(currentSelectionIdentifiers());
  if (state.dryRun.selectionKey && state.dryRun.selectionKey !== currentKey) {
    resetDryRunState();
  }
  updateDryRunConfirmVisibility();
}

function setCoverageCard(metric, value, subtitle) {
  const meta = COVERAGE_CARD_META[metric];
  if (!meta) return;
  const valueEl = $(meta.valueId);
  const subEl = $(meta.subId);
  if (valueEl) valueEl.textContent = String(value);
  if (subEl) subEl.textContent = subtitle;
}

function setCoverageLoading() {
  setCoverageCard("total", "—", "Loading coverage...");
  setCoverageCard("synced", "—", "Loading coverage...");
  setCoverageCard("missing", "—", "Loading coverage...");
  setCoverageCard("stale", "—", "Loading coverage...");
  setCoverageCard("failed", "—", "Loading coverage...");
}

function updateCoverageCardSelection() {
  document.querySelectorAll("[data-coverage-filter]").forEach((card) => {
    const filter = card.getAttribute("data-coverage-filter") || "";
    let isActive = state.kaseya.coverageFilter === filter;
    if (filter === "missing") {
      isActive = state.onlyMissing && state.kaseya.coverageFilter === "missing";
    }
    card.classList.toggle("stat-card--active", isActive);
  });
}

function parseIsoTimestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isFinite(parsed) ? parsed : null;
}

function isStaleAsset(asset, cutoffMs) {
  const modifiedMs = parseIsoTimestamp(asset?.ModifiedDate);
  if (modifiedMs === null) return false;
  return modifiedMs < cutoffMs;
}

function matchesKaseyaSearch(asset, searchText) {
  if (!searchText) return true;
  return (
    (asset?.Identifier || "").toLowerCase().includes(searchText) ||
    (asset?.Name || "").toLowerCase().includes(searchText) ||
    (asset?.Manufacturer || "").toLowerCase().includes(searchText) ||
    (asset?.Model || "").toLowerCase().includes(searchText)
  );
}

function hasFailureSignal(entry) {
  const candidates = [
    entry?.last_sync_status,
    entry?.sync_status,
    entry?.match_status,
    entry?.kaseya_asset?.last_sync_status,
    entry?.kaseya_asset?.sync_status,
  ];
  return candidates.some((candidate) => {
    const value = String(candidate || "").toLowerCase();
    return value.includes("failed") || value.includes("error") || value.includes("partial");
  });
}

function paginateItems(items, page, pageSize) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const normalizedPage = Math.min(Math.max(page, 1), totalPages);
  const start = (normalizedPage - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page: normalizedPage,
    totalPages,
    total,
  };
}

async function fetchCoverageComparison(forceRefresh = false) {
  if (forceRefresh) {
    state.coverage.items = [];
  }
  if (state.coverage.items.length && !forceRefresh) {
    return state.coverage.items;
  }
  if (coverageFetchPromise) {
    return coverageFetchPromise;
  }
  coverageFetchPromise = apiFetch("/api/assets/compare")
    .then((data) => {
      state.coverage.items = Array.isArray(data.items) ? data.items : [];
      return state.coverage.items;
    })
    .finally(() => {
      coverageFetchPromise = null;
    });
  return coverageFetchPromise;
}

function filterCoverageAssets(comparisonItems) {
  const searchText = state.kaseya.search.trim().toLowerCase();
  const staleCutoffMs =
    parseIsoTimestamp(state.kaseya.lastUpdatedBefore) ??
    Date.now() - state.coverage.staleDays * 24 * 60 * 60 * 1000;

  return comparisonItems
    .filter((entry) => {
      const status = String(entry.match_status || "").toLowerCase();
      if (state.kaseya.coverageFilter === "synced" && status !== "matched") {
        return false;
      }
      if (state.kaseya.coverageFilter === "failed" && !hasFailureSignal(entry)) {
        return false;
      }
      if (state.kaseya.coverageFilter === "stale" && !isStaleAsset(entry.kaseya_asset, staleCutoffMs)) {
        return false;
      }
      if (state.onlyMissing && status !== "missing_in_revnue") {
        return false;
      }
      return true;
    })
    .map((entry) => entry.kaseya_asset || {})
    .filter((asset) => !!asset.Identifier)
    .filter((asset) => matchesKaseyaSearch(asset, searchText));
}

function applyCoverageFilter(filter) {
  const staleCutoffIso = new Date(Date.now() - state.coverage.staleDays * 24 * 60 * 60 * 1000).toISOString();
  if (filter === "missing") {
    state.onlyMissing = true;
    state.kaseya.coverageFilter = "missing";
    state.kaseya.lastUpdatedBefore = "";
  } else if (filter === "stale") {
    state.onlyMissing = false;
    state.kaseya.coverageFilter = "stale";
    state.kaseya.lastUpdatedBefore = staleCutoffIso;
  } else if (filter === "synced") {
    state.onlyMissing = false;
    state.kaseya.coverageFilter = "synced";
    state.kaseya.lastUpdatedBefore = "";
  } else if (filter === "failed") {
    state.onlyMissing = false;
    state.kaseya.coverageFilter = "failed";
    state.kaseya.lastUpdatedBefore = "";
  } else {
    state.onlyMissing = false;
    state.kaseya.coverageFilter = "all";
    state.kaseya.lastUpdatedBefore = "";
  }

  $("only-missing-toggle").checked = state.onlyMissing;
  state.kaseya.page = 1;
  updateCoverageCardSelection();
  withLoading(loadKaseyaAssets);
}

function diffActionLabel(action, status) {
  const normalizedAction = String(action || "").toLowerCase();
  if (normalizedAction === "created" || normalizedAction === "create") return "Create";
  if (normalizedAction === "updated" || normalizedAction === "update") return "Update";
  if (normalizedAction === "skipped" || normalizedAction === "skip" || normalizedAction === "unchanged") return "Skip";
  if (normalizedAction === "error") return "Error";
  const normalizedStatus = String(status || "").toLowerCase();
  if (normalizedStatus === "failed" || normalizedStatus === "error") return "Error";
  return "Skip";
}

function diffRowClass(action, status) {
  const label = diffActionLabel(action, status).toLowerCase();
  if (label === "create") return "diff-create";
  if (label === "update") return "diff-update";
  if (label === "error") return "diff-error";
  return "diff-skip";
}

function normalizeDiffEntries(entry) {
  const notesPreview = entry?.notes?.diff_preview;
  if (Array.isArray(notesPreview)) {
    return notesPreview.map((item) => ({
      field: item.field ?? item.key ?? "",
      before: item.before,
      after: item.after,
    }));
  }

  if (notesPreview && typeof notesPreview === "object") {
    return Object.entries(notesPreview).map(([field, value]) => ({
      field,
      before: value && typeof value === "object" ? value.before : "",
      after: value && typeof value === "object" ? value.after : value,
    }));
  }

  const fieldDiffs = Array.isArray(entry?.field_diffs) ? entry.field_diffs : [];
  return fieldDiffs.map((item) => ({
    field: item.field ?? item.key ?? "",
    before: item.before,
    after: item.after,
  }));
}

function formatDiffValue(value) {
  if (value === null || value === undefined || value === "") return "(empty)";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderDiffCell(entry) {
  const diffs = normalizeDiffEntries(entry);
  if (diffs.length) {
    return diffs
      .map(
        (item) => `
      <div class="diff-field-row">
        <span class="mono">${escapeHtml(item.field || "-")}</span>:
        <span class="diff-before">${escapeHtml(formatDiffValue(item.before))}</span>
        <span>&rarr;</span>
        <span class="diff-after">${escapeHtml(formatDiffValue(item.after))}</span>
      </div>
    `
      )
      .join("");
  }

  if (entry?.error) {
    return `<div class="diff-field-row"><span class="diff-before">${escapeHtml(entry.error)}</span></div>`;
  }
  return `<span class="muted">No field changes</span>`;
}

function openDryRunModal() {
  const modal = $("dry-run-modal");
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  state.dryRun.previewViewed = true;
  updateDryRunConfirmVisibility();
}

function closeDryRunModal() {
  const modal = $("dry-run-modal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

function updateDryRunConfirmVisibility() {
  const button = $("confirm-dry-run-btn");
  const showConfirm = state.dryRun.previewViewed && state.dryRun.previewSyncReady;
  button.hidden = !showConfirm;
  button.disabled = !showConfirm;
}

function renderDryRunPreview(result, identifiers) {
  const tableWrap = $("dry-run-table-wrap");
  const emptyState = $("dry-run-empty");
  const tbody = $("dry-run-table-body");
  const summary = $("dry-run-summary");
  const rows = Array.isArray(result?.results) ? result.results : [];
  const changed = rows.filter((entry) => {
    const action = String(entry?.action || "").toLowerCase();
    return action === "created" || action === "updated" || action === "create" || action === "update";
  });

  state.dryRun.identifiers = identifiers.slice();
  state.dryRun.selectionKey = selectionKey(identifiers);
  state.dryRun.previewSyncReady = changed.length > 0;
  state.dryRun.previewViewed = false;
  updateDryRunConfirmVisibility();

  if (!rows.length || !changed.length) {
    tableWrap.hidden = true;
    emptyState.hidden = false;
    tbody.innerHTML = "";
    summary.textContent = "Nothing to sync. Dry run returned no create/update operations.";
    return;
  }

  tableWrap.hidden = false;
  emptyState.hidden = true;
  summary.textContent = `Preview generated for ${identifiers.length} selected asset(s). Review changes before confirming sync.`;

  tbody.innerHTML = rows
    .map((entry) => {
      const diffs = normalizeDiffEntries(entry);
      const actionLabel = diffActionLabel(entry.action, entry.status);
      return `
      <tr class="${diffRowClass(entry.action, entry.status)}">
        <td class="mono">${escapeHtml(entry.identifier || "-")}</td>
        <td>${escapeHtml(actionLabel)}</td>
        <td>${diffs.length}</td>
        <td>${renderDiffCell(entry)}</td>
      </tr>
    `;
    })
    .join("");
}

async function runDryRunPreview() {
  const identifiers = currentSelectionIdentifiers();
  if (!identifiers.length) {
    setSelectionValidation("Select at least one source asset to preview.");
    return;
  }
  setSelectionValidation("");
  const result = await apiFetch("/api/transfer", {
    method: "POST",
    body: JSON.stringify({ identifiers, dry_run: true }),
  });
  renderDryRunPreview(result, identifiers);
  openDryRunModal();
  notify("Preview generated. No data was changed.", "info");
}

function formatFieldValue(value) {
  if (value === null || value === undefined || value === "") return "(empty)";
  if (Array.isArray(value)) {
    if (!value.length) return "(empty)";
    return value
      .map((item) => (typeof item === "object" && item !== null ? JSON.stringify(item) : String(item)))
      .join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderAssetFieldList(containerId, data, emptyMessage) {
  const container = $(containerId);
  if (!container) return;
  const entries =
    data && typeof data === "object"
      ? Object.entries(data).sort(([left], [right]) => left.localeCompare(right))
      : [];

  if (!entries.length) {
    container.innerHTML = `<div class="muted">${escapeHtml(emptyMessage)}</div>`;
    return;
  }

  container.innerHTML = entries
    .map(
      ([key, value]) => `
      <div class="asset-field-row">
        <div class="asset-field-key">${escapeHtml(key)}</div>
        <div class="asset-field-value">${escapeHtml(formatFieldValue(value))}</div>
      </div>
    `
    )
    .join("");
}

function timelineStatusMeta(event) {
  const eventType = String(event?.event_type || "").toLowerCase();
  const payload = event?.payload && typeof event.payload === "object" ? event.payload : {};
  const payloadStatus = String(payload.status || payload.result || payload.level || "").toLowerCase();
  if (eventType.includes("retry") || payloadStatus.includes("retry")) {
    return { icon: "🔄", label: "Retried", tone: "info" };
  }
  if (
    eventType.includes("fail") ||
    eventType.includes("error") ||
    payloadStatus.includes("fail") ||
    payloadStatus.includes("error")
  ) {
    return { icon: "❌", label: "Failed", tone: "error" };
  }
  if (
    eventType.includes("partial") ||
    payloadStatus.includes("partial") ||
    payloadStatus.includes("warning") ||
    payloadStatus.includes("warn")
  ) {
    return { icon: "⚠️", label: "Partial", tone: "warning" };
  }
  if (
    eventType.includes("success") ||
    payloadStatus.includes("success") ||
    payloadStatus.includes("ok") ||
    payloadStatus.includes("complete")
  ) {
    return { icon: "✅", label: "Success", tone: "success" };
  }
  return { icon: "✅", label: "Success", tone: "success" };
}

function timelineSummary(event) {
  const payload = event?.payload && typeof event.payload === "object" ? event.payload : {};
  if (payload.error) return String(payload.error);
  if (payload.message) return String(payload.message);
  if (payload.notes && typeof payload.notes === "string") return payload.notes;
  if (event?.source) return `Source: ${event.source}`;
  return "Event recorded.";
}

function renderAssetTimeline(events) {
  const container = $("asset-detail-timeline");
  if (!container) return;
  if (!events.length) {
    container.innerHTML = `<div class="empty-state"><p>No sync events found for this asset.</p></div>`;
    return;
  }
  container.innerHTML = events
    .map((event) => {
      const meta = timelineStatusMeta(event);
      const eventType = event?.event_type || "unknown_event";
      const timestamp = formatDate(event?.created_at || event?.timestamp);
      const summary = timelineSummary(event);
      return `
      <div class="timeline-item timeline-item--${meta.tone}">
        <div class="timeline-dot" aria-hidden="true">${meta.icon}</div>
        <div class="timeline-body">
          <div class="row spread">
            <strong>${escapeHtml(eventType)}</strong>
            <span class="pill ${meta.tone}">${meta.label}</span>
          </div>
          <div class="muted">${escapeHtml(timestamp)}</div>
          <div class="subtle">${escapeHtml(summary)}</div>
        </div>
      </div>
    `;
    })
    .join("");
}

function openAssetDetailPanel() {
  const panel = $("asset-detail-panel");
  const backdrop = $("asset-detail-backdrop");
  if (!panel || !backdrop) return;
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  backdrop.classList.add("open");
  backdrop.setAttribute("aria-hidden", "false");
  state.assetDetail.open = true;
}

function closeAssetDetailPanel() {
  const panel = $("asset-detail-panel");
  const backdrop = $("asset-detail-backdrop");
  if (!panel || !backdrop) return;
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  backdrop.classList.remove("open");
  backdrop.setAttribute("aria-hidden", "true");
  state.assetDetail.open = false;
}

function renderAssetDetailLoading(identifier) {
  $("asset-detail-title").textContent = identifier || "-";
  $("asset-detail-subtitle").textContent = "Loading asset details...";
  renderAssetFieldList("asset-detail-source", null, "Loading source fields...");
  renderAssetFieldList("asset-detail-destination", null, "Loading destination fields...");
  $("asset-detail-timeline").innerHTML = `<div class="muted">Loading timeline...</div>`;
  $("asset-detail-destination-empty").hidden = true;
}

function renderAssetDetail(detail) {
  const identifier = detail?.identifier || state.assetDetail.identifier;
  const sourceAsset = detail?.kaseya || null;
  const destinationAsset = detail?.revnue_match || null;
  const syncEvents = Array.isArray(detail?.sync_events) ? detail.sync_events : [];
  $("asset-detail-title").textContent = identifier || "-";
  $("asset-detail-subtitle").textContent = destinationAsset
    ? "Matched destination asset found."
    : "Not yet synced to destination.";
  renderAssetFieldList("asset-detail-source", sourceAsset, "No source asset details available.");
  renderAssetFieldList(
    "asset-detail-destination",
    destinationAsset,
    "No destination fields found for this identifier."
  );
  $("asset-detail-destination-empty").hidden = !!destinationAsset;
  renderAssetTimeline(syncEvents);
}

async function openAssetDetail(identifier) {
  const normalizedIdentifier = String(identifier || "").trim();
  if (!normalizedIdentifier) return;
  state.assetDetail.identifier = normalizedIdentifier;
  renderAssetDetailLoading(normalizedIdentifier);
  openAssetDetailPanel();
  const detail = await apiFetch(`/api/assets/detail/${encodeURIComponent(normalizedIdentifier)}`);
  if (state.assetDetail.identifier !== normalizedIdentifier) return;
  renderAssetDetail(detail);
}

function renderKaseyaTable(items) {
  const body = $("kaseya-table").querySelector("tbody");
  body.innerHTML = "";
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">No source assets found.</td></tr>`;
    return;
  }
  items.forEach((asset) => {
    const identifier = asset.Identifier || "";
    const checked = state.selectedIdentifiers.has(identifier) ? "checked" : "";
    const row = document.createElement("tr");
    row.classList.add("kaseya-row-clickable");
    row.setAttribute("tabindex", "0");
    row.setAttribute("role", "button");
    row.setAttribute("aria-label", `View detail for ${identifier || "asset"}`);
    row.classList.toggle("selected", !!checked);
    row.innerHTML = `
      <td><input type="checkbox" data-id="${identifier}" class="kaseya-select" ${checked}></td>
      <td class="mono">${identifier}</td>
      <td>${asset.Name || ""}</td>
      <td>${asset.Manufacturer || ""}</td>
      <td>${asset.Model || ""}</td>
      <td>${formatDate(asset.ModifiedDate)}</td>
    `;
    row.addEventListener("click", (event) => {
      if (!identifier) return;
      if (event.target.closest("input, button, a, label")) return;
      withLoading(() => openAssetDetail(identifier));
    });
    row.addEventListener("keydown", (event) => {
      if (!identifier) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("input, button, a, label")) return;
      event.preventDefault();
      withLoading(() => openAssetDetail(identifier));
    });
    body.appendChild(row);
  });

  body.querySelectorAll(".kaseya-select").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const id = event.target.getAttribute("data-id");
      if (!id) return;
      if (event.target.checked) state.selectedIdentifiers.add(id);
      else state.selectedIdentifiers.delete(id);
      const row = event.target.closest("tr");
      if (row) row.classList.toggle("selected", !!event.target.checked);
      setSelectionValidation("");
      refreshDryRunSelectionState();
    });
  });
}

function renderRevnueTable(items) {
  const body = $("revnue-table").querySelector("tbody");
  body.innerHTML = "";
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No destination assets found.</td></tr>`;
    return;
  }
  items.forEach((asset) => {
    const identifier = asset.serial_number || asset.asset_tag || "";
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${asset.id || ""}</td>
      <td class="mono">${asset.serial_number || ""}</td>
      <td class="mono">${asset.asset_tag || ""}</td>
      <td>${asset.name || ""}</td>
      <td><button class="danger delete-revnue-btn" data-id="${identifier}">Remove</button></td>
    `;
    body.appendChild(row);
  });
  body.querySelectorAll(".delete-revnue-btn").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const identifier = event.target.getAttribute("data-id");
      if (!identifier) return;
      if (!window.confirm(`Remove destination asset "${identifier}"? This action cannot be undone.`)) return;
      try {
        setLoading(true);
        await apiFetch(`/api/assets/revnue/${encodeURIComponent(identifier)}`, { method: "DELETE" });
        await Promise.all([loadRevnueAssets(), loadLogs()]);
        notify(`Removed destination asset "${identifier}".`, "info");
      } catch (error) {
        notify(`Could not remove asset: ${error.message}`, "error");
      } finally {
        setLoading(false);
      }
    });
  });
}

function renderLogEntries(containerId, items) {
  const container = $(containerId);
  if (!items.length) {
    container.innerHTML = `<div class="muted">No activity yet.</div>`;
    return;
  }
  container.innerHTML = items
    .map((item) => {
      const level = item.level || "info";
      const pillClass = level === "error" ? "error" : level === "warning" ? "warning" : "success";
      return `
      <div class="activity-item">
        <div class="row spread">
          <strong>${item.message || "-"}</strong>
          <span class="pill ${pillClass}">${formatStatusLabel(level)}</span>
        </div>
        <div class="muted">${formatDate(item.timestamp)} | ${item.category || ""}</div>
      </div>
    `;
    })
    .join("");
}

function renderTransferSummary(result) {
  if (!result) return;
  const summary = result.summary || {};
  const firstWarning = (result.results || []).find((entry) => entry.status === "partial" || entry.status === "failed");
  const debug = firstWarning ? firstWarning.debug || {} : {};
  const hasDebug = Object.keys(debug).length > 0;
  const mode = result.mode || "unknown";
  const skipped = summary.skipped || 0;
  $("transfer-summary").innerHTML = `
    <div><strong>Added:</strong> ${summary.created || 0} | <strong>Updated:</strong> ${
    summary.updated || 0
  } | <strong>Needs review:</strong> ${summary.partial || 0} | <strong>Failed:</strong> ${
    summary.failed || 0
  } | <strong>Skipped:</strong> ${skipped}</div>
    <div class="muted">Mode: <strong>${mode === "live" ? "Live API" : mode === "mock" ? "Mock API" : mode}</strong>${
    skipped ? " | Some selected assets were skipped due sync safeguards." : ""
  }</div>
    <div class="muted">Records marked as "Needs review" synced with missing or incomplete optional fields.</div>
    ${
      hasDebug
        ? `<div class="muted">Sample technical details (for troubleshooting):</div><pre class="mono">${JSON.stringify(
            debug,
            null,
            2
          )}</pre>`
        : ""
    }
  `;
}

function renderHistory(identifier, items) {
  const container = $("history-list");
  const target = identifier.trim();
  const filtered = items.filter((item) => {
    const details = item.details || {};
    const ownId = details.identifier || details?.debug?.identifier;
    if (ownId === target) return true;
    if (Array.isArray(details.results)) {
      return details.results.some((entry) => entry.identifier === target);
    }
    return false;
  });
  if (!filtered.length) {
    container.innerHTML = `<div class="muted">No activity history found for ${
      target || "the selected identifier"
    }.</div>`;
    return;
  }
  container.innerHTML = filtered
    .map(
      (item) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${item.message}</strong>
          <span>${formatStatusLabel(item.level)}</span>
        </div>
        <div class="muted">${formatDate(item.timestamp)} | ${item.category || ""}</div>
      </div>
    `
    )
    .join("");
}

async function loadKaseyaAssets() {
  const { page, pageSize, search } = state.kaseya;
  const useCoverageFilter = ["synced", "stale", "failed"].includes(state.kaseya.coverageFilter);

  if (useCoverageFilter) {
    const comparisonItems = await fetchCoverageComparison(false);
    const filteredAssets = filterCoverageAssets(comparisonItems);
    const paged = paginateItems(filteredAssets, page, pageSize);
    state.kaseya.page = paged.page;
    state.kaseya.totalPages = paged.totalPages;
    $("kaseya-page-label").textContent = `Page ${paged.page} of ${paged.totalPages}`;
    renderKaseyaTable(paged.items);
    return;
  }

  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    search,
    only_missing: state.onlyMissing ? "true" : "false",
  });
  const data = await apiFetch(`/api/kaseya/assets?${query.toString()}`);
  state.kaseya.totalPages = data.total_pages || 1;
  $("kaseya-page-label").textContent = `Page ${data.page} of ${state.kaseya.totalPages}`;
  renderKaseyaTable(data.items || []);
}

async function loadCoverageStats() {
  setCoverageLoading();
  const comparisonItems = await fetchCoverageComparison(true);
  const staleCutoffMs = Date.now() - state.coverage.staleDays * 24 * 60 * 60 * 1000;

  let matched = 0;
  let missing = 0;
  let stale = 0;
  let failureSignals = 0;

  comparisonItems.forEach((entry) => {
    const status = String(entry.match_status || "").toLowerCase();
    if (status === "matched") {
      matched += 1;
    } else if (status === "missing_in_revnue") {
      missing += 1;
    }

    if (isStaleAsset(entry.kaseya_asset, staleCutoffMs)) {
      stale += 1;
    }
    if (hasFailureSignal(entry)) {
      failureSignals += 1;
    }
  });

  setCoverageCard("total", comparisonItems.length, "Comparison snapshot");
  setCoverageCard("synced", matched, "Identifiers found in destination");
  setCoverageCard("missing", missing, "Click to show only missing assets");
  setCoverageCard("stale", stale, "Click to filter by last-updated age");
  setCoverageCard(
    "failed",
    failureSignals > 0 ? "Yes" : "No",
    failureSignals > 0 ? `${failureSignals} failure signal(s) detected` : "No failure signal in comparison payload"
  );
  updateCoverageCardSelection();
}

async function loadRevnueAssets() {
  const { page, pageSize, search } = state.revnue;
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    search,
  });
  const data = await apiFetch(`/api/revnue/assets?${query.toString()}`);
  state.revnue.totalPages = data.total_pages || 1;
  $("revnue-page-label").textContent = `Page ${data.page} of ${state.revnue.totalPages}`;
  renderRevnueTable(data.items || []);
}

async function loadLogs() {
  const data = await apiFetch("/api/logs?limit=200");
  state.logs.notifications = data.channels?.notifications || [];
  state.logs.messages = data.channels?.messages || [];
  state.logs.unreadCount = data.channels?.unread_count || 0;
  $("activity-unread-badge").textContent = String(state.logs.unreadCount);
  renderLogEntries("activity-notifications", state.logs.notifications);
  renderLogEntries("activity-messages", state.logs.messages);
}

async function loadAutosyncState() {
  const data = await apiFetch("/api/autosync/state");
  setAutosyncButton(!!data.enabled);
}

function openActivityModal() {
  $("activity-modal").classList.add("open");
}

function closeActivityModal() {
  $("activity-modal").classList.remove("open");
}

async function executeTransfer(options = {}) {
  const identifiers = options.identifiers || currentSelectionIdentifiers();
  if (!identifiers.length) {
    setSelectionValidation("Select at least one source asset to sync.");
    return;
  }
  const transferButton = options.button || null;
  const onSuccess = typeof options.onSuccess === "function" ? options.onSuccess : null;
  try {
    setLoading(true);
    setButtonBusy(transferButton, true);
    const result = await apiFetch("/api/transfer", {
      method: "POST",
      body: JSON.stringify({ identifiers }),
    });
    renderTransferSummary(result);
    state.selectedIdentifiers.clear();
    $("kaseya-select-all").checked = false;
    setSelectionValidation("");
    resetDryRunState();
    updateDryRunConfirmVisibility();
    if (onSuccess) {
      onSuccess();
    }
    await Promise.all([loadKaseyaAssets(), loadRevnueAssets(), loadLogs()]);
    notify("Sync completed successfully.", "info");
  } catch (error) {
    notify(`Sync failed: ${error.message}`, "error");
  } finally {
    setButtonBusy(transferButton, false);
    setLoading(false);
  }
}

async function markLogsRead() {
  await apiFetch("/api/logs/mark-read", {
    method: "POST",
    body: JSON.stringify({ channels: ["notifications", "messages"] }),
  });
  await loadLogs();
}

function bindEvents() {
  $("open-activity-btn").addEventListener("click", () => {
    openActivityModal();
  });
  $("close-activity-btn").addEventListener("click", () => closeActivityModal());
  $("close-asset-detail-btn").addEventListener("click", () => closeAssetDetailPanel());
  $("asset-detail-backdrop").addEventListener("click", () => closeAssetDetailPanel());
  $("asset-detail-sync-btn").addEventListener("click", () => {
    const identifier = state.assetDetail.identifier;
    if (!identifier) {
      notify("Select an asset first.", "warning");
      return;
    }
    executeTransfer({
      identifiers: [identifier],
      button: $("asset-detail-sync-btn"),
      onSuccess: () => {
        window.setTimeout(() => {
          if (state.assetDetail.open && state.assetDetail.identifier === identifier) {
            withLoading(() => openAssetDetail(identifier));
          }
        }, 0);
      },
    });
  });
  $("mark-activity-read-btn").addEventListener("click", () => {
    withLoading(markLogsRead);
  });

  $("refresh-data-btn").addEventListener("click", () => withLoading(refreshAll));
  document.querySelectorAll("[data-coverage-filter]").forEach((card) => {
    card.addEventListener("click", () => {
      applyCoverageFilter(card.getAttribute("data-coverage-filter") || "all");
    });
  });
  $("export-csv-btn").addEventListener("click", () => {
    const url = "/api/assets/export.csv";
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "asset_sync_comparison.csv";
    anchor.click();
    notify("CSV export started.", "info");
  });
  $("run-reconcile-btn").addEventListener("click", () =>
    withLoading(async () => {
      setSyncRunStatus("Manual sync started...");
      const run = await apiFetch("/api/sync/run-now", {
        method: "POST",
        body: JSON.stringify({ force: true, process_limit: 100 }),
      });
      await Promise.all([loadRevnueAssets(), loadLogs()]);
      const processed = run.processed || 0;
      const failed = run.failed || 0;
      const reconcileQueued = run.reconcile_queued || 0;
      setSyncRunStatus(
        `Last manual sync: processed ${processed}, queued ${reconcileQueued}, failed ${failed}, finished ${formatDate(
          run.completed_at
        )}.`
      );
      notify("Manual sync completed.", failed > 0 ? "warning" : "info");
    })
  );
  $("preview-selected-btn").addEventListener("click", () => withLoading(runDryRunPreview));
  $("transfer-selected-btn").addEventListener("click", () => withLoading(runDryRunPreview));
  $("close-dry-run-btn").addEventListener("click", closeDryRunModal);
  $("cancel-dry-run-btn").addEventListener("click", closeDryRunModal);
  $("confirm-dry-run-btn").addEventListener("click", () =>
    executeTransfer({
      identifiers: state.dryRun.identifiers.slice(),
      button: $("confirm-dry-run-btn"),
      onSuccess: closeDryRunModal,
    })
  );
  $("dry-run-modal").addEventListener("click", (event) => {
    if (event.target.id === "dry-run-modal") {
      closeDryRunModal();
    }
  });

  $("autosync-navbar-toggle").addEventListener("click", async () => {
    try {
      setLoading(true);
      const current = await apiFetch("/api/autosync/state");
      const nextEnabled = !current.enabled;
      await apiFetch("/api/autosync/state", {
        method: "POST",
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      setAutosyncButton(nextEnabled);
      notify(`Auto Sync is now ${nextEnabled ? "On" : "Off"}.`, "info");
    } catch (error) {
      notify(`Could not update Auto Sync: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  });

  $("only-missing-toggle").addEventListener("change", (event) => {
    state.onlyMissing = !!event.target.checked;
    state.kaseya.coverageFilter = state.onlyMissing ? "missing" : "all";
    state.kaseya.lastUpdatedBefore = "";
    state.kaseya.page = 1;
    updateCoverageCardSelection();
    withLoading(loadKaseyaAssets);
  });

  $("kaseya-search-btn").addEventListener("click", () => {
    state.kaseya.search = $("kaseya-search").value.trim();
    state.kaseya.page = 1;
    withLoading(loadKaseyaAssets);
  });
  $("kaseya-search").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    state.kaseya.search = $("kaseya-search").value.trim();
    state.kaseya.page = 1;
    withLoading(loadKaseyaAssets);
  });
  $("revnue-search-btn").addEventListener("click", () => {
    state.revnue.search = $("revnue-search").value.trim();
    state.revnue.page = 1;
    withLoading(loadRevnueAssets);
  });
  $("revnue-search").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    state.revnue.search = $("revnue-search").value.trim();
    state.revnue.page = 1;
    withLoading(loadRevnueAssets);
  });

  $("kaseya-prev-btn").addEventListener("click", () => {
    if (state.kaseya.page > 1) {
      state.kaseya.page -= 1;
      withLoading(loadKaseyaAssets);
    }
  });
  $("kaseya-next-btn").addEventListener("click", () => {
    if (state.kaseya.page < state.kaseya.totalPages) {
      state.kaseya.page += 1;
      withLoading(loadKaseyaAssets);
    }
  });
  $("revnue-prev-btn").addEventListener("click", () => {
    if (state.revnue.page > 1) {
      state.revnue.page -= 1;
      withLoading(loadRevnueAssets);
    }
  });
  $("revnue-next-btn").addEventListener("click", () => {
    if (state.revnue.page < state.revnue.totalPages) {
      state.revnue.page += 1;
      withLoading(loadRevnueAssets);
    }
  });

  $("kaseya-select-all").addEventListener("change", (event) => {
    const check = !!event.target.checked;
    document.querySelectorAll(".kaseya-select").forEach((box) => {
      box.checked = check;
      const id = box.getAttribute("data-id");
      if (!id) return;
      if (check) state.selectedIdentifiers.add(id);
      else state.selectedIdentifiers.delete(id);
      const row = box.closest("tr");
      if (row) row.classList.toggle("selected", check);
    });
    setSelectionValidation("");
    refreshDryRunSelectionState();
  });

  $("history-load-btn").addEventListener("click", () => {
    const identifier = $("history-identifier").value.trim();
    renderHistory(identifier, state.logs.messages);
  });
  $("history-identifier").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const identifier = $("history-identifier").value.trim();
    renderHistory(identifier, state.logs.messages);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeDryRunModal();
    closeAssetDetailPanel();
    closeActivityModal();
  });
}

async function refreshAll() {
  let coverageError = null;
  try {
    await loadCoverageStats();
  } catch (error) {
    coverageError = error;
  }
  await Promise.all([loadKaseyaAssets(), loadRevnueAssets(), loadLogs(), loadAutosyncState()]);
  if (coverageError) {
    throw coverageError;
  }
}

async function withLoading(fn) {
  try {
    setLoading(true);
    await fn();
  } catch (error) {
    notify(`Action failed: ${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

async function init() {
  bindEvents();
  resetDryRunState();
  updateDryRunConfirmVisibility();
  updateCoverageCardSelection();
  setSyncRunStatus("No manual sync has been started in this session.");
  updateHealthDot().catch(() => {});
  await withLoading(refreshAll);
  window.setInterval(() => loadLogs().catch(() => {}), 15000);
  window.setInterval(() => updateHealthDot().catch(() => {}), 30000);
}

init().catch((error) => {
  setLoading(false);
  notify(`Could not load dashboard: ${error.message}`, "error");
});
