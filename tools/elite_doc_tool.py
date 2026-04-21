#!/usr/bin/env python3
"""
Elite Document Service Tool

Provides document parsing and extraction via Elite's doc_service.
Supports PDF and PPTX files — extracts text content as structured chunks.

Tools:
- elite_doc_extract: Parse a document file into text chunks
"""

import json
from tools.registry import registry
from tools.elite_client import (
    EliteClient,
    check_elite_available,
    _elite_requires_env,
    safe_elite_call,
)


# ─── Schema ────────────────────────────────────────────────────────────────────

ELITE_DOC_EXTRACT_SCHEMA = {
    "name": "elite_doc_extract",
    "description": (
        "Extract text content from a document (PDF or PPTX) using Elite's doc_service. "
        "Provide a URL to the document or a file path accessible to the Elite backend. "
        "Returns structured text chunks suitable for indexing or analysis."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL or file path of the document to parse",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'chunks' (structured chunks) or 'text' (plain text). Default: 'chunks'",
                "enum": ["chunks", "text"],
            },
        },
        "required": ["url"],
    },
}


# ─── Handler ───────────────────────────────────────────────────────────────────


def _elite_doc_extract(url: str, format: str = "chunks", **kwargs) -> str:
    client = EliteClient.get()
    body = {"url": url, "format": format}
    result = client.doc_request("POST", "/parse", json=body)

    if format == "text":
        text = result.get("text", result.get("content", ""))
        return json.dumps(
            {
                "success": True,
                "text": text,
                "char_count": len(text),
            }
        )
    else:
        chunks = result.get("chunks", result.get("data", []))
        return json.dumps(
            {
                "success": True,
                "chunks": chunks,
                "count": len(chunks),
            }
        )


# ─── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="elite_doc_extract",
    toolset="elite",
    schema=ELITE_DOC_EXTRACT_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_doc_extract,
        url=args.get("url", ""),
        format=args.get("format", "chunks"),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📄",
    max_result_size_chars=80_000,
)
