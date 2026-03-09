(function initSidebarToggle() {
  const toggleButton = document.getElementById("sidebar-toggle-btn");
  const sidebar = document.getElementById("dashboard-sidebar");
  const shell = document.querySelector(".app-shell");
  if (!toggleButton || !sidebar || !shell) return;

  const storageKey = "asset_sync_sidebar_collapsed";
  const mobileQuery = window.matchMedia("(max-width: 768px)");

  function persistCollapsed(collapsed) {
    storedValue = collapsed ? "1" : "0";
    try {
      window.localStorage.setItem(storageKey, collapsed ? "1" : "0");
    } catch (_error) {
      // Ignore storage write failures and keep UI behavior.
    }
  }

  function setCollapsed(collapsed) {
    sidebar.classList.toggle("collapsed", collapsed);
    shell.classList.toggle("menu-collapsed", collapsed);
    toggleButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }

  let storedValue = null;
  try {
    storedValue = window.localStorage.getItem(storageKey);
  } catch (_error) {
    storedValue = null;
  }
  const defaultCollapsed = mobileQuery.matches;
  setCollapsed(storedValue === null ? defaultCollapsed : storedValue === "1");

  toggleButton.addEventListener("click", () => {
    const collapsed = !sidebar.classList.contains("collapsed");
    setCollapsed(collapsed);
    persistCollapsed(collapsed);
  });

  document.addEventListener("click", (event) => {
    if (!mobileQuery.matches || sidebar.classList.contains("collapsed")) return;
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (sidebar.contains(target) || toggleButton.contains(target)) return;
    setCollapsed(true);
    persistCollapsed(true);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!mobileQuery.matches || sidebar.classList.contains("collapsed")) return;
    setCollapsed(true);
    persistCollapsed(true);
  });

  const onViewportChange = () => {
    if (storedValue !== null) return;
    setCollapsed(mobileQuery.matches);
  };
  if (typeof mobileQuery.addEventListener === "function") {
    mobileQuery.addEventListener("change", onViewportChange);
  } else if (typeof mobileQuery.addListener === "function") {
    mobileQuery.addListener(onViewportChange);
  }
})();
