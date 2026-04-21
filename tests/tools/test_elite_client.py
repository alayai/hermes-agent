"""Tests for the Elite HTTP client module.

Tests authentication, token caching, request handling, error recovery,
and availability checking.
"""

import json
import os
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import httpx

from tools.elite_client import (
    EliteClient,
    EliteAuthError,
    check_elite_available,
    safe_elite_call,
    _elite_requires_env,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_client():
    """Reset singleton between tests."""
    EliteClient.reset()
    yield
    EliteClient.reset()


@pytest.fixture
def env_token(monkeypatch):
    """Set ELITE_API_TOKEN env var."""
    monkeypatch.setenv("ELITE_API_TOKEN", "test-token-123")
    monkeypatch.setenv("ELITE_BASE_URL", "http://localhost:8080")


@pytest.fixture
def env_credentials(monkeypatch):
    """Set ELITE_USERNAME + ELITE_PASSWORD env vars."""
    monkeypatch.setenv("ELITE_USERNAME", "admin")
    monkeypatch.setenv("ELITE_PASSWORD", "secret")
    monkeypatch.setenv("ELITE_BASE_URL", "http://localhost:8080")


# ---------------------------------------------------------------------------
# check_elite_available
# ---------------------------------------------------------------------------


class TestCheckEliteAvailable:
    def test_available_with_token(self, monkeypatch):
        monkeypatch.setenv("ELITE_API_TOKEN", "tok")
        assert check_elite_available() is True

    def test_available_with_credentials(self, monkeypatch):
        monkeypatch.setenv("ELITE_USERNAME", "user")
        monkeypatch.setenv("ELITE_PASSWORD", "pass")
        assert check_elite_available() is True

    def test_unavailable_no_config(self, monkeypatch):
        monkeypatch.delenv("ELITE_API_TOKEN", raising=False)
        monkeypatch.delenv("ELITE_USERNAME", raising=False)
        monkeypatch.delenv("ELITE_PASSWORD", raising=False)
        assert check_elite_available() is False

    def test_unavailable_partial_credentials(self, monkeypatch):
        monkeypatch.setenv("ELITE_USERNAME", "user")
        monkeypatch.delenv("ELITE_PASSWORD", raising=False)
        assert check_elite_available() is False


# ---------------------------------------------------------------------------
# EliteClient initialization
# ---------------------------------------------------------------------------


class TestEliteClientInit:
    def test_default_urls(self, monkeypatch):
        monkeypatch.delenv("ELITE_BASE_URL", raising=False)
        monkeypatch.delenv("ELITE_DOC_SERVICE_URL", raising=False)
        monkeypatch.setenv("ELITE_API_TOKEN", "tok")
        client = EliteClient.get()
        assert client.base_url == "http://127.0.0.1:8080"
        assert client.doc_service_url == "http://127.0.0.1:8001"

    def test_custom_urls(self, monkeypatch):
        monkeypatch.setenv("ELITE_BASE_URL", "http://elite.local:9090/")
        monkeypatch.setenv("ELITE_DOC_SERVICE_URL", "http://docs.local:9001/")
        monkeypatch.setenv("ELITE_API_TOKEN", "tok")
        client = EliteClient.get()
        # Trailing slash should be stripped
        assert client.base_url == "http://elite.local:9090"
        assert client.doc_service_url == "http://docs.local:9001"

    def test_singleton(self, env_token):
        c1 = EliteClient.get()
        c2 = EliteClient.get()
        assert c1 is c2


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


class TestTokenManagement:
    def test_static_token_preferred(self, env_token):
        client = EliteClient.get()
        token = client._get_token()
        assert token == "test-token-123"

    def test_login_with_credentials(self, env_credentials):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token": "jwt-from-login",
            "expires_in": 7200,
        }
        mock_response.raise_for_status = MagicMock()

        client = EliteClient.get()
        with patch.object(
            client._client, "post", return_value=mock_response
        ) as mock_post:
            token = client._get_token()
            assert token == "jwt-from-login"
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/v1/auth/login" in call_args[0][0]

    def test_cached_token_reused(self, env_credentials):
        # Simulate a cached token
        EliteClient._token = "cached-jwt"
        EliteClient._token_expires = time.time() + 3600

        client = EliteClient.get()
        with patch.object(client._client, "post") as mock_post:
            token = client._get_token()
            assert token == "cached-jwt"
            mock_post.assert_not_called()

    def test_expired_token_refreshed(self, env_credentials):
        # Simulate an expired token
        EliteClient._token = "old-jwt"
        EliteClient._token_expires = time.time() - 100

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "new-jwt", "expires_in": 3600}
        mock_response.raise_for_status = MagicMock()

        client = EliteClient.get()
        with patch.object(client._client, "post", return_value=mock_response):
            token = client._get_token()
            assert token == "new-jwt"

    def test_login_failure_raises(self, env_credentials):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_response
        )

        client = EliteClient.get()
        with patch.object(client._client, "post", return_value=mock_response):
            with pytest.raises(EliteAuthError, match="login failed"):
                client._get_token()

    def test_no_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("ELITE_API_TOKEN", raising=False)
        monkeypatch.delenv("ELITE_USERNAME", raising=False)
        monkeypatch.delenv("ELITE_PASSWORD", raising=False)
        client = EliteClient.get()
        with pytest.raises(EliteAuthError, match="No Elite credentials"):
            client._get_token()


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------


class TestRequest:
    def test_successful_request(self, env_token):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": [1, 2, 3]}'
        mock_response.json.return_value = {"data": [1, 2, 3]}
        mock_response.raise_for_status = MagicMock()

        client = EliteClient.get()
        with patch.object(
            client._client, "request", return_value=mock_response
        ) as mock_req:
            result = client.request("GET", "/rag/search")
            assert result == {"data": [1, 2, 3]}
            call_args = mock_req.call_args
            assert call_args[0] == ("GET", "http://localhost:8080/api/v1/rag/search")
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"] == "Bearer test-token-123"

    def test_401_retry_with_fresh_token(self, env_token, monkeypatch):
        """On 401, client should clear token cache and retry once."""
        call_count = [0]

        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.status_code = 401
                resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "401", request=MagicMock(), response=resp
                )
            else:
                resp.status_code = 200
                resp.content = b'{"ok": true}'
                resp.json.return_value = {"ok": True}
                resp.raise_for_status = MagicMock()
            return resp

        client = EliteClient.get()
        with patch.object(client._client, "request", side_effect=mock_request):
            result = client.request("GET", "/test")
            assert result == {"ok": True}
            assert call_count[0] == 2

    def test_empty_response_body(self, env_token):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_response.raise_for_status = MagicMock()

        client = EliteClient.get()
        with patch.object(client._client, "request", return_value=mock_response):
            result = client.request("DELETE", "/some/resource")
            assert result == {}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy(self, env_token):
        mock_response = MagicMock()
        mock_response.status_code = 200

        client = EliteClient.get()
        with patch.object(client._client, "get", return_value=mock_response):
            assert client.health_check() is True

    def test_unhealthy(self, env_token):
        client = EliteClient.get()
        with patch.object(
            client._client, "get", side_effect=httpx.ConnectError("refused")
        ):
            assert client.health_check() is False


# ---------------------------------------------------------------------------
# safe_elite_call wrapper
# ---------------------------------------------------------------------------


class TestSafeEliteCall:
    def test_success_passthrough(self):
        def fn():
            return json.dumps({"success": True})

        result = safe_elite_call(fn)
        assert json.loads(result)["success"] is True

    def test_auth_error_caught(self):
        def fn():
            raise EliteAuthError("bad creds")

        result = json.loads(safe_elite_call(fn))
        assert result["success"] is False
        assert "Auth error" in result["error"]

    def test_http_error_caught(self):
        def fn():
            resp = MagicMock()
            resp.status_code = 500
            resp.text = "Internal Server Error"
            raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp)

        result = json.loads(safe_elite_call(fn))
        assert result["success"] is False
        assert "HTTP 500" in result["error"]

    def test_connect_error_caught(self):
        def fn():
            raise httpx.ConnectError("Connection refused")

        result = json.loads(safe_elite_call(fn))
        assert result["success"] is False
        assert "Cannot connect" in result["error"]

    def test_timeout_error_caught(self):
        def fn():
            raise httpx.TimeoutException("timed out")

        result = json.loads(safe_elite_call(fn))
        assert result["success"] is False
        assert "timed out" in result["error"]

    def test_generic_exception_caught(self):
        def fn():
            raise RuntimeError("something broke")

        result = json.loads(safe_elite_call(fn))
        assert result["success"] is False
        assert "something broke" in result["error"]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_elite_requires_env(self):
        env_list = _elite_requires_env()
        assert "ELITE_API_TOKEN" in env_list
