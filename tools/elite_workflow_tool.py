#!/usr/bin/env python3
"""
Elite Workflow Tools

Provides workflow listing, execution, status monitoring, and control
via the Elite backend's workflow module.

Tools:
- elite_workflow_list: List available workflows
- elite_workflow_execute: Execute a workflow (requires approval)
- elite_workflow_status: Check execution status
- elite_workflow_logs: Get execution logs
- elite_workflow_stop: Stop a running execution (requires approval)
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

ELITE_WORKFLOW_LIST_SCHEMA = {
    "name": "elite_workflow_list",
    "description": (
        "List all available workflows in Elite. "
        "Returns workflow names, IDs, descriptions, and status."
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

ELITE_WORKFLOW_EXECUTE_SCHEMA = {
    "name": "elite_workflow_execute",
    "description": (
        "Execute a workflow by ID. This triggers the workflow to run with optional input parameters. "
        "Returns an execution ID that can be used to track status. "
        "WARNING: This is a write operation that triggers real workflow execution."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID to execute",
            },
            "inputs": {
                "type": "object",
                "description": "Optional input parameters for the workflow execution",
            },
        },
        "required": ["workflow_id"],
    },
}

ELITE_WORKFLOW_STATUS_SCHEMA = {
    "name": "elite_workflow_status",
    "description": (
        "Get the current status of a workflow execution. "
        "Returns execution state (running, completed, failed, stopped), progress, and timing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "The execution ID to check status for",
            },
        },
        "required": ["execution_id"],
    },
}

ELITE_WORKFLOW_LOGS_SCHEMA = {
    "name": "elite_workflow_logs",
    "description": (
        "Get logs from a workflow execution. "
        "Returns step-by-step execution logs for debugging and monitoring."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "The execution ID to get logs for",
            },
        },
        "required": ["execution_id"],
    },
}

ELITE_WORKFLOW_STOP_SCHEMA = {
    "name": "elite_workflow_stop",
    "description": (
        "Stop a running workflow execution. "
        "WARNING: This will terminate the execution immediately."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "The execution ID to stop",
            },
        },
        "required": ["execution_id"],
    },
}


# ─── Handlers ──────────────────────────────────────────────────────────────────


def _elite_workflow_list(page: int = 1, page_size: int = 20, **kwargs) -> str:
    client = EliteClient.get()
    params = {"page": page, "page_size": min(page_size, 50)}
    result = client.request("GET", "/workflows/", params=params)
    workflows = result.get("workflows", result.get("data", result.get("items", [])))
    return json.dumps(
        {
            "success": True,
            "workflows": workflows,
            "count": len(workflows),
            "page": page,
        }
    )


def _elite_workflow_execute(workflow_id: str, inputs: dict = None, **kwargs) -> str:
    client = EliteClient.get()
    body = {}
    if inputs:
        body["inputs"] = inputs
    result = client.request("POST", f"/workflows/{workflow_id}/execute", json=body)
    return json.dumps(
        {
            "success": True,
            "execution_id": result.get("execution_id", result.get("id", "")),
            "status": result.get("status", "started"),
            "message": f"Workflow {workflow_id} execution started.",
        }
    )


def _elite_workflow_status(execution_id: str, **kwargs) -> str:
    client = EliteClient.get()
    result = client.request("GET", f"/workflows/executions/{execution_id}/status")
    return json.dumps(
        {
            "success": True,
            "execution_id": execution_id,
            "status": result.get("status", "unknown"),
            "progress": result.get("progress"),
            "started_at": result.get("started_at"),
            "completed_at": result.get("completed_at"),
            "error": result.get("error"),
        }
    )


def _elite_workflow_logs(execution_id: str, **kwargs) -> str:
    client = EliteClient.get()
    result = client.request("GET", f"/workflows/executions/{execution_id}/logs")
    logs = result.get("logs", result.get("data", []))
    return json.dumps(
        {
            "success": True,
            "execution_id": execution_id,
            "logs": logs,
            "count": len(logs),
        }
    )


def _elite_workflow_stop(execution_id: str, **kwargs) -> str:
    client = EliteClient.get()
    result = client.request("POST", f"/workflows/executions/{execution_id}/stop")
    return json.dumps(
        {
            "success": True,
            "execution_id": execution_id,
            "status": result.get("status", "stopped"),
            "message": f"Execution {execution_id} stop requested.",
        }
    )


# ─── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="elite_workflow_list",
    toolset="elite",
    schema=ELITE_WORKFLOW_LIST_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_workflow_list,
        page=args.get("page", 1),
        page_size=args.get("page_size", 20),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="⚙️",
    max_result_size_chars=30_000,
)

registry.register(
    name="elite_workflow_execute",
    toolset="elite",
    schema=ELITE_WORKFLOW_EXECUTE_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_workflow_execute,
        workflow_id=args.get("workflow_id", ""),
        inputs=args.get("inputs"),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="▶️",
    max_result_size_chars=10_000,
)

registry.register(
    name="elite_workflow_status",
    toolset="elite",
    schema=ELITE_WORKFLOW_STATUS_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_workflow_status,
        execution_id=args.get("execution_id", ""),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📊",
    max_result_size_chars=10_000,
)

registry.register(
    name="elite_workflow_logs",
    toolset="elite",
    schema=ELITE_WORKFLOW_LOGS_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_workflow_logs,
        execution_id=args.get("execution_id", ""),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📋",
    max_result_size_chars=50_000,
)

registry.register(
    name="elite_workflow_stop",
    toolset="elite",
    schema=ELITE_WORKFLOW_STOP_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_workflow_stop,
        execution_id=args.get("execution_id", ""),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="⏹️",
    max_result_size_chars=5_000,
)
