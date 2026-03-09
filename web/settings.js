const $ = (id) => document.getElementById(id);

const state = {
  envValues: {},
  coreKeys: [],
  authRequired: false,
  authenticated: false,
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
  }
}

$("reload-env-btn").addEventListener("click", () => withLoading(loadEnv));
$("save-env-btn").addEventListener("click", () => withLoading(saveEnv));
$("secret-toggle").addEventListener("change", () => withLoading(loadEnv));
$("add-env-row-btn").addEventListener("click", addAdditionalRow);
$("settings-login-btn").addEventListener("click", () => withLoading(loginSettings));
$("settings-logout-btn").addEventListener("click", () => withLoading(logoutSettings));
$("test-notify-btn").addEventListener("click", () => withLoading(testNotification));
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
  await loadEnv();
});
