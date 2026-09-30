"""RBAC-001: every API route declares a permission, public or authenticated-only marker."""

from fastapi.routing import APIRoute

from app.api.main import ROUTERS


def _routes():
    for router, prefix in ROUTERS:
        for route in router.routes:
            assert isinstance(route, APIRoute)
            yield prefix + route.path, route


def _markers(route: APIRoute) -> set[str]:
    found = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = dep.call
        if getattr(call, "required_permission", None) is not None:
            found.add("permission")
        if getattr(call, "is_public", False):
            found.add("public")
        if getattr(call, "is_authenticated_only", False):
            found.add("authenticated")
        stack.extend(dep.dependencies)
    return found


def test_routes_are_discovered():
    assert len(list(_routes())) > 30


def test_every_route_declares_access():
    missing = [f"{sorted(r.methods)} {path}" for path, r in _routes() if not _markers(r)]
    assert missing == []


def test_public_routes_are_the_expected_few():
    public = sorted(path for path, r in _routes() if "public" in _markers(r))
    assert public == sorted(
        [
            "/healthz",
            "/readyz",
            "/api/v1/system/version",
            "/api/v1/setup/status",
            "/api/v1/setup",
            "/api/v1/auth/login",
        ]
    )
