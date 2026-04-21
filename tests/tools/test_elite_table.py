"""Tests for the Elite Table tools module.

Tests table listing, querying, and writing with mocked HTTP responses.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tools.elite_client import EliteClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_client():
    EliteClient.reset()
    yield
    EliteClient.reset()


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("ELITE_API_TOKEN", "test-token")
    monkeypatch.setenv("ELITE_BASE_URL", "http://localhost:8080")


@pytest.fixture
def mock_client():
    mock = MagicMock()
    with patch("tools.elite_table_tool.EliteClient") as cls_mock:
        cls_mock.get.return_value = mock
        yield mock


# ---------------------------------------------------------------------------
# elite_table_list
# ---------------------------------------------------------------------------


class TestEliteTableList:
    def test_list_basic(self, mock_client):
        from tools.elite_table_tool import _elite_table_list

        mock_client.request.return_value = {
            "tables": [
                {"id": "tbl-1", "name": "Users", "row_count": 150},
                {"id": "tbl-2", "name": "Orders", "row_count": 5000},
            ]
        }

        result = json.loads(_elite_table_list())
        assert result["success"] is True
        assert result["count"] == 2
        assert result["tables"][0]["name"] == "Users"

    def test_list_pagination(self, mock_client):
        from tools.elite_table_tool import _elite_table_list

        mock_client.request.return_value = {"tables": []}

        _elite_table_list(page=3, page_size=10)
        mock_client.request.assert_called_once_with(
            "GET", "/tables/", params={"page": 3, "page_size": 10}
        )


# ---------------------------------------------------------------------------
# elite_table_query
# ---------------------------------------------------------------------------


class TestEliteTableQuery:
    def test_query_basic(self, mock_client):
        from tools.elite_table_tool import _elite_table_query

        mock_client.request.return_value = {
            "rows": [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
            ],
            "total": 150,
        }

        result = json.loads(_elite_table_query(table_id="tbl-1"))
        assert result["success"] is True
        assert result["count"] == 2
        assert result["total"] == 150
        assert result["rows"][0]["name"] == "Alice"

    def test_query_with_filters(self, mock_client):
        from tools.elite_table_tool import _elite_table_query

        mock_client.request.return_value = {"rows": [], "total": 0}

        _elite_table_query(table_id="tbl-1", filters={"status": "active"})
        call_params = mock_client.request.call_args[1]["params"]
        assert "filters" in call_params
        assert json.loads(call_params["filters"]) == {"status": "active"}

    def test_query_with_sorting(self, mock_client):
        from tools.elite_table_tool import _elite_table_query

        mock_client.request.return_value = {"rows": [], "total": 0}

        _elite_table_query(table_id="tbl-1", sort_by="name", sort_order="desc")
        call_params = mock_client.request.call_args[1]["params"]
        assert call_params["sort_by"] == "name"
        assert call_params["sort_order"] == "desc"

    def test_query_page_size_clamped(self, mock_client):
        from tools.elite_table_tool import _elite_table_query

        mock_client.request.return_value = {"rows": [], "total": 0}

        _elite_table_query(table_id="tbl-1", page_size=200)
        call_params = mock_client.request.call_args[1]["params"]
        assert call_params["page_size"] == 100


# ---------------------------------------------------------------------------
# elite_table_write
# ---------------------------------------------------------------------------


class TestEliteTableWrite:
    def test_write_insert(self, mock_client):
        from tools.elite_table_tool import _elite_table_write

        mock_client.request.return_value = {"affected_rows": 2}

        rows = [
            {"name": "Charlie", "email": "charlie@example.com"},
            {"name": "Diana", "email": "diana@example.com"},
        ]
        result = json.loads(_elite_table_write(table_id="tbl-1", rows=rows))
        assert result["success"] is True
        assert result["affected_rows"] == 2
        assert result["mode"] == "insert"

        mock_client.request.assert_called_once_with(
            "POST", "/tables/tbl-1/rows", json={"rows": rows, "mode": "insert"}
        )

    def test_write_upsert(self, mock_client):
        from tools.elite_table_tool import _elite_table_write

        mock_client.request.return_value = {"affected_rows": 1}

        rows = [{"id": 1, "name": "Alice Updated"}]
        result = json.loads(
            _elite_table_write(table_id="tbl-1", rows=rows, mode="upsert")
        )
        assert result["mode"] == "upsert"

        call_json = mock_client.request.call_args[1]["json"]
        assert call_json["mode"] == "upsert"


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_tools_registered(self):
        from tools.registry import registry

        import tools.elite_table_tool  # noqa: F401

        assert registry.get_entry("elite_table_list") is not None
        assert registry.get_entry("elite_table_query") is not None
        assert registry.get_entry("elite_table_write") is not None
