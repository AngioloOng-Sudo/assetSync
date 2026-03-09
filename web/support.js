const $ = (id) => document.getElementById(id);

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
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
  window.setTimeout(() => toast.remove(), 2600);
}

function formatDate(isoDate) {
  if (!isoDate) return "-";
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed.toLocaleString();
}

function formatLevelLabel(value) {
  if (!value) return "Info";
  const normalized = String(value).toLowerCase();
  if (normalized === "partial") return "Needs review";
  if (normalized === "failed" || normalized === "error") return "Failed";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

const CONNECTIVITY_TARGETS = [
  { key: "kaseya", label: "Kaseya API" },
  { key: "revnue", label: "Revnue API" },
];

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function connectivityStatus(result) {
  if (!result) return { tone: "neutral", label: "Not checked" };
  const mode = String(result.mode || "").toLowerCase();
  const error = String(result.error || "").toLowerCase();
  if (mode === "mock") return { tone: "info", label: "Mock mode" };
  if (result.reachable) return { tone: "success", label: "Connected" };
  if (error.includes("circuit_open")) return { tone: "warning", label: "Circuit open" };
  if (error.includes("missing_credentials")) return { tone: "warning", label: "Missing credentials" };
  if (error.includes("missing_url")) return { tone: "warning", label: "Missing endpoint" };
  return { tone: "error", label: "Unavailable" };
}

function connectivityDetails(result) {
  if (!result) return "No connectivity result returned.";
  if (result.error) return String(result.error);
  if (result.reachable) return "Connection test succeeded.";
  return "Connection test failed.";
}

function renderConnectivityStatus(results) {
  const container = $("connectivity-status");
  if (!container) return;

  if (!results || typeof results !== "object") {
    container.innerHTML = `<div class="connectivity-status-empty">Connectivity data is unavailable.</div>`;
    return;
  }

  container.innerHTML = CONNECTIVITY_TARGETS.map(({ key, label }) => {
    const result = results[key] || null;
    const status = connectivityStatus(result);
    const mode = result?.mode ? String(result.mode).toUpperCase() : "-";
    const statusCode = result?.status_code != null ? String(result.status_code) : "-";
    const endpoint = result?.url || result?.target || "-";
    const detail = connectivityDetails(result);

    return `
      <article class="connectivity-status-card ${status.tone}">
        <div class="connectivity-status-head">
          <div class="connectivity-service">${escapeHtml(label)}</div>
          <span class="pill ${status.tone}">${escapeHtml(status.label)}</span>
        </div>
        <dl class="connectivity-meta">
          <div>
            <dt>Mode</dt>
            <dd>${escapeHtml(mode)}</dd>
          </div>
          <div>
            <dt>HTTP</dt>
            <dd>${escapeHtml(statusCode)}</dd>
          </div>
          <div>
            <dt>Endpoint</dt>
            <dd class="mono">${escapeHtml(endpoint)}</dd>
          </div>
          <div>
            <dt>Details</dt>
            <dd>${escapeHtml(detail)}</dd>
          </div>
        </dl>
      </article>
    `;
  }).join("");
}

function renderFailedPartialActivity(items) {
  const container = $("failed-partial-activity");
  if (!items || !items.length) {
    container.innerHTML = `<div class="muted">No items need attention right now.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${item.message || "-"}</strong>
          <span>${formatLevelLabel(item.level)}</span>
        </div>
        <div class="muted">${formatDate(item.timestamp)} | ${item.category || ""}</div>
      </div>
    `
    )
    .join("");
}

async function loadDiagnostics() {
  const data = await apiFetch("/api/support/diagnostics");
  $("diagnostics-viewer").textContent = JSON.stringify(data, null, 2);
  $("safe-config-viewer").textContent = JSON.stringify(data.safe_config || {}, null, 2);
  renderFailedPartialActivity(data.recent_failed_or_partial_activity || []);
}

async function runConnectivity() {
  try {
    const data = await apiFetch("/api/support/checks");
    const results = data.results || {};
    renderConnectivityStatus(results);
    $("connectivity-output").textContent = JSON.stringify(results, null, 2);
  } catch (error) {
    const fallbackResults = Object.fromEntries(
      CONNECTIVITY_TARGETS.map(({ key }) => [key, { reachable: false, mode: "live", error: error.message }])
    );
    renderConnectivityStatus(fallbackResults);
    $("connectivity-output").textContent = error.message;
    throw error;
  }
}

async function submitTicket() {
  const title = $("ticket-title").value.trim();
  const description = $("ticket-description").value.trim();
  const priority = $("ticket-priority").value;

  if (!title || !description) {
    $("ticket-message").textContent = "Please add both a title and a description.";
    return;
  }

  await apiFetch("/api/support/tickets", {
    method: "POST",
    body: JSON.stringify({ title, description, priority }),
  });
  $("ticket-title").value = "";
  $("ticket-description").value = "";
  $("ticket-message").textContent = "Issue report submitted.";
  notify("Issue report submitted.", "info");
  await loadTickets();
}

async function loadTickets() {
  const data = await apiFetch("/api/support/tickets?limit=100");
  const items = data.items || [];
  const container = $("ticket-history");
  if (!items.length) {
    container.innerHTML = `<div class="muted">No reports submitted yet.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (ticket) => `
      <div class="event-item">
        <div class="row spread">
          <strong>#${ticket.id} ${ticket.title}</strong>
          <span class="pill ${
            ticket.priority === "high" ? "error" : ticket.priority === "normal" ? "warning" : "success"
          }">${formatLevelLabel(ticket.priority)}</span>
        </div>
        <div>${ticket.description}</div>
        <div class="muted">${formatDate(ticket.created_at)}</div>
      </div>
    `
    )
    .join("");
}

async function exportDiagnostics() {
  const text = await apiFetch("/api/support/diagnostics/export");
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "diagnostics_export.json";
  anchor.click();
  URL.revokeObjectURL(url);
  notify("Diagnostics file downloaded.", "info");
}

async function withLoading(fn) {
  try {
    setLoading(true);
    await fn();
  } catch (error) {
    notify(`Unable to complete this action: ${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

$("run-diagnostics-btn").addEventListener("click", () => withLoading(loadDiagnostics));
$("connectivity-btn").addEventListener("click", () => withLoading(runConnectivity));
$("submit-ticket-btn").addEventListener("click", () => withLoading(submitTicket));
$("load-tickets-btn").addEventListener("click", () => withLoading(loadTickets));
$("export-diagnostics-btn").addEventListener("click", () => withLoading(exportDiagnostics));

withLoading(async () => {
  await Promise.all([loadDiagnostics(), runConnectivity(), loadTickets()]);
});
