const $ = (id) => document.getElementById(id);

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
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

function healthPillClass(state) {
  if (state === "critical") return "error";
  if (state === "degraded") return "warning";
  return "success";
}

function renderKpis(status, overview) {
  const kpis = [
    { label: "Autosync", value: status.autosync_enabled ? "Enabled" : "Disabled" },
    { label: "Success Rate", value: `${status.success_rate || 0}%` },
    { label: "Events (window)", value: overview.totals?.events || 0 },
    { label: "Partial (window)", value: overview.totals?.partial || 0 },
  ];
  $("sync-kpis").innerHTML = kpis
    .map(
      (kpi) => `
      <div class="kpi">
        <div class="muted">${kpi.label}</div>
        <div class="value">${kpi.value}</div>
      </div>
    `
    )
    .join("");

  const healthState = status.health_state || overview.health_state || "healthy";
  $("health-state-pill").textContent = healthState;
  $("health-state-pill").className = `pill ${healthPillClass(healthState)}`;
  $("worker-heartbeat").textContent = formatDate(status.worker_heartbeat_at);
  $("last-reconcile").textContent = formatDate(status.last_reconcile_at);
}

function renderQueueMetrics(metrics) {
  $("queue-metrics").innerHTML = Object.entries(metrics || {})
    .map(
      ([key, value]) => `
      <div class="event-item row spread">
        <span>${key}</span><strong>${value}</strong>
      </div>
    `
    )
    .join("");
}

function renderEvents(containerId, events) {
  const container = $(containerId);
  if (!events || !events.length) {
    container.innerHTML = `<div class="muted">No events.</div>`;
    return;
  }
  container.innerHTML = events
    .map(
      (event) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${event.event_type || "event"} (${event.status || "unknown"})</strong>
          <span>#${event.id || ""}</span>
        </div>
        <div class="muted">${formatDate(event.created_at)} | ${event.identifier || "-"}</div>
      </div>
    `
    )
    .join("");
}

async function loadData() {
  try {
    setLoading(true);
    const windowKey = $("overview-window").value;
    const [status, overview, health] = await Promise.all([
      apiFetch("/api/sync/status"),
      apiFetch(`/api/sync/overview?window=${encodeURIComponent(windowKey)}`),
      apiFetch("/api/support/health"),
    ]);
    renderKpis(status, overview);
    renderQueueMetrics(status.queue_metrics || {});
    const failedPartial = [...(status.failed_events || []), ...(status.partial_events || [])].slice(0, 30);
    renderEvents("failed-partial-events", failedPartial);
    renderEvents("recent-events", status.recent_events || []);
    $("health-snapshot").textContent = JSON.stringify(
      {
        timestamp: health.timestamp,
        storage: health.storage,
        safe_config: health.safe_config,
      },
      null,
      2
    );
  } finally {
    setLoading(false);
  }
}

$("sync-refresh-btn").addEventListener("click", () => {
  loadData().catch((error) => notify(error.message, "error"));
});

$("overview-window").addEventListener("change", () => {
  loadData().catch((error) => notify(error.message, "error"));
});

loadData().catch((error) => {
  setLoading(false);
  notify(`Failed to load sync status: ${error.message}`, "error");
});

window.setInterval(() => loadData().catch(() => {}), 20000);
