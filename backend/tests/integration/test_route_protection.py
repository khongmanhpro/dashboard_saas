"""Mọi route đều phải được bảo vệ, trừ danh sách công khai ghi rõ ở đây.

Thêm route mới mà quên `require(Perm.X)` thì test này fail.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.deps import get_auth_context, get_session_context
from app.main import app

pytestmark = pytest.mark.integration

PUBLIC = {"/healthz", "/readyz", "/api/config", "/api/auth/login"}
# Chỉ cần đăng nhập, dùng được cả khi đang bị bắt đổi mật khẩu.
SESSION_ONLY = {"/api/me", "/api/auth/logout", "/api/auth/change-password"}


def _calls(dep: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dep.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


@dataclass(frozen=True)
class RouteInfo:
    path: str
    methods: frozenset[str]
    dependant: Dependant


def _walk(routes: list[Any]) -> Iterator[RouteInfo]:
    for r in routes:
        if isinstance(r, APIRoute):
            yield RouteInfo(r.path, frozenset(r.methods), r.dependant)
        elif hasattr(r, "effective_route_contexts"):
            # FastAPI mới bọc router con trong _IncludedRouter.
            for c in r.effective_route_contexts():
                yield RouteInfo(c.path, frozenset(c.methods or ()), c.dependant)


def _routes() -> list[RouteInfo]:
    return list(_walk(app.routes))


def test_route_list_is_known() -> None:
    assert {r.path for r in _routes()} >= PUBLIC | SESSION_ONLY


@pytest.mark.parametrize("route", _routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_route_is_protected(route: RouteInfo) -> None:
    calls = list(_calls(route.dependant))
    if route.path in PUBLIC:
        assert get_session_context not in calls, "route công khai không nên đòi đăng nhập"
        return
    assert get_session_context in calls, f"{route.path} chưa kiểm tra đăng nhập"
    if route.path in SESSION_ONLY:
        return
    assert get_auth_context in calls, f"{route.path} chưa chặn người đang bị bắt đổi mật khẩu"
    perms = [getattr(c, "required_permission", None) for c in calls]
    assert any(perms), f"{route.path} chưa khai báo require(Perm.X)"
