const state = {
  kaseya: { page: 1, pageSize: 8, search: "", totalPages: 1 },
  revnue: { page: 1, pageSize: 8, search: "", totalPages: 1 },
  selectedIdentifiers: new Set(),
  onlyMissing: false,
  logs: { notifications: [], messages: [], unreadCount: 0 },
};

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
    row.classList.toggle("selected", !!checked);
    row.innerHTML = `
      <td><input type="checkbox" data-id="${identifier}" class="kaseya-select" ${checked}></td>
      <td class="mono">${identifier}</td>
      <td>${asset.Name || ""}</td>
      <td>${asset.Manufacturer || ""}</td>
      <td>${asset.Model || ""}</td>
      <td>${formatDate(asset.ModifiedDate)}</td>
    `;
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
  $("transfer-summary").innerHTML = `
    <div><strong>Added:</strong> ${summary.created || 0} | <strong>Updated:</strong> ${
    summary.updated || 0
  } | <strong>Needs review:</strong> ${summary.partial || 0} | <strong>Failed:</strong> ${
    summary.failed || 0
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

function openTransferModal() {
  const count = state.selectedIdentifiers.size;
  if (!count) {
    notify("Select at least one source asset to sync.", "warning");
    return;
  }
  $("transfer-modal-text").textContent = `Sync ${count} selected asset(s) to the destination system?`;
  $("transfer-modal").classList.add("open");
}

function closeTransferModal() {
  $("transfer-modal").classList.remove("open");
}

function openActivityModal() {
  $("activity-modal").classList.add("open");
}

function closeActivityModal() {
  $("activity-modal").classList.remove("open");
}

async function executeTransfer() {
  const identifiers = Array.from(state.selectedIdentifiers);
  if (!identifiers.length) return;
  const transferButton = $("confirm-transfer-btn");
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
    closeTransferModal();
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
  $("mark-activity-read-btn").addEventListener("click", () => {
    withLoading(markLogsRead);
  });

  $("refresh-data-btn").addEventListener("click", () => withLoading(refreshAll));
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
  $("preview-selected-btn").addEventListener("click", () =>
    withLoading(async () => {
      const identifiers = Array.from(state.selectedIdentifiers);
      if (!identifiers.length) {
        notify("Select at least one source asset to preview.", "warning");
        return;
      }
      const result = await apiFetch("/api/sync/dry-run", {
        method: "POST",
        body: JSON.stringify({ identifiers }),
      });
      renderTransferSummary(result);
      notify("Preview generated. No data was changed.", "info");
    })
  );
  $("transfer-selected-btn").addEventListener("click", openTransferModal);
  $("confirm-transfer-btn").addEventListener("click", executeTransfer);
  $("cancel-transfer-btn").addEventListener("click", closeTransferModal);

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
    state.kaseya.page = 1;
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
}

async function refreshAll() {
  await Promise.all([loadKaseyaAssets(), loadRevnueAssets(), loadLogs(), loadAutosyncState()]);
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
  setSyncRunStatus("No manual sync has been started in this session.");
  await withLoading(refreshAll);
  window.setInterval(() => loadLogs().catch(() => {}), 15000);
}

init().catch((error) => {
  setLoading(false);
  notify(`Could not load dashboard: ${error.message}`, "error");
});
