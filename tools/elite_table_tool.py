#!/usr/bin/env python3
"""
Elite Table Tools

Provides multi-dimensional table listing, querying, and writing
via the Elite backend's table module.

Tools:
- elite_table_list: List available tables
- elite_table_query: Query rows from a table (with filtering/pagination)
- elite_table_write: Write rows to a table (requires approval)
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

ELITE_TABLE_LIST_SCHEMA = {
    "name": "elite_table_list",
    "description": (
        "List all available tables in Elite. "
        "Returns table names, IDs, column schemas, and row counts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "Page number (default: 1)",
            },
            "page_size": {
                "type": "integer",
                "description": "Results per page (default: 20, max: 50)",
            },
        },
        "required": [],
    },
}

ELITE_TABLE_QUERY_SCHEMA = {
    "name": "elite_table_query",
    "description": (
        "Query rows from an Elite table. Supports filtering, sorting, and pagination. "
        "Returns row data matching the specified criteria."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "table_id": {
                "type": "string",
                "description": "The table ID to query",
            },
            "filters": {
                "type": "object",
                "description": "Optional filter conditions (field-value pairs)",
            },
            "sort_by": {
                "type": "string",
                "description": "Optional: field name to sort by",
            },
            "sort_order": {
                "type": "string",
                "description": "Sort order: 'asc' or 'desc' (default: 'asc')",
                "enum": ["asc", "desc"],
            },
            "page": {
                "type": "integer",
                "description": "Page number (default: 1)",
            },
            "page_size": {
                "type": "integer",
                "description": "Rows per page (default: 20, max: 100)",
            },
        },
        "required": ["table_id"],
    },
}

ELITE_TABLE_WRITE_SCHEMA = {
    "name": "elite_table_write",
    "description": (
        "Write (insert or update) rows to an Elite table. "
        "WARNING: This modifies table data. Provide rows as a list of objects "
        "where each object maps column names to values."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "table_id": {
                "type": "string",
                "description": "The table ID to write to",
            },
            "rows": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of row objects to insert/update (each maps column names to values)",
            },
            "mode": {
                "type": "string",
                "description": "Write mode: 'insert' (add new rows) or 'upsert' (update existing or insert). Default: 'insert'",
                "enum": ["insert", "upsert"],
            },
        },
        "required": ["table_id", "rows"],
    },
}


# ─── Handlers ──────────────────────────────────────────────────────────────────


def _elite_table_list(page: int = 1, page_size: int = 20, **kwargs) -> str:
    client = EliteClient.get()
    params = {"page": page, "page_size": min(page_size, 50)}
    result = client.request("GET", "/tables/", params=params)
    tables = result.get("tables", result.get("data", result.get("items", [])))
    return json.dumps(
        {
            "success": True,
            "tables": tables,
            "count": len(tables),
            "page": page,
        }
    )


def _elite_table_query(
    table_id: str,
    filters: dict = None,
    sort_by: str = None,
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 20,
    **kwargs,
) -> str:
    client = EliteClient.get()
    params = {"page": page, "page_size": min(page_size, 100)}
    if sort_by:
        params["sort_by"] = sort_by
        params["sort_order"] = sort_order
    if filters:
        params["filters"] = json.dumps(filters)

    result = client.request("GET", f"/tables/{table_id}/rows", params=params)
    rows = result.get("rows", result.get("data", result.get("items", [])))
    return json.dumps(
        {
            "success": True,
            "table_id": table_id,
            "rows": rows,
            "count": len(rows),
            "page": page,
            "total": result.get("total", len(rows)),
        }
    )


def _elite_table_write(
    table_id: str, rows: list, mode: str = "insert", **kwargs
) -> str:
    client = EliteClient.get()
    body = {"rows": rows, "mode": mode}
    result = client.request("POST", f"/tables/{table_id}/rows", json=body)
    return json.dumps(
        {
            "success": True,
            "table_id": table_id,
            "affected_rows": result.get(
                "affected_rows", result.get("count", len(rows))
            ),
            "mode": mode,
            "message": f"Successfully wrote {len(rows)} row(s) to table {table_id}.",
        }
    )


# ─── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="elite_table_list",
    toolset="elite",
    schema=ELITE_TABLE_LIST_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_table_list,
        page=args.get("page", 1),
        page_size=args.get("page_size", 20),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📊",
    max_result_size_chars=30_000,
)

registry.register(
    name="elite_table_query",
    toolset="elite",
    schema=ELITE_TABLE_QUERY_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_table_query,
        table_id=args.get("table_id", ""),
        filters=args.get("filters"),
        sort_by=args.get("sort_by"),
        sort_order=args.get("sort_order", "asc"),
        page=args.get("page", 1),
        page_size=args.get("page_size", 20),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="🔍",
    max_result_size_chars=50_000,
)

registry.register(
    name="elite_table_write",
    toolset="elite",
    schema=ELITE_TABLE_WRITE_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_table_write,
        table_id=args.get("table_id", ""),
        rows=args.get("rows", []),
        mode=args.get("mode", "insert"),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="✏️",
    max_result_size_chars=10_000,
)
