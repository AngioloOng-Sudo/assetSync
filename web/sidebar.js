(function initSidebarToggle() {
  const toggleButton = document.getElementById("sidebar-toggle-btn");
  const sidebar = document.getElementById("dashboard-sidebar");
  const shell = document.querySelector(".app-shell");
  if (!toggleButton || !sidebar || !shell) return;

  const storageKey = "asset_sync_sidebar_collapsed";

  function setCollapsed(collapsed) {
    sidebar.classList.toggle("collapsed", collapsed);
    shell.classList.toggle("menu-collapsed", collapsed);
  }

  try {
    const storedValue = window.localStorage.getItem(storageKey);
    setCollapsed(storedValue === "1");
  } catch (_error) {
    setCollapsed(false);
  }

  toggleButton.addEventListener("click", () => {
    const collapsed = !sidebar.classList.contains("collapsed");
    setCollapsed(collapsed);
    try {
      window.localStorage.setItem(storageKey, collapsed ? "1" : "0");
    } catch (_error) {
      // Ignore storage write failures and keep UI behavior.
    }
  });
})();
