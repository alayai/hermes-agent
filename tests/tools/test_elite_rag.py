"""Tests for the Elite RAG tools module.

Tests search, query, and knowledge base listing with mocked HTTP responses.
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
    """Patch EliteClient.get() to return a mock."""
    mock = MagicMock()
    with patch("tools.elite_rag_tool.EliteClient") as cls_mock:
        cls_mock.get.return_value = mock
        yield mock


# ---------------------------------------------------------------------------
# elite_rag_search
# ---------------------------------------------------------------------------


class TestEliteRagSearch:
    def test_search_basic(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_search

        mock_client.request.return_value = {
            "results": [
                {"text": "chunk 1", "score": 0.95, "source": "doc1.pdf"},
                {"text": "chunk 2", "score": 0.87, "source": "doc2.pdf"},
            ]
        }

        result = json.loads(_elite_rag_search(query="machine learning"))
        assert result["success"] is True
        assert result["count"] == 2
        assert result["results"][0]["text"] == "chunk 1"
        mock_client.request.assert_called_once_with(
            "POST", "/rag/search", json={"query": "machine learning", "top_k": 5}
        )

    def test_search_with_kb_id(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_search

        mock_client.request.return_value = {"results": []}

        _elite_rag_search(query="test", knowledge_base_id="kb-abc")
        mock_client.request.assert_called_once_with(
            "POST",
            "/rag/knowledge-bases/kb-abc/search",
            json={"query": "test", "top_k": 5},
        )

    def test_search_top_k_clamped(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_search

        mock_client.request.return_value = {"results": []}

        _elite_rag_search(query="test", top_k=100)
        call_json = mock_client.request.call_args[1]["json"]
        assert call_json["top_k"] == 20  # clamped to max

    def test_search_top_k_minimum(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_search

        mock_client.request.return_value = {"results": []}

        _elite_rag_search(query="test", top_k=0)
        call_json = mock_client.request.call_args[1]["json"]
        assert call_json["top_k"] == 1  # clamped to min


# ---------------------------------------------------------------------------
# elite_rag_query
# ---------------------------------------------------------------------------


class TestEliteRagQuery:
    def test_query_basic(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_query

        mock_client.request.return_value = {
            "answer": "Machine learning is a subset of AI.",
            "sources": [{"doc": "intro.pdf", "page": 3}],
        }

        result = json.loads(_elite_rag_query(question="What is ML?"))
        assert result["success"] is True
        assert "Machine learning" in result["answer"]
        assert len(result["sources"]) == 1

    def test_query_with_kb_id(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_query

        mock_client.request.return_value = {"answer": "yes", "sources": []}

        _elite_rag_query(question="test?", knowledge_base_id="kb-xyz")
        mock_client.request.assert_called_once_with(
            "POST", "/rag/knowledge-bases/kb-xyz/query", json={"question": "test?"}
        )

    def test_query_fallback_references_key(self, mock_client):
        from tools.elite_rag_tool import _elite_rag_query

        mock_client.request.return_value = {
            "answer": "answer",
            "references": [{"ref": "a"}],
        }

        result = json.loads(_elite_rag_query(question="q"))
        assert result["sources"] == [{"ref": "a"}]


# ---------------------------------------------------------------------------
# elite_kb_list
# ---------------------------------------------------------------------------


class TestEliteKbList:
    def test_list_basic(self, mock_client):
        from tools.elite_rag_tool import _elite_kb_list

        mock_client.request.return_value = {
            "knowledge_bases": [
                {"id": "kb-1", "name": "Docs", "doc_count": 42},
                {"id": "kb-2", "name": "FAQ", "doc_count": 10},
            ]
        }

        result = json.loads(_elite_kb_list())
        assert result["success"] is True
        assert result["count"] == 2
        assert result["knowledge_bases"][0]["name"] == "Docs"

    def test_list_fallback_data_key(self, mock_client):
        from tools.elite_rag_tool import _elite_kb_list

        mock_client.request.return_value = {"data": [{"id": "kb-1", "name": "Test"}]}

        result = json.loads(_elite_kb_list())
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_tools_registered(self):
        from tools.registry import registry

        # Import to trigger registration
        import tools.elite_rag_tool  # noqa: F401

        assert registry.get_entry("elite_rag_search") is not None
        assert registry.get_entry("elite_rag_query") is not None
        assert registry.get_entry("elite_kb_list") is not None
