"""Unit tests for api-gateway/src/middleware/rbac.py."""
import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))

from fastapi import HTTPException  # noqa: E402
from src.middleware.rbac import require_role, require_min_role  # noqa: E402


def _fake_request(role: str | None):
    request = MagicMock()
    if role is None:
        request.state = MagicMock(spec=[])  # no `role` attribute at all -> getattr fallback
    else:
        request.state = MagicMock(spec=["role"])
        request.state.role = role
    return request


class TestRequireRole:
    def test_allows_matching_role(self):
        checker = require_role("admin").dependency
        request = _fake_request("admin")
        assert checker(request) == "admin"

    def test_rejects_non_matching_role(self):
        checker = require_role("admin").dependency
        request = _fake_request("engineer")
        with pytest.raises(HTTPException) as exc_info:
            checker(request)
        assert exc_info.value.status_code == 403

    def test_allows_any_of_multiple_roles(self):
        checker = require_role("admin", "engineer").dependency
        assert checker(_fake_request("engineer")) == "engineer"

    def test_missing_role_defaults_to_readonly_and_is_rejected(self):
        checker = require_role("admin").dependency
        request = _fake_request(None)
        with pytest.raises(HTTPException) as exc_info:
            checker(request)
        assert "readonly" in exc_info.value.detail


class TestRequireMinRole:
    @pytest.mark.parametrize(
        "role,min_role,should_pass",
        [
            ("admin", "analyst", True),
            ("engineer", "analyst", True),
            ("analyst", "analyst", True),
            ("auditor", "analyst", False),
            ("readonly", "analyst", False),
            ("admin", "admin", True),
            ("engineer", "admin", False),
        ],
    )
    def test_hierarchy_enforced(self, role, min_role, should_pass):
        checker = require_min_role(min_role).dependency
        request = _fake_request(role)
        if should_pass:
            assert checker(request) == role
        else:
            with pytest.raises(HTTPException) as exc_info:
                checker(request)
            assert exc_info.value.status_code == 403

    def test_unknown_role_treated_as_below_readonly(self):
        checker = require_min_role("readonly").dependency
        request = _fake_request("some-made-up-role")
        with pytest.raises(HTTPException):
            checker(request)

    def test_missing_role_defaults_to_readonly(self):
        checker = require_min_role("readonly").dependency
        request = _fake_request(None)
        # readonly >= readonly -> passes even with no role set at all
        assert checker(request) == "readonly"
