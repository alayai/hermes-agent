"""Tests for the Elite Agents tools module.

Tests agent listing, task creation, execution, and status with mocked HTTP.
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
    with patch("tools.elite_agents_tool.EliteClient") as cls_mock:
        cls_mock.get.return_value = mock
        yield mock


# ---------------------------------------------------------------------------
# elite_agents_list
# ---------------------------------------------------------------------------


class TestEliteAgentsList:
    def test_list_basic(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_list

        mock_client.request.return_value = {
            "agents": [
                {"id": "agent-1", "name": "Research Bot", "status": "active"},
                {"id": "agent-2", "name": "Data Analyst", "status": "inactive"},
            ]
        }

        result = json.loads(_elite_agents_list())
        assert result["success"] is True
        assert result["count"] == 2
        assert result["agents"][0]["name"] == "Research Bot"

    def test_list_pagination(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_list

        mock_client.request.return_value = {"agents": []}

        _elite_agents_list(page=2, page_size=5)
        mock_client.request.assert_called_once_with(
            "GET", "/agents/", params={"page": 2, "page_size": 5}
        )


# ---------------------------------------------------------------------------
# elite_agents_create_task
# ---------------------------------------------------------------------------


class TestEliteAgentsCreateTask:
    def test_create_basic(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_create_task

        mock_client.request.return_value = {
            "task_id": "task-abc",
            "status": "created",
        }

        result = json.loads(
            _elite_agents_create_task(
                agent_id="agent-1",
                title="Analyze Q1 data",
            )
        )
        assert result["success"] is True
        assert result["task_id"] == "task-abc"
        assert "Analyze Q1 data" in result["message"]

    def test_create_with_description_and_inputs(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_create_task

        mock_client.request.return_value = {"task_id": "task-xyz", "status": "created"}

        _elite_agents_create_task(
            agent_id="agent-1",
            title="Process files",
            description="Process all CSV files in /data",
            inputs={"directory": "/data", "format": "csv"},
        )

        call_json = mock_client.request.call_args[1]["json"]
        assert call_json["agent_id"] == "agent-1"
        assert call_json["title"] == "Process files"
        assert call_json["description"] == "Process all CSV files in /data"
        assert call_json["inputs"] == {"directory": "/data", "format": "csv"}

    def test_create_minimal(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_create_task

        mock_client.request.return_value = {"id": "task-min", "status": "created"}

        _elite_agents_create_task(agent_id="agent-1", title="Quick task")
        call_json = mock_client.request.call_args[1]["json"]
        assert "description" not in call_json
        assert "inputs" not in call_json


# ---------------------------------------------------------------------------
# elite_agents_execute_task
# ---------------------------------------------------------------------------


class TestEliteAgentsExecuteTask:
    def test_execute_basic(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_execute_task

        mock_client.request.return_value = {"status": "executing"}

        result = json.loads(_elite_agents_execute_task(task_id="task-abc"))
        assert result["success"] is True
        assert result["status"] == "executing"
        mock_client.request.assert_called_once_with(
            "POST", "/agents/tasks/task-abc/execute"
        )


# ---------------------------------------------------------------------------
# elite_agents_task_status
# ---------------------------------------------------------------------------


class TestEliteAgentsTaskStatus:
    def test_status_running(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_task_status

        mock_client.request.return_value = {
            "status": "running",
            "progress": 0.6,
            "created_at": "2026-04-20T10:00:00Z",
        }

        result = json.loads(_elite_agents_task_status(task_id="task-abc"))
        assert result["success"] is True
        assert result["status"] == "running"
        assert result["progress"] == 0.6

    def test_status_completed_with_result(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_task_status

        mock_client.request.return_value = {
            "status": "completed",
            "result": {"summary": "Analysis complete", "rows_processed": 1500},
            "completed_at": "2026-04-20T10:10:00Z",
        }

        result = json.loads(_elite_agents_task_status(task_id="task-abc"))
        assert result["status"] == "completed"
        assert result["result"]["rows_processed"] == 1500

    def test_status_failed(self, mock_client):
        from tools.elite_agents_tool import _elite_agents_task_status

        mock_client.request.return_value = {
            "status": "failed",
            "error": "Connection timeout to data source",
        }

        result = json.loads(_elite_agents_task_status(task_id="task-abc"))
        assert result["status"] == "failed"
        assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_tools_registered(self):
        from tools.registry import registry

        import tools.elite_agents_tool  # noqa: F401

        assert registry.get_entry("elite_agents_list") is not None
        assert registry.get_entry("elite_agents_create_task") is not None
        assert registry.get_entry("elite_agents_execute_task") is not None
        assert registry.get_entry("elite_agents_task_status") is not None
