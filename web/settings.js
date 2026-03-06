const $ = (id) => document.getElementById(id);

const state = {
  envValues: {},
  coreKeys: [],
};

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
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
    wrapper.className = "card";
    wrapper.innerHTML = `
      <label for="core-${key}">${key}</label>
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
    body.innerHTML = `<tr><td colspan="3" class="muted">No additional variables.</td></tr>`;
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
  $("settings-message").textContent = reveal ? "Secrets are visible." : "Secrets are masked by default.";
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
  $("settings-message").textContent = "Settings saved.";
  notify("Environment settings saved.", "info");
  saveButton.classList.remove("is-busy");
}

async function withLoading(fn) {
  try {
    setLoading(true);
    await fn();
  } catch (error) {
    $("settings-message").textContent = `Error: ${error.message}`;
    notify(`Settings error: ${error.message}`, "error");
  } finally {
    setLoading(false);
    $("save-env-btn").classList.remove("is-busy");
  }
}

$("reload-env-btn").addEventListener("click", () => withLoading(loadEnv));
$("save-env-btn").addEventListener("click", () => withLoading(saveEnv));
$("secret-toggle").addEventListener("change", () => withLoading(loadEnv));
$("add-env-row-btn").addEventListener("click", addAdditionalRow);

withLoading(loadEnv);
