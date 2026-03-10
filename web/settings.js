const $ = (id) => document.getElementById(id);

const state = {
  envValues: {},
  coreKeys: [],
  authRequired: false,
  authenticated: false,
  scheduleRows: [],
  scheduleUnparsed: [],
  scheduleRowSeed: 0,
};

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object" && parsed.detail) {
        message = String(parsed.detail);
      }
    } catch (_error) {
      // keep raw text fallback
    }
    throw new Error(message || `Request failed: ${response.status}`);
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
  window.setTimeout(() => toast.remove(), 2600);
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

function formatDate(isoDate) {
  if (!isoDate) return "-";
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed.toLocaleString();
}

const SCHEDULE_DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
const SCHEDULE_DAY_LABELS = {
  0: "Sun",
  1: "Mon",
  2: "Tue",
  3: "Wed",
  4: "Thu",
  5: "Fri",
  6: "Sat",
};

function nextScheduleRowId() {
  state.scheduleRowSeed += 1;
  return `schedule-row-${state.scheduleRowSeed}`;
}

function normalizeScheduleDays(days) {
  const daySet = new Set(
    (days || [])
      .map((day) => Number(day))
      .filter((day) => Number.isInteger(day) && SCHEDULE_DAY_ORDER.includes(day))
  );
  return SCHEDULE_DAY_ORDER.filter((day) => daySet.has(day));
}

function createScheduleRow(config = {}) {
  const normalizedDays = normalizeScheduleDays(config.days);
  let startHour = Number(config.startHour);
  if (!Number.isInteger(startHour) || startHour < 0 || startHour > 23) {
    startHour = 9;
  }
  let endHour = Number(config.endHour);
  if (!Number.isInteger(endHour) || endHour < 1 || endHour > 24) {
    endHour = Math.min(24, startHour + 8);
  }
  if (endHour <= startHour) {
    endHour = Math.min(24, startHour + 1);
  }
  return {
    id: nextScheduleRowId(),
    days: normalizedDays.length ? normalizedDays : [1, 2, 3, 4, 5],
    startHour,
    endHour,
  };
}

function splitScheduleExpressions(rawValue) {
  return String(rawValue || "")
    .replace(/\r/g, "")
    .split(/[\n;]+/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function parseCronDayField(weekdayField) {
  const expr = String(weekdayField || "").trim();
  if (!expr || expr === "*") {
    return [...SCHEDULE_DAY_ORDER];
  }
  if (expr.includes("/")) {
    return null;
  }
  const values = [];
  const tokens = expr.split(",").map((token) => token.trim()).filter(Boolean);
  for (const token of tokens) {
    if (token.includes("-")) {
      const [rawStart, rawEnd] = token.split("-", 2);
      const start = Number(rawStart);
      const end = Number(rawEnd);
      if (!Number.isInteger(start) || !Number.isInteger(end)) {
        return null;
      }
      const normalizedStart = start === 7 ? 0 : start;
      const normalizedEnd = end === 7 ? 0 : end;
      if (
        normalizedStart < 0 ||
        normalizedStart > 6 ||
        normalizedEnd < 0 ||
        normalizedEnd > 6 ||
        normalizedStart > normalizedEnd
      ) {
        return null;
      }
      for (let day = normalizedStart; day <= normalizedEnd; day += 1) {
        values.push(day);
      }
      continue;
    }
    const numeric = Number(token);
    if (!Number.isInteger(numeric)) {
      return null;
    }
    const normalized = numeric === 7 ? 0 : numeric;
    if (normalized < 0 || normalized > 6) {
      return null;
    }
    values.push(normalized);
  }
  const normalizedValues = normalizeScheduleDays(values);
  return normalizedValues.length ? normalizedValues : null;
}

function parseCronHourField(hourField) {
  const expr = String(hourField || "").trim();
  if (!expr || expr === "*") {
    return [{ startHour: 0, endHour: 24 }];
  }
  if (expr.includes("/")) {
    return null;
  }
  const ranges = [];
  const tokens = expr.split(",").map((token) => token.trim()).filter(Boolean);
  for (const token of tokens) {
    if (token.includes("-")) {
      const [rawStart, rawEnd] = token.split("-", 2);
      const start = Number(rawStart);
      const end = Number(rawEnd);
      if (!Number.isInteger(start) || !Number.isInteger(end)) {
        return null;
      }
      if (start < 0 || end > 23 || start > end) {
        return null;
      }
      ranges.push({ startHour: start, endHour: end + 1 });
      continue;
    }
    const numeric = Number(token);
    if (!Number.isInteger(numeric) || numeric < 0 || numeric > 23) {
      return null;
    }
    ranges.push({ startHour: numeric, endHour: numeric + 1 });
  }
  return ranges.length ? ranges : null;
}

function parseScheduleExpression(expression) {
  const fields = String(expression || "").trim().split(/\s+/);
  if (fields.length !== 5) {
    return null;
  }
  const [minuteField, hourField, dayField, monthField, weekdayField] = fields;
  if (minuteField !== "*" || dayField !== "*" || monthField !== "*") {
    return null;
  }
  const days = parseCronDayField(weekdayField);
  const hourRanges = parseCronHourField(hourField);
  if (!days || !hourRanges) {
    return null;
  }
  return hourRanges.map((range) =>
    createScheduleRow({
      days,
      startHour: range.startHour,
      endHour: range.endHour,
    })
  );
}

function setAuthView() {
  const needsUnlock = state.authRequired && !state.authenticated;
  const authCard = $("settings-auth-card");
  const content = $("settings-content");
  const logoutButton = $("settings-logout-btn");
  if (authCard) authCard.hidden = !needsUnlock;
  if (content) content.hidden = needsUnlock;
  if (logoutButton) logoutButton.hidden = !(state.authRequired && state.authenticated);
}

async function refreshAuthStatus() {
  const status = await apiFetch("/api/auth/status");
  state.authRequired = !!status.required;
  state.authenticated = !!status.authenticated;
  setAuthView();
}

function toEditorText(values) {
  return Object.entries(values)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
}

function parseEditorText(text) {
  const lines = text.split("\n");
  const values = {};
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    const equalIndex = trimmed.indexOf("=");
    if (equalIndex < 0) return;
    const key = trimmed.slice(0, equalIndex).trim();
    const value = trimmed.slice(equalIndex + 1);
    if (key) values[key] = value;
  });
  return values;
}

function scheduleDayLabel(days) {
  const normalized = normalizeScheduleDays(days);
  if (normalized.length === 7) return "Every day";
  return normalized.map((day) => SCHEDULE_DAY_LABELS[day]).join(", ");
}

function scheduleHourLabel(hour) {
  const clamped = Math.max(0, Math.min(24, Number(hour)));
  return `${String(clamped).padStart(2, "0")}:00`;
}

function scheduleHourExpression(startHour, endHour) {
  if (startHour <= 0 && endHour >= 24) {
    return "*";
  }
  if (endHour <= startHour + 1) {
    return String(startHour);
  }
  return `${startHour}-${endHour - 1}`;
}

function scheduleDayExpression(days) {
  const normalized = normalizeScheduleDays(days);
  return normalized.length === 7 ? "*" : normalized.join(",");
}

function scheduleExpressionFromRow(row) {
  return `* ${scheduleHourExpression(row.startHour, row.endHour)} * * ${scheduleDayExpression(row.days)}`;
}

function scheduleSummary(row) {
  return `${scheduleDayLabel(row.days)} | ${scheduleHourLabel(row.startHour)}-${scheduleHourLabel(row.endHour)}`;
}

function serializeScheduleRows() {
  const generated = state.scheduleRows.map((row) => scheduleExpressionFromRow(row));
  return [...generated, ...state.scheduleUnparsed].join("; ");
}

function updateSchedulePreview() {
  const preview = $("schedule-preview");
  if (!preview) return;
  const generated = state.scheduleRows.map((row) => ({
    summary: scheduleSummary(row),
    expression: scheduleExpressionFromRow(row),
  }));
  const lines = [];
  if (!generated.length && !state.scheduleUnparsed.length) {
    lines.push("Always open: no schedule windows are configured.");
    lines.push("Saved value: (empty)");
    preview.textContent = lines.join("\n");
    return;
  }
  generated.forEach((item, index) => {
    lines.push(`Window ${index + 1}: ${item.summary}`);
    lines.push(`  ${item.expression}`);
  });
  if (state.scheduleUnparsed.length) {
    lines.push("");
    lines.push("Preserved custom cron windows:");
    state.scheduleUnparsed.forEach((expression) => lines.push(`  ${expression}`));
  }
  lines.push("");
  lines.push(`Saved value: ${serializeScheduleRows()}`);
  preview.textContent = lines.join("\n");
}

function syncScheduleToEnvEditor() {
  state.envValues.AUTOSYNC_CRON_WINDOWS = serializeScheduleRows();
  syncRawEditor();
  updateSchedulePreview();
}

function loadScheduleFromEnv(rawValue) {
  const expressions = splitScheduleExpressions(rawValue);
  const parsedRows = [];
  const unparsed = [];
  expressions.forEach((expression) => {
    const rows = parseScheduleExpression(expression);
    if (!rows || !rows.length) {
      unparsed.push(expression);
      return;
    }
    parsedRows.push(...rows);
  });
  state.scheduleRows = parsedRows;
  state.scheduleUnparsed = unparsed;
  renderScheduleRows();
  updateSchedulePreview();
}

function renderScheduleRows() {
  const container = $("schedule-window-list");
  if (!container) return;
  if (!state.scheduleRows.length) {
    container.innerHTML = `<div class="schedule-window-empty">No windows configured. Autosync is currently allowed at all times.</div>`;
  } else {
    container.innerHTML = state.scheduleRows
      .map((row, index) => {
        const endHour = row.endHour <= row.startHour ? Math.min(24, row.startHour + 1) : row.endHour;
        row.endHour = endHour;
        const dayButtons = SCHEDULE_DAY_ORDER.map((day) => {
          const active = row.days.includes(day) ? " active" : "";
          return `<button type="button" class="schedule-day-btn${active}" data-row-id="${row.id}" data-day="${day}">${SCHEDULE_DAY_LABELS[day]}</button>`;
        }).join("");
        const startOptions = Array.from({ length: 24 }, (_, hour) => {
          const selected = hour === row.startHour ? " selected" : "";
          return `<option value="${hour}"${selected}>${scheduleHourLabel(hour)}</option>`;
        }).join("");
        const endOptions = Array.from({ length: 24 - row.startHour }, (_, offset) => {
          const hour = row.startHour + 1 + offset;
          const selected = hour === row.endHour ? " selected" : "";
          return `<option value="${hour}"${selected}>${scheduleHourLabel(hour)}</option>`;
        }).join("");
        return `
          <article class="schedule-window-row">
            <div class="row spread">
              <strong>Window ${index + 1}</strong>
              <button type="button" class="danger btn-sm schedule-remove-btn" data-row-id="${row.id}">Remove</button>
            </div>
            <div class="schedule-day-grid" role="group" aria-label="Select days for window ${index + 1}">
              ${dayButtons}
            </div>
            <div class="schedule-hours">
              <label class="field-label-inline" for="schedule-start-${row.id}">Start</label>
              <select id="schedule-start-${row.id}" class="schedule-start-select" data-row-id="${row.id}">
                ${startOptions}
              </select>
              <label class="field-label-inline" for="schedule-end-${row.id}">End</label>
              <select id="schedule-end-${row.id}" class="schedule-end-select" data-row-id="${row.id}">
                ${endOptions}
              </select>
              <span class="muted">${scheduleSummary(row)}</span>
            </div>
          </article>
        `;
      })
      .join("");
  }
  if (state.scheduleUnparsed.length) {
    const note = document.createElement("div");
    note.className = "schedule-window-empty";
    note.textContent = `${state.scheduleUnparsed.length} custom cron window(s) were preserved as-is.`;
    container.appendChild(note);
  }
}

function findScheduleRow(rowId) {
  return state.scheduleRows.find((row) => row.id === rowId) || null;
}

function updateScheduleStatusPill(snapshot, errorMessage = "") {
  const pill = $("schedule-window-status");
  if (!pill) return;
  if (errorMessage) {
    pill.className = "pill error";
    pill.textContent = `Status unavailable: ${errorMessage}`;
    return;
  }
  const windowCount = Array.isArray(snapshot?.windows) ? snapshot.windows.length : 0;
  const nowLabel = formatDate(snapshot?.now_local || snapshot?.now_utc);
  if (!snapshot?.enabled) {
    pill.className = "pill info";
    pill.textContent = `Always open | ${nowLabel}`;
    return;
  }
  if (snapshot.window_open) {
    pill.className = "pill success";
    pill.textContent = `Open now | ${windowCount} windows | ${nowLabel}`;
    return;
  }
  pill.className = "pill warning";
  pill.textContent = `Closed now | ${windowCount} windows | ${nowLabel}`;
}

async function refreshScheduleStatus() {
  try {
    const snapshot = await apiFetch("/api/sync/schedule");
    updateScheduleStatusPill(snapshot);
  } catch (error) {
    updateScheduleStatusPill(null, error.message);
    throw error;
  }
}

function addScheduleWindow() {
  state.scheduleRows.push(
    createScheduleRow({
      days: [1, 2, 3, 4, 5],
      startHour: 9,
      endHour: 17,
    })
  );
  renderScheduleRows();
  syncScheduleToEnvEditor();
}

function onScheduleListClick(event) {
  const removeButton = event.target.closest(".schedule-remove-btn");
  if (removeButton) {
    const rowId = removeButton.getAttribute("data-row-id");
    if (!rowId) return;
    state.scheduleRows = state.scheduleRows.filter((row) => row.id !== rowId);
    renderScheduleRows();
    syncScheduleToEnvEditor();
    return;
  }

  const dayButton = event.target.closest(".schedule-day-btn");
  if (!dayButton) return;
  const rowId = dayButton.getAttribute("data-row-id");
  const day = Number(dayButton.getAttribute("data-day"));
  if (!rowId || !Number.isInteger(day)) return;
  const row = findScheduleRow(rowId);
  if (!row) return;
  const selectedDays = new Set(row.days);
  if (selectedDays.has(day)) {
    if (selectedDays.size === 1) {
      notify("Each window must include at least one day.", "warning");
      return;
    }
    selectedDays.delete(day);
  } else {
    selectedDays.add(day);
  }
  row.days = normalizeScheduleDays([...selectedDays]);
  renderScheduleRows();
  syncScheduleToEnvEditor();
}

function onScheduleListChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) return;
  const rowId = target.getAttribute("data-row-id");
  if (!rowId) return;
  const row = findScheduleRow(rowId);
  if (!row) return;
  const numeric = Number(target.value);
  if (!Number.isInteger(numeric)) return;
  if (target.classList.contains("schedule-start-select")) {
    row.startHour = Math.max(0, Math.min(23, numeric));
    if (row.endHour <= row.startHour) {
      row.endHour = Math.min(24, row.startHour + 1);
    }
  } else if (target.classList.contains("schedule-end-select")) {
    row.endHour = Math.max(1, Math.min(24, numeric));
    if (row.endHour <= row.startHour) {
      row.endHour = Math.min(24, row.startHour + 1);
    }
  } else {
    return;
  }
  renderScheduleRows();
  syncScheduleToEnvEditor();
}

async function saveScheduleWindows() {
  const saveButton = $("save-schedule-btn");
  if (saveButton) {
    saveButton.classList.add("is-busy");
  }
  const value = serializeScheduleRows();
  state.envValues.AUTOSYNC_CRON_WINDOWS = value;
  syncRawEditor();
  await apiFetch("/api/settings/env", {
    method: "POST",
    body: JSON.stringify({ values: { AUTOSYNC_CRON_WINDOWS: value } }),
  });
  await loadEnv();
  await refreshScheduleStatus();
  $("settings-message").textContent = "Sync schedule saved.";
  notify("Sync schedule saved.", "info");
  if (saveButton) {
    saveButton.classList.remove("is-busy");
  }
}

function renderCoreInputs() {
  const container = $("core-env-grid");
  container.innerHTML = "";
  state.coreKeys.forEach((key) => {
    const wrapper = document.createElement("div");
    wrapper.className = "card inset env-field";
    wrapper.innerHTML = `
      <label class="field-label" for="core-${key}">${key}</label>
      <input id="core-${key}" data-key="${key}" type="text" value="${state.envValues[key] || ""}" />
    `;
    container.appendChild(wrapper);
  });

  container.querySelectorAll("input[data-key]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const key = event.target.getAttribute("data-key");
      if (!key) return;
      state.envValues[key] = event.target.value;
      if (key === "AUTOSYNC_CRON_WINDOWS") {
        loadScheduleFromEnv(state.envValues[key]);
      }
      syncRawEditor();
    });
  });
}

function additionalRows() {
  return Object.entries(state.envValues).filter(([key]) => !state.coreKeys.includes(key));
}

function renderAdditionalRows() {
  const body = $("additional-env-table").querySelector("tbody");
  const rows = additionalRows();
  body.innerHTML = "";
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="3" class="muted">No extra settings added yet.</td></tr>`;
    return;
  }
  rows.forEach(([key, value]) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input class="additional-key" data-key="${key}" type="text" value="${key}" /></td>
      <td><input class="additional-value" data-key="${key}" type="text" value="${value || ""}" /></td>
      <td><button class="danger remove-env-btn" data-key="${key}">Remove</button></td>
    `;
    body.appendChild(row);
  });

  body.querySelectorAll(".additional-value").forEach((input) => {
    input.addEventListener("input", (event) => {
      const key = event.target.getAttribute("data-key");
      if (!key) return;
      state.envValues[key] = event.target.value;
      syncRawEditor();
    });
  });
  body.querySelectorAll(".additional-key").forEach((input) => {
    input.addEventListener("change", (event) => {
      const oldKey = event.target.getAttribute("data-key");
      const newKey = event.target.value.trim();
      if (!oldKey || !newKey || oldKey === newKey) return;
      state.envValues[newKey] = state.envValues[oldKey];
      delete state.envValues[oldKey];
      renderAdditionalRows();
      syncRawEditor();
    });
  });
  body.querySelectorAll(".remove-env-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      const key = event.target.getAttribute("data-key");
      if (!key) return;
      delete state.envValues[key];
      renderAdditionalRows();
      syncRawEditor();
    });
  });
}

function syncRawEditor() {
  $("env-editor").value = toEditorText(state.envValues);
}

async function loadEnv() {
  const reveal = $("secret-toggle").checked;
  const data = await apiFetch(`/api/settings/env?reveal_secrets=${reveal ? "true" : "false"}`);
  state.envValues = { ...(data.values || {}) };
  state.coreKeys = data.core_keys || [];
  renderCoreInputs();
  renderAdditionalRows();
  loadScheduleFromEnv(state.envValues.AUTOSYNC_CRON_WINDOWS || "");
  syncRawEditor();
  $("settings-message").textContent = reveal
    ? "Sensitive values are currently visible."
    : "Sensitive values are hidden.";
}

async function loginSettings() {
  const password = $("settings-password").value;
  if (!password.trim()) {
    $("settings-auth-message").textContent = "Password is required.";
    return;
  }
  await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  $("settings-password").value = "";
  $("settings-auth-message").textContent = "Access granted.";
  await refreshAuthStatus();
  if (!state.authRequired || state.authenticated) {
    await loadEnv();
    await refreshScheduleStatus();
    notify("Settings unlocked.", "info");
  }
}

async function logoutSettings() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  await refreshAuthStatus();
  $("settings-auth-message").textContent = "Settings locked.";
  notify("Settings locked.", "info");
}

async function testNotification() {
  const result = await apiFetch("/api/support/notifications/test", { method: "POST" });
  if (result.sent) {
    notify("Test notification sent successfully.", "info");
    $("settings-message").textContent = "Test notification sent.";
  } else if (result.reason === "not_configured") {
    notify("Set OUTBOUND_WEBHOOK_URL first to enable notifications.", "warning");
    $("settings-message").textContent = "Notification endpoint is not configured.";
  } else {
    notify("Notification test failed.", "error");
    $("settings-message").textContent = "Notification test failed. Check logs for details.";
  }
}

function addAdditionalRow() {
  let index = 1;
  let key = `NEW_VAR_${index}`;
  while (state.envValues[key] !== undefined) {
    index += 1;
    key = `NEW_VAR_${index}`;
  }
  state.envValues[key] = "";
  renderAdditionalRows();
  syncRawEditor();
}

async function saveEnv() {
  // Raw editor wins for final serialization if manually edited.
  state.envValues = parseEditorText($("env-editor").value);
  const saveButton = $("save-env-btn");
  saveButton.classList.add("is-busy");
  const data = await apiFetch("/api/settings/env", {
    method: "POST",
    body: JSON.stringify({ values: state.envValues }),
  });
  state.envValues = { ...(data.values || {}) };
  renderCoreInputs();
  renderAdditionalRows();
  loadScheduleFromEnv(state.envValues.AUTOSYNC_CRON_WINDOWS || "");
  syncRawEditor();
  $("settings-message").textContent = "Configuration saved.";
  notify("Configuration saved successfully.", "info");
  saveButton.classList.remove("is-busy");
}

async function withLoading(fn) {
  try {
    setLoading(true);
    await fn();
  } catch (error) {
    if (String(error.message).includes("settings_auth_required")) {
      state.authenticated = false;
      setAuthView();
      $("settings-auth-message").textContent = "Session expired. Enter password again.";
      notify("Settings access expired. Please unlock again.", "warning");
    } else {
      $("settings-message").textContent = `Could not save configuration: ${error.message}`;
      notify(`Configuration error: ${error.message}`, "error");
    }
  } finally {
    setLoading(false);
    if ($("save-env-btn")) {
      $("save-env-btn").classList.remove("is-busy");
    }
    if ($("save-schedule-btn")) {
      $("save-schedule-btn").classList.remove("is-busy");
    }
  }
}

$("reload-env-btn").addEventListener("click", () => withLoading(loadEnv));
$("save-env-btn").addEventListener("click", () => withLoading(saveEnv));
$("secret-toggle").addEventListener("change", () => withLoading(loadEnv));
$("add-env-row-btn").addEventListener("click", addAdditionalRow);
$("add-schedule-window-btn").addEventListener("click", addScheduleWindow);
$("save-schedule-btn").addEventListener("click", () => withLoading(saveScheduleWindows));
$("settings-login-btn").addEventListener("click", () => withLoading(loginSettings));
$("settings-logout-btn").addEventListener("click", () => withLoading(logoutSettings));
$("test-notify-btn").addEventListener("click", () => withLoading(testNotification));
$("schedule-window-list").addEventListener("click", onScheduleListClick);
$("schedule-window-list").addEventListener("change", onScheduleListChange);
$("settings-password").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    withLoading(loginSettings);
  }
});

withLoading(async () => {
  await refreshAuthStatus();
  if (state.authRequired && !state.authenticated) {
    $("settings-auth-message").textContent = "Please unlock settings to continue.";
    return;
  }
  await Promise.all([loadEnv(), refreshScheduleStatus()]);
});

updateHealthDot().catch(() => {});
window.setInterval(() => updateHealthDot().catch(() => {}), 30000);
window.setInterval(() => refreshScheduleStatus().catch(() => {}), 60000);
