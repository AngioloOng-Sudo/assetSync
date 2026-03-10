const $ = (id) => document.getElementById(id);
let syncTrendChart = null;
let failedPartialRetryIdentifiers = [];

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

function formatLabel(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function dayKeyFromIso(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}

function dayLabelFromKey(dayKey) {
  if (!dayKey) return "-";
  const parsed = new Date(`${dayKey}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return dayKey;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function destroyTrendChart() {
  if (syncTrendChart) {
    syncTrendChart.destroy();
    syncTrendChart = null;
  }
}

function renderTrendChart(auditItems) {
  const empty = $("sync-trend-empty");
  const canvas = $("sync-trend-chart");
  if (!empty || !canvas) return;

  destroyTrendChart();

  const groupedByDay = new Map();
  (auditItems || []).forEach((item) => {
    const dayKey = dayKeyFromIso(item?.completed_at);
    if (!dayKey) return;
    const current = groupedByDay.get(dayKey) || { processed: 0, failed: 0 };
    current.processed += toFiniteNumber(item?.processed);
    current.failed += toFiniteNumber(item?.failed);
    groupedByDay.set(dayKey, current);
  });

  const days = Array.from(groupedByDay.keys()).sort().slice(-7);
  if (days.length < 2 || typeof Chart === "undefined") {
    canvas.hidden = true;
    empty.hidden = false;
    empty.textContent =
      typeof Chart === "undefined"
        ? "Trend chart is unavailable because Chart.js did not load."
        : "Not enough data yet.";
    return;
  }

  const labels = days.map((dayKey) => dayLabelFromKey(dayKey));
  const successRate = days.map((dayKey) => {
    const totals = groupedByDay.get(dayKey) || { processed: 0, failed: 0 };
    const denominator = totals.processed + totals.failed;
    if (denominator <= 0) return 0;
    return Number(((totals.processed / denominator) * 100).toFixed(2));
  });
  const failedCount = days.map((dayKey) => {
    const totals = groupedByDay.get(dayKey) || { failed: 0 };
    return totals.failed;
  });

  canvas.hidden = false;
  empty.hidden = true;

  const context = canvas.getContext("2d");
  syncTrendChart = new Chart(context, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Success Rate (%)",
          data: successRate,
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.16)",
          yAxisID: "ySuccess",
          tension: 0.28,
          pointRadius: 3,
          borderWidth: 2,
        },
        {
          label: "Failed Count",
          data: failedCount,
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.16)",
          yAxisID: "yFailed",
          tension: 0.28,
          pointRadius: 3,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        ySuccess: {
          type: "linear",
          position: "left",
          min: 0,
          max: 100,
          ticks: {
            callback: (value) => `${value}%`,
          },
          title: { display: true, text: "Success Rate (%)" },
        },
        yFailed: {
          type: "linear",
          position: "right",
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Failed Count" },
        },
      },
    },
  });
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

function healthPillClass(state) {
  if (state === "critical") return "error";
  if (state === "degraded") return "warning";
  return "success";
}

function renderKpis(status, overview) {
  const kpis = [
    { label: "Auto Sync", value: status.autosync_enabled ? "On" : "Off" },
    { label: "Success Rate", value: `${status.success_rate || 0}%` },
    { label: "Events in Window", value: overview.totals?.events || 0 },
    { label: "Needs Review", value: overview.totals?.partial || 0 },
    { label: "Schedule Window", value: status.schedule?.window_open ? "Open" : "Closed" },
    { label: "Dedup Cache", value: status.dedup_metrics?.active_fingerprints || 0 },
  ];
  $("sync-kpis").innerHTML = kpis
    .map(
      (kpi) => `
      <div class="kpi">
        <div class="kpi-label">${kpi.label}</div>
        <div class="kpi-value">${kpi.value}</div>
      </div>
    `
    )
    .join("");

  const healthState = status.health_state || overview.health_state || "healthy";
  $("health-state-pill").textContent = formatLabel(healthState);
  $("health-state-pill").className = `pill ${healthPillClass(healthState)}`;
  $("worker-heartbeat").textContent = formatDate(status.worker_heartbeat_at);
  $("last-reconcile").textContent = formatDate(status.last_reconcile_at);
}

function renderQueueMetrics(metrics) {
  const entries = Object.entries(metrics || {});
  if (!entries.length) {
    $("queue-metrics").innerHTML = `<div class="muted">No queue metrics available.</div>`;
    return;
  }
  $("queue-metrics").innerHTML = entries
    .map(
      ([key, value]) => `
      <div class="event-item row spread">
        <span>${formatLabel(key)}</span><strong>${value}</strong>
      </div>
    `
    )
    .join("");
}

function renderEvents(containerId, events) {
  const container = $(containerId);
  if (!events || !events.length) {
    container.innerHTML = `<div class="muted">No activity for this time range.</div>`;
    return;
  }
  container.innerHTML = events
    .map(
      (event) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${formatLabel(event.event_type || "event")} (${formatLabel(event.status || "unknown")})</strong>
          <span>#${event.id || ""}</span>
        </div>
        <div class="muted">${formatDate(event.created_at)} | ${event.identifier || "-"}</div>
      </div>
    `
    )
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function retryIdentifiers(events) {
  const identifiers = new Set();
  (events || []).forEach((event) => {
    const identifier = String(event?.identifier || "").trim();
    if (identifier) {
      identifiers.add(identifier);
    }
  });
  return Array.from(identifiers);
}

function updateRetryAllFailedButton(events) {
  const button = $("retry-all-failed-btn");
  if (!button) return;
  failedPartialRetryIdentifiers = retryIdentifiers(events);
  const count = failedPartialRetryIdentifiers.length;
  button.textContent = `Retry All Failed (${count})`;
  button.disabled = count === 0;
}

function renderAttentionEvents(events) {
  const container = $("failed-partial-events");
  if (!container) return;
  updateRetryAllFailedButton(events);
  if (!events || !events.length) {
    container.innerHTML = `<div class="muted">No activity for this time range.</div>`;
    return;
  }
  container.innerHTML = events
    .map((event) => {
      const identifier = String(event?.identifier || "").trim();
      const retryButton = identifier
        ? `<button class="soft btn-xs retry-item-btn" data-identifier="${escapeHtml(
            identifier
          )}" type="button" title="Retry this identifier">↺ Retry</button>`
        : `<button class="ghost btn-xs retry-item-btn" type="button" disabled title="Identifier unavailable">↺ Retry</button>`;
      return `
      <div class="event-item">
        <div class="row spread">
          <strong>${formatLabel(event.event_type || "event")} (${formatLabel(event.status || "unknown")})</strong>
          <span class="row">
            <span>#${event.id || ""}</span>
            ${retryButton}
          </span>
        </div>
        <div class="muted">${formatDate(event.created_at)} | ${identifier || "-"}</div>
      </div>
    `;
    })
    .join("");
}

function renderAuditHistory(items) {
  const container = $("sync-audit-history");
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = `<div class="muted">No sync runs recorded yet.</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
      <div class="event-item">
        <div class="row spread">
          <strong>${formatLabel(item.run_type)} (${formatLabel(item.trigger)})</strong>
          <span>#${item.id || "-"}</span>
        </div>
        <div class="muted">
          Completed: ${formatDate(item.completed_at)} | Duration: ${item.duration_ms || 0}ms | Processed: ${
        item.processed || 0
      } | Failed: ${item.failed || 0}
        </div>
      </div>
    `
    )
    .join("");
}

function renderDiffHistory(auditItems) {
  const container = $("sync-diff-history");
  if (!container) return;
  const entries = [];
  (auditItems || []).forEach((run) => {
    const notes = run && typeof run === "object" ? run.notes || {} : {};
    const preview = Array.isArray(notes.diff_preview) ? notes.diff_preview : [];
    preview.forEach((item) => {
      const diffs = Array.isArray(item.field_diffs) ? item.field_diffs : [];
      if (!diffs.length) return;
      entries.push({
        runId: run.id,
        completedAt: run.completed_at,
        identifier: item.identifier || "-",
        status: item.status || "-",
        action: item.action || "-",
        diffs,
      });
    });
  });

  if (!entries.length) {
    container.innerHTML = `<div class="muted">No field-level changes recorded yet.</div>`;
    return;
  }

  container.innerHTML = entries
    .slice(0, 80)
    .map((entry) => {
      const previewText = entry.diffs
        .slice(0, 3)
        .map((diff) => `${diff.field}: ${diff.before ?? "-"} -> ${diff.after ?? "-"}`)
        .join(" | ");
      const overflow = entry.diffs.length > 3 ? ` (+${entry.diffs.length - 3} more)` : "";
      return `
      <div class="event-item">
        <div class="row spread">
          <strong>${entry.identifier} (${formatLabel(entry.action)})</strong>
          <span>Run #${entry.runId || "-"}</span>
        </div>
        <div class="muted">${formatDate(entry.completedAt)} | ${formatLabel(entry.status)}</div>
        <div class="mono">${previewText}${overflow}</div>
      </div>
    `;
    })
    .join("");
}

async function loadData() {
  try {
    setLoading(true);
    const windowKey = $("overview-window").value;
    const [status, overview, health, audit] = await Promise.all([
      apiFetch("/api/sync/status"),
      apiFetch(`/api/sync/overview?window=${encodeURIComponent(windowKey)}`),
      apiFetch("/api/support/health"),
      apiFetch("/api/sync/audit?limit=40"),
    ]);
    renderKpis(status, overview);
    renderQueueMetrics(status.queue_metrics || {});
    const failedPartial = [...(status.failed_events || []), ...(status.partial_events || [])].slice(0, 30);
    renderEvents("failed-partial-events", failedPartial);
    renderEvents("recent-events", status.recent_events || []);
    renderAuditHistory(audit.items || []);
    renderDiffHistory(audit.items || []);
    renderTrendChart(audit.items || []);
    $("health-snapshot").textContent = JSON.stringify(
      {
        timestamp: health.timestamp,
        storage: health.storage,
        safe_config: health.safe_config,
        schedule: status.schedule,
        dedup_metrics: status.dedup_metrics,
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

$("sync-run-now-btn").addEventListener("click", () => {
  setLoading(true);
  apiFetch("/api/sync/run-now", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: true, process_limit: 100 }),
  })
    .then(() => {
      notify("Manual sync run completed.", "info");
      return loadData();
    })
    .catch((error) => notify(error.message, "error"))
    .finally(() => setLoading(false));
});

loadData().catch((error) => {
  setLoading(false);
  notify(`Could not load sync health: ${error.message}`, "error");
});

window.setInterval(() => loadData().catch(() => {}), 20000);
updateHealthDot().catch(() => {});
window.setInterval(() => updateHealthDot().catch(() => {}), 30000);
