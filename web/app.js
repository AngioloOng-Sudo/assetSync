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

function setAutosyncButton(enabled) {
  const button = $("autosync-navbar-toggle");
  button.textContent = `AUTOSYNC: ${enabled ? "LIVE" : "OFFLINE"}`;
  button.classList.toggle("primary", enabled);
  button.classList.toggle("soft", !enabled);
}

function renderKaseyaTable(items) {
  const body = $("kaseya-table").querySelector("tbody");
  body.innerHTML = "";
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">No Kaseya assets found.</td></tr>`;
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
    body.innerHTML = `<tr><td colspan="5" class="muted">No Revnue assets found.</td></tr>`;
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
      <td><button class="danger delete-revnue-btn" data-id="${identifier}">Delete</button></td>
    `;
    body.appendChild(row);
  });
  body.querySelectorAll(".delete-revnue-btn").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const identifier = event.target.getAttribute("data-id");
      if (!identifier) return;
      if (!window.confirm(`Delete Revnue asset with identifier ${identifier}?`)) return;
      try {
        setLoading(true);
        await apiFetch(`/api/assets/revnue/${encodeURIComponent(identifier)}`, { method: "DELETE" });
        await Promise.all([loadRevnueAssets(), loadLogs()]);
      } catch (error) {
        notify(`Delete failed: ${error.message}`, "error");
      } finally {
        setLoading(false);
      }
    });
  });
}

function renderLogEntries(containerId, items) {
  const container = $(containerId);
  if (!items.length) {
    container.innerHTML = `<div class="muted">No entries.</div>`;
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
          <span class="pill ${pillClass}">${level}</span>
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
  const firstWarning = (result.results || []).find((entry) => entry.status === "partial");
  const debug = firstWarning ? firstWarning.debug || {} : {};
  $("transfer-summary").innerHTML = `
    <div><strong>Created:</strong> ${summary.created || 0} | <strong>Updated:</strong> ${
    summary.updated || 0
  } | <strong>Partial:</strong> ${summary.partial || 0} | <strong>Failed:</strong> ${summary.failed || 0}</div>
    <div class="muted">Warnings are marked as partial with debug metadata for field completeness checks.</div>
    <pre class="mono">${JSON.stringify(debug, null, 2)}</pre>
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
    container.innerHTML = `<div class="muted">No transfer history for ${target || "the selected identifier"}.</div>`;
    return;
  }
  container.innerHTML = filtered
    .map(
      (item) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${item.message}</strong>
          <span>${item.level}</span>
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
  $("kaseya-page-label").textContent = `Page ${data.page}/${state.kaseya.totalPages}`;
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
  $("revnue-page-label").textContent = `Page ${data.page}/${state.revnue.totalPages}`;
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
    notify("Select at least one Kaseya asset.", "warning");
    return;
  }
  $("transfer-modal-text").textContent = `Transfer ${count} selected asset(s) to Revnue?`;
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
    closeTransferModal();
    await Promise.all([loadKaseyaAssets(), loadRevnueAssets(), loadLogs()]);
    notify("Transfer completed successfully.", "info");
  } catch (error) {
    notify(`Transfer failed: ${error.message}`, "error");
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
  $("sidebar-toggle-btn").addEventListener("click", () => {
    const sidebar = $("dashboard-sidebar");
    const shell = document.querySelector(".app-shell");
    const isCollapsed = sidebar.classList.toggle("collapsed");
    if (shell) {
      shell.classList.toggle("menu-collapsed", isCollapsed);
    }
  });

  $("open-activity-btn").addEventListener("click", () => {
    openActivityModal();
  });
  $("close-activity-btn").addEventListener("click", () => closeActivityModal());
  $("mark-activity-read-btn").addEventListener("click", () => {
    withLoading(markLogsRead);
  });

  $("refresh-data-btn").addEventListener("click", () => withLoading(refreshAll));
  $("run-reconcile-btn").addEventListener("click", () =>
    withLoading(async () => {
      await apiFetch("/api/sync/reconcile", { method: "POST" });
      await apiFetch("/api/autosync/process", { method: "POST" });
      await Promise.all([loadRevnueAssets(), loadLogs()]);
      notify("Reconciliation completed.", "info");
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
    } catch (error) {
      notify(`Autosync update failed: ${error.message}`, "error");
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
  $("revnue-search-btn").addEventListener("click", () => {
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
    });
  });

  $("history-load-btn").addEventListener("click", () => {
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
    notify(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function init() {
  bindEvents();
  await withLoading(refreshAll);
  window.setInterval(() => loadLogs().catch(() => {}), 15000);
}

init().catch((error) => {
  setLoading(false);
  notify(`Initialization failed: ${error.message}`, "error");
});
