def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_dashboard_page_has_required_features(web_dir):
    html = _read(web_dir / "index.html")
    for required in [
        "kaseya-table",
        "revnue-table",
        "transfer-selected-btn",
        "transfer-modal",
        "activity-modal",
        "autosync-navbar-toggle",
        "only-missing-toggle",
        "history-list",
        "loading-overlay",
    ]:
        assert required in html


def test_sync_status_page_has_required_sections(web_dir):
    html = _read(web_dir / "sync-status.html")
    for required in [
        "sync-kpis",
        "queue-metrics",
        "recent-events",
        "failed-partial-events",
        "health-snapshot",
        "worker-heartbeat",
    ]:
        assert required in html


def test_settings_page_has_required_controls(web_dir):
    html = _read(web_dir / "settings.html")
    for required in [
        "env-editor",
        "secret-toggle",
        "save-env-btn",
        "reload-env-btn",
        "core-env-grid",
        "additional-env-table",
    ]:
        assert required in html


def test_support_page_has_required_tools(web_dir):
    html = _read(web_dir / "support.html")
    for required in [
        "diagnostics-viewer",
        "connectivity-btn",
        "submit-ticket-btn",
        "ticket-history",
        "export-diagnostics-btn",
        "safe-config-viewer",
        "failed-partial-activity",
    ]:
        assert required in html
