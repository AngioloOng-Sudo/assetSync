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

function renderFailedPartialActivity(items) {
  const container = $("failed-partial-activity");
  if (!items || !items.length) {
    container.innerHTML = `<div class="muted">No failed or partial activity.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${item.message || "-"}</strong>
          <span>${item.level || "-"}</span>
        </div>
        <div class="muted">${item.timestamp || ""} | ${item.category || ""}</div>
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
  const data = await apiFetch("/api/support/checks");
  $("connectivity-output").textContent = JSON.stringify(data, null, 2);
}

async function submitTicket() {
  const title = $("ticket-title").value.trim();
  const description = $("ticket-description").value.trim();
  const priority = $("ticket-priority").value;

  if (!title || !description) {
    $("ticket-message").textContent = "Title and description are required.";
    return;
  }

  await apiFetch("/api/support/tickets", {
    method: "POST",
    body: JSON.stringify({ title, description, priority }),
  });
  $("ticket-title").value = "";
  $("ticket-description").value = "";
  $("ticket-message").textContent = "Ticket submitted.";
  notify("Support ticket submitted.", "info");
  await loadTickets();
}

async function loadTickets() {
  const data = await apiFetch("/api/support/tickets?limit=100");
  const items = data.items || [];
  const container = $("ticket-history");
  if (!items.length) {
    container.innerHTML = `<div class="muted">No tickets found.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (ticket) => `
      <div class="event-item">
        <div class="row spread">
          <strong>#${ticket.id} ${ticket.title}</strong>
          <span class="pill ${ticket.priority === "high" ? "error" : "success"}">${ticket.priority}</span>
        </div>
        <div>${ticket.description}</div>
        <div class="muted">${ticket.created_at}</div>
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
}

async function withLoading(fn) {
  try {
    setLoading(true);
    await fn();
  } catch (error) {
    notify(`Support action failed: ${error.message}`, "error");
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
