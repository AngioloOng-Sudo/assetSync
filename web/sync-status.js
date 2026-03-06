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

function formatLabel(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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
        <div class="muted">${kpi.label}</div>
        <div class="value">${kpi.value}</div>
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
