#!/usr/bin/env python3
"""
Elite RAG Tools

Provides knowledge base search, query, and management capabilities
via the Elite backend's RAG module.

Tools:
- elite_rag_search: Search for relevant document chunks
- elite_rag_query: Ask questions against the knowledge base
- elite_kb_list: List available knowledge bases
"""

import json
from tools.registry import registry
from tools.elite_client import (
    EliteClient,
    check_elite_available,
    _elite_requires_env,
    safe_elite_call,
)


# ─── Schemas ───────────────────────────────────────────────────────────────────

ELITE_RAG_SEARCH_SCHEMA = {
    "name": "elite_rag_search",
    "description": (
        "Search the Elite knowledge base for relevant document chunks. "
        "Returns ranked text fragments matching the query. "
        "Optionally specify a knowledge_base_id to search within a specific KB."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query text",
            },
            "knowledge_base_id": {
                "type": "string",
                "description": "Optional: specific knowledge base ID to search within",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 20)",
            },
        },
        "required": ["query"],
    },
}

ELITE_RAG_QUERY_SCHEMA = {
    "name": "elite_rag_query",
    "description": (
        "Ask a question against the Elite knowledge base. "
        "Returns an AI-generated answer grounded in retrieved documents, "
        "along with source references."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to answer using knowledge base context",
            },
            "knowledge_base_id": {
                "type": "string",
                "description": "Optional: specific knowledge base ID to query",
            },
        },
        "required": ["question"],
    },
}

ELITE_KB_LIST_SCHEMA = {
    "name": "elite_kb_list",
    "description": (
        "List all available knowledge bases in Elite. "
        "Returns KB names, IDs, document counts, and descriptions."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ─── Handlers ──────────────────────────────────────────────────────────────────


def _elite_rag_search(
    query: str, knowledge_base_id: str = None, top_k: int = 5, **kwargs
) -> str:
    client = EliteClient.get()
    body = {"query": query, "top_k": min(max(top_k, 1), 20)}

    if knowledge_base_id:
        path = f"/rag/knowledge-bases/{knowledge_base_id}/search"
    else:
        path = "/rag/search"

    result = client.request("POST", path, json=body)
    results = result.get("results", result.get("data", []))
    return json.dumps({"success": True, "results": results, "count": len(results)})


def _elite_rag_query(question: str, knowledge_base_id: str = None, **kwargs) -> str:
    client = EliteClient.get()
    body = {"question": question}

    if knowledge_base_id:
        path = f"/rag/knowledge-bases/{knowledge_base_id}/query"
    else:
        path = "/rag/query"

    result = client.request("POST", path, json=body)
    return json.dumps(
        {
            "success": True,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", result.get("references", [])),
        }
    )


def _elite_kb_list(**kwargs) -> str:
    client = EliteClient.get()
    result = client.request("GET", "/rag/knowledge-bases")
    kbs = result.get("knowledge_bases", result.get("data", result.get("items", [])))
    return json.dumps({"success": True, "knowledge_bases": kbs, "count": len(kbs)})


# ─── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="elite_rag_search",
    toolset="elite",
    schema=ELITE_RAG_SEARCH_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_rag_search,
        query=args.get("query", ""),
        knowledge_base_id=args.get("knowledge_base_id"),
        top_k=args.get("top_k", 5),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="🔎",
    max_result_size_chars=50_000,
)

registry.register(
    name="elite_rag_query",
    toolset="elite",
    schema=ELITE_RAG_QUERY_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_rag_query,
        question=args.get("question", ""),
        knowledge_base_id=args.get("knowledge_base_id"),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="💡",
    max_result_size_chars=50_000,
)

registry.register(
    name="elite_kb_list",
    toolset="elite",
    schema=ELITE_KB_LIST_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(_elite_kb_list),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📚",
    max_result_size_chars=30_000,
)
