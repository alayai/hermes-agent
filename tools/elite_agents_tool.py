#!/usr/bin/env python3
"""
Elite Agents Tools

Provides agent listing, task creation, execution, and status monitoring
via the Elite backend's agents module.

Tools:
- elite_agents_list: List available agents
- elite_agents_create_task: Create a new task
- elite_agents_execute_task: Execute a task (requires approval)
- elite_agents_task_status: Check task status
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

ELITE_AGENTS_LIST_SCHEMA = {
    "name": "elite_agents_list",
    "description": (
        "List all available agents in Elite. "
        "Returns agent names, IDs, descriptions, and activation status."
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

ELITE_AGENTS_CREATE_TASK_SCHEMA = {
    "name": "elite_agents_create_task",
    "description": (
        "Create a new task for an Elite agent. "
        "The task will be queued for execution. "
        "Returns the task ID for status tracking."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent ID to assign the task to",
            },
            "title": {
                "type": "string",
                "description": "Task title/name",
            },
            "description": {
                "type": "string",
                "description": "Detailed task description or instructions",
            },
            "inputs": {
                "type": "object",
                "description": "Optional input parameters for the task",
            },
        },
        "required": ["agent_id", "title"],
    },
}

ELITE_AGENTS_EXECUTE_TASK_SCHEMA = {
    "name": "elite_agents_execute_task",
    "description": (
        "Execute a previously created task immediately. "
        "WARNING: This triggers real task execution on the Elite agent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to execute",
            },
        },
        "required": ["task_id"],
    },
}

ELITE_AGENTS_TASK_STATUS_SCHEMA = {
    "name": "elite_agents_task_status",
    "description": (
        "Get the current status of an Elite agent task. "
        "Returns task state (pending, running, completed, failed), progress, and results."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to check status for",
            },
        },
        "required": ["task_id"],
    },
}


# ─── Handlers ──────────────────────────────────────────────────────────────────


def _elite_agents_list(page: int = 1, page_size: int = 20, **kwargs) -> str:
    client = EliteClient.get()
    params = {"page": page, "page_size": min(page_size, 50)}
    result = client.request("GET", "/agents/", params=params)
    agents = result.get("agents", result.get("data", result.get("items", [])))
    return json.dumps(
        {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "page": page,
        }
    )


def _elite_agents_create_task(
    agent_id: str,
    title: str,
    description: str = "",
    inputs: dict = None,
    **kwargs,
) -> str:
    client = EliteClient.get()
    body = {
        "agent_id": agent_id,
        "title": title,
    }
    if description:
        body["description"] = description
    if inputs:
        body["inputs"] = inputs

    result = client.request("POST", "/agents/tasks", json=body)
    return json.dumps(
        {
            "success": True,
            "task_id": result.get("task_id", result.get("id", "")),
            "status": result.get("status", "created"),
            "message": f"Task '{title}' created for agent {agent_id}.",
        }
    )


def _elite_agents_execute_task(task_id: str, **kwargs) -> str:
    client = EliteClient.get()
    result = client.request("POST", f"/agents/tasks/{task_id}/execute")
    return json.dumps(
        {
            "success": True,
            "task_id": task_id,
            "status": result.get("status", "executing"),
            "message": f"Task {task_id} execution started.",
        }
    )


def _elite_agents_task_status(task_id: str, **kwargs) -> str:
    client = EliteClient.get()
    result = client.request("GET", f"/agents/tasks/{task_id}")
    return json.dumps(
        {
            "success": True,
            "task_id": task_id,
            "status": result.get("status", "unknown"),
            "progress": result.get("progress"),
            "result": result.get("result"),
            "error": result.get("error"),
            "created_at": result.get("created_at"),
            "completed_at": result.get("completed_at"),
        }
    )


# ─── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="elite_agents_list",
    toolset="elite",
    schema=ELITE_AGENTS_LIST_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_agents_list,
        page=args.get("page", 1),
        page_size=args.get("page_size", 20),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="🤖",
    max_result_size_chars=30_000,
)

registry.register(
    name="elite_agents_create_task",
    toolset="elite",
    schema=ELITE_AGENTS_CREATE_TASK_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_agents_create_task,
        agent_id=args.get("agent_id", ""),
        title=args.get("title", ""),
        description=args.get("description", ""),
        inputs=args.get("inputs"),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📝",
    max_result_size_chars=10_000,
)

registry.register(
    name="elite_agents_execute_task",
    toolset="elite",
    schema=ELITE_AGENTS_EXECUTE_TASK_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_agents_execute_task,
        task_id=args.get("task_id", ""),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="▶️",
    max_result_size_chars=10_000,
)

registry.register(
    name="elite_agents_task_status",
    toolset="elite",
    schema=ELITE_AGENTS_TASK_STATUS_SCHEMA,
    handler=lambda args, **kw: safe_elite_call(
        _elite_agents_task_status,
        task_id=args.get("task_id", ""),
    ),
    check_fn=check_elite_available,
    requires_env=_elite_requires_env(),
    emoji="📊",
    max_result_size_chars=10_000,
)
