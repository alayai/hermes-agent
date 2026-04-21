#!/usr/bin/env python3
"""
Elite Backend HTTP Client

Provides authenticated HTTP access to the Elite enterprise backend.
Handles JWT token caching, auto-refresh, and connection management.

Configuration via environment variables:
- ELITE_BASE_URL: Backend URL (default: http://127.0.0.1:8080)
- ELITE_API_TOKEN: Static long-lived token (preferred)
- ELITE_USERNAME + ELITE_PASSWORD: Credential-based auth (fallback)
- ELITE_DOC_SERVICE_URL: Doc service URL (default: http://127.0.0.1:8001)
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Default timeout for Elite API calls (seconds)
_DEFAULT_TIMEOUT = 30.0


class EliteAuthError(Exception):
    """Raised when authentication with Elite fails."""

    pass


class EliteClient:
    """HTTP client for Elite backend with JWT caching."""

    _instance: Optional["EliteClient"] = None
    _token: Optional[str] = None
    _token_expires: float = 0

    def __init__(self):
        self.base_url = (os.getenv("ELITE_BASE_URL") or "http://127.0.0.1:8080").rstrip(
            "/"
        )
        self.doc_service_url = (
            os.getenv("ELITE_DOC_SERVICE_URL") or "http://127.0.0.1:8001"
        ).rstrip("/")
        self._client = httpx.Client(timeout=_DEFAULT_TIMEOUT)

    @classmethod
    def get(cls) -> "EliteClient":
        """Get or create the singleton client instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        if cls._instance and cls._instance._client:
            try:
                cls._instance._client.close()
            except Exception:
                pass
        cls._instance = None
        cls._token = None
        cls._token_expires = 0

    def _get_token(self) -> str:
        """Get a valid auth token, refreshing if needed."""
        # Priority 1: static token from env
        static_token = os.getenv("ELITE_API_TOKEN")
        if static_token:
            return static_token

        # Priority 2: cached token still valid (with 60s buffer)
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        # Priority 3: login with credentials
        username = os.getenv("ELITE_USERNAME", "")
        password = os.getenv("ELITE_PASSWORD", "")
        if not username or not password:
            raise EliteAuthError(
                "No Elite credentials configured. Set ELITE_API_TOKEN or "
                "ELITE_USERNAME + ELITE_PASSWORD in your .env file."
            )

        try:
            resp = self._client.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise EliteAuthError(
                f"Elite login failed (HTTP {e.response.status_code}): "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.ConnectError as e:
            raise EliteAuthError(
                f"Cannot connect to Elite at {self.base_url}. "
                "Check ELITE_BASE_URL configuration."
            ) from e

        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise EliteAuthError(
                "Elite login response missing token field. "
                f"Response keys: {list(data.keys())}"
            )

        EliteClient._token = token
        EliteClient._token_expires = time.time() + data.get("expires_in", 3600)
        return token

    def request(
        self,
        method: str,
        path: str,
        *,
        retry_auth: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to Elite backend.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g. "/rag/search") — will be prefixed with /api/v1
            retry_auth: If True, retry once on 401 with fresh token
            **kwargs: Passed to httpx (json, params, data, files, etc.)

        Returns:
            Parsed JSON response as dict

        Raises:
            httpx.HTTPStatusError: On non-2xx responses (after auth retry)
            EliteAuthError: On authentication failures
        """
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_token()}"

        url = f"{self.base_url}/api/v1{path}"

        try:
            resp = self._client.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and retry_auth:
                # Token expired — clear cache and retry once
                EliteClient._token = None
                EliteClient._token_expires = 0
                headers["Authorization"] = f"Bearer {self._get_token()}"
                resp = self._client.request(method, url, headers=headers, **kwargs)
                resp.raise_for_status()
            else:
                raise

        if not resp.content:
            return {}
        return resp.json()

    def doc_request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request to the doc_service (typically no auth required).

        Args:
            method: HTTP method
            path: Full path on doc_service (e.g. "/parse")
            **kwargs: Passed to httpx
        """
        resp = self._client.request(
            method,
            f"{self.doc_service_url}{path}",
            **kwargs,
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()

    def health_check(self) -> bool:
        """Check if Elite backend is reachable."""
        try:
            resp = self._client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


def check_elite_available() -> bool:
    """Check if Elite credentials are configured (for tool registry check_fn)."""
    return bool(
        os.getenv("ELITE_API_TOKEN")
        or (os.getenv("ELITE_USERNAME") and os.getenv("ELITE_PASSWORD"))
    )


def _elite_requires_env() -> list:
    """Return the env var list for registry display."""
    return ["ELITE_API_TOKEN"]


def safe_elite_call(fn, *args, **kwargs) -> str:
    """
    Wrap an Elite tool handler with standard error handling.
    Returns JSON string with success/error fields.
    """
    try:
        return fn(*args, **kwargs)
    except EliteAuthError as e:
        return json.dumps({"success": False, "error": f"Auth error: {e}"})
    except httpx.HTTPStatusError as e:
        return json.dumps(
            {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}",
            }
        )
    except httpx.ConnectError:
        return json.dumps(
            {
                "success": False,
                "error": "Cannot connect to Elite backend. Check ELITE_BASE_URL.",
            }
        )
    except httpx.TimeoutException:
        return json.dumps(
            {
                "success": False,
                "error": "Request to Elite timed out. The server may be overloaded.",
            }
        )
    except Exception as e:
        logger.exception("Unexpected error in Elite tool call")
        return json.dumps({"success": False, "error": str(e)[:300]})
