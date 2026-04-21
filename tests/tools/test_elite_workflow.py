"""Tests for the Elite Workflow tools module.

Tests workflow listing, execution, status, logs, and stop with mocked HTTP.
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
    with patch("tools.elite_workflow_tool.EliteClient") as cls_mock:
        cls_mock.get.return_value = mock
        yield mock


# ---------------------------------------------------------------------------
# elite_workflow_list
# ---------------------------------------------------------------------------


class TestEliteWorkflowList:
    def test_list_basic(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_list

        mock_client.request.return_value = {
            "workflows": [
                {"id": "wf-1", "name": "Data Pipeline", "status": "active"},
                {"id": "wf-2", "name": "Report Gen", "status": "active"},
            ]
        }

        result = json.loads(_elite_workflow_list())
        assert result["success"] is True
        assert result["count"] == 2
        assert result["workflows"][0]["name"] == "Data Pipeline"

    def test_list_pagination(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_list

        mock_client.request.return_value = {"workflows": []}

        _elite_workflow_list(page=2, page_size=10)
        mock_client.request.assert_called_once_with(
            "GET", "/workflows/", params={"page": 2, "page_size": 10}
        )

    def test_list_page_size_clamped(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_list

        mock_client.request.return_value = {"workflows": []}

        _elite_workflow_list(page_size=100)
        call_params = mock_client.request.call_args[1]["params"]
        assert call_params["page_size"] == 50


# ---------------------------------------------------------------------------
# elite_workflow_execute
# ---------------------------------------------------------------------------


class TestEliteWorkflowExecute:
    def test_execute_basic(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_execute

        mock_client.request.return_value = {
            "execution_id": "exec-123",
            "status": "running",
        }

        result = json.loads(_elite_workflow_execute(workflow_id="wf-1"))
        assert result["success"] is True
        assert result["execution_id"] == "exec-123"
        mock_client.request.assert_called_once_with(
            "POST", "/workflows/wf-1/execute", json={}
        )

    def test_execute_with_inputs(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_execute

        mock_client.request.return_value = {
            "execution_id": "exec-456",
            "status": "started",
        }

        _elite_workflow_execute(workflow_id="wf-2", inputs={"param1": "value1"})
        call_json = mock_client.request.call_args[1]["json"]
        assert call_json["inputs"] == {"param1": "value1"}


# ---------------------------------------------------------------------------
# elite_workflow_status
# ---------------------------------------------------------------------------


class TestEliteWorkflowStatus:
    def test_status_running(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_status

        mock_client.request.return_value = {
            "status": "running",
            "progress": 0.45,
            "started_at": "2026-04-20T10:00:00Z",
        }

        result = json.loads(_elite_workflow_status(execution_id="exec-123"))
        assert result["success"] is True
        assert result["status"] == "running"
        assert result["progress"] == 0.45

    def test_status_completed(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_status

        mock_client.request.return_value = {
            "status": "completed",
            "started_at": "2026-04-20T10:00:00Z",
            "completed_at": "2026-04-20T10:05:00Z",
        }

        result = json.loads(_elite_workflow_status(execution_id="exec-123"))
        assert result["status"] == "completed"
        assert result["completed_at"] is not None


# ---------------------------------------------------------------------------
# elite_workflow_logs
# ---------------------------------------------------------------------------


class TestEliteWorkflowLogs:
    def test_logs_basic(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_logs

        mock_client.request.return_value = {
            "logs": [
                {"step": 1, "message": "Starting", "timestamp": "2026-04-20T10:00:00Z"},
                {
                    "step": 2,
                    "message": "Processing",
                    "timestamp": "2026-04-20T10:01:00Z",
                },
            ]
        }

        result = json.loads(_elite_workflow_logs(execution_id="exec-123"))
        assert result["success"] is True
        assert result["count"] == 2
        assert result["logs"][0]["message"] == "Starting"


# ---------------------------------------------------------------------------
# elite_workflow_stop
# ---------------------------------------------------------------------------


class TestEliteWorkflowStop:
    def test_stop_basic(self, mock_client):
        from tools.elite_workflow_tool import _elite_workflow_stop

        mock_client.request.return_value = {"status": "stopped"}

        result = json.loads(_elite_workflow_stop(execution_id="exec-123"))
        assert result["success"] is True
        assert result["status"] == "stopped"
        mock_client.request.assert_called_once_with(
            "POST", "/workflows/executions/exec-123/stop"
        )


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_tools_registered(self):
        from tools.registry import registry

        import tools.elite_workflow_tool  # noqa: F401

        assert registry.get_entry("elite_workflow_list") is not None
        assert registry.get_entry("elite_workflow_execute") is not None
        assert registry.get_entry("elite_workflow_status") is not None
        assert registry.get_entry("elite_workflow_logs") is not None
        assert registry.get_entry("elite_workflow_stop") is not None
