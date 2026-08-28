"""Write-route governance — allowlist must equal mutating routes exactly."""

from ui.app import UI_WRITE_ROUTE_ALLOWLIST, app

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _mutating_routes():
    found = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for m in methods:
            if m in _WRITE_METHODS:
                found.add((m, path))
    return found


def test_ui_write_routes_match_allowlist_exactly():
    found = _mutating_routes()
    assert found == set(UI_WRITE_ROUTE_ALLOWLIST), (
        f"mutating routes {found} != allowlist {set(UI_WRITE_ROUTE_ALLOWLIST)}"
    )
    assert found == {
        ("POST", "/ask"),
        ("POST", "/run/{routine_id}"),
    }
