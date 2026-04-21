# Hermes-Agent × Elite 整合实施计划

> 版本：2026-04-20 v2  
> 基于 hermes-agent 工具注册模式 + Elite 实际 API 路由整理

---

## 1. 整合目标

让用户在 Hermes CLI / Gateway / ACP 中通过自然语言对话，直接调用 Elite 后端的全部核心能力：

- **知识库检索与问答**（RAG）
- **工作流编排与执行**（Workflow）
- **多维表格数据操作**（Table）
- **Agent 任务管理**（Agents）
- **文档解析入库**（Doc Service）
- **用户与工作空间管理**（Platform）

整合方式与 hermes-agent 现有 `tools/*.py` + `registry` 体系完全一致，不破坏 Prompt Caching。

---

## 2. 推荐方案：分层架构

```
┌─────────────────────────────────────────────────────┐
│  用户 (CLI / Telegram / Slack / ACP / ...)          │
└────────────────────────┬────────────────────────────┘
                         │ 自然语言
                         ▼
┌─────────────────────────────────────────────────────┐
│  Hermes AIAgent (run_agent.py)                      │
│  ┌───────────────────────────────────────────────┐  │
│  │ Elite Toolset (tools/elite_*.py)              │  │
│  │  • elite_rag_search / elite_rag_query         │  │
│  │  • elite_workflow_execute / _status            │  │
│  │  • elite_table_query / _write                 │  │
│  │  • elite_agents_task / _session               │  │
│  │  • elite_doc_extract                          │  │
│  └───────────────────┬───────────────────────────┘  │
│                      │ HTTP (httpx)                  │
└──────────────────────┼──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Elite Backend (:8080)  +  Doc Service (:8001)      │
│  /api/v1/rag/* | /workflow/* | /tables/* | /agents/*│
└─────────────────────────────────────────────────────┘
```

**为什么选 REST 工具集（模式 A）为主**：
- 与现有 web_tools、browser_tool 等模式完全一致，无额外运维
- 工具名和描述完全可控，模型调用准确率高
- 可精细做参数校验、结果脱敏、分页截断
- 单测覆盖简单（mock HTTP）

**MCP 作为可选扩展**（模式 B）：中长期由 Elite 侧提供 MCP Server，Hermes 通过 `config.yaml → mcp_servers.elite` 接入，供多客户端复用。

---

## 3. 文件变更清单

### 3.1 新增文件

| 文件 | 职责 |
|------|------|
| `tools/elite_client.py` | Elite HTTP 客户端封装（认证、Token 缓存、请求/响应处理） |
| `tools/elite_rag_tool.py` | RAG 相关工具：search、query、kb_query、doc_upload |
| `tools/elite_workflow_tool.py` | 工作流工具：list、execute、status、logs、stop |
| `tools/elite_table_tool.py` | 表格工具：list_tables、query_rows、write_rows |
| `tools/elite_agents_tool.py` | Agent 工具：create_task、execute_task、list_sessions |
| `tools/elite_doc_tool.py` | 文档解析工具：extract（调 doc_service :8001） |
| `tests/tools/test_elite_client.py` | 客户端单测 |
| `tests/tools/test_elite_rag.py` | RAG 工具单测 |
| `tests/tools/test_elite_workflow.py` | 工作流工具单测 |
| `tests/tools/test_elite_table.py` | 表格工具单测 |
| `tests/tools/test_elite_agents.py` | Agent 工具单测 |

### 3.2 修改文件

| 文件 | 变更 |
|------|------|
| `toolsets.py` | 新增 `"elite"` toolset 定义 |
| `hermes_cli/config.py` | `OPTIONAL_ENV_VARS` 增加 Elite 相关环境变量；`DEFAULT_CONFIG` 增加 `elite:` 配置段 |

---

## 4. 核心实现设计

### 4.1 Elite HTTP 客户端 (`tools/elite_client.py`)

```python
"""Elite backend HTTP client with JWT caching and auto-refresh."""

import json
import os
import time
from typing import Optional
import httpx

class EliteClient:
    """Singleton-style client for Elite REST API."""

    _instance: Optional["EliteClient"] = None
    _token: Optional[str] = None
    _token_expires: float = 0

    def __init__(self):
        self.base_url = os.getenv("ELITE_BASE_URL", "http://127.0.0.1:8080")
        self.doc_service_url = os.getenv("ELITE_DOC_SERVICE_URL", "http://127.0.0.1:8001")
        self._client = httpx.Client(timeout=30.0)

    @classmethod
    def get(cls) -> "EliteClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_token(self) -> str:
        """Get cached token or authenticate."""
        # 优先使用静态 token
        static_token = os.getenv("ELITE_API_TOKEN")
        if static_token:
            return static_token

        # Token 未过期则复用
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        # 用账密登录
        username = os.getenv("ELITE_USERNAME", "")
        password = os.getenv("ELITE_PASSWORD", "")
        resp = self._client.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    def request(self, method: str, path: str, **kwargs) -> dict:
        """Authenticated request to Elite backend."""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_token()}"
        resp = self._client.request(
            method,
            f"{self.base_url}/api/v1{path}",
            headers=headers,
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def doc_request(self, method: str, path: str, **kwargs) -> dict:
        """Request to doc_service (no auth required typically)."""
        resp = self._client.request(
            method,
            f"{self.doc_service_url}{path}",
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


def check_elite_available() -> bool:
    """Check if Elite env vars are configured."""
    return bool(
        os.getenv("ELITE_API_TOKEN")
        or (os.getenv("ELITE_USERNAME") and os.getenv("ELITE_PASSWORD"))
    )
```

### 4.2 工具注册模式（以 RAG 为例）

```python
"""tools/elite_rag_tool.py — Elite RAG tools."""

import json
from tools.registry import registry
from tools.elite_client import EliteClient, check_elite_available


# ─── Schemas ───────────────────────────────────────────────

ELITE_RAG_SEARCH_SCHEMA = {
    "name": "elite_rag_search",
    "description": "Search the Elite knowledge base for relevant document chunks. Returns ranked text fragments matching the query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query text"
            },
            "knowledge_base_id": {
                "type": "string",
                "description": "Optional: specific knowledge base ID to search within"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 20)"
            }
        },
        "required": ["query"]
    }
}

ELITE_RAG_QUERY_SCHEMA = {
    "name": "elite_rag_query",
    "description": "Ask a question against the Elite knowledge base. Returns an AI-generated answer grounded in retrieved documents.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to answer using knowledge base context"
            },
            "knowledge_base_id": {
                "type": "string",
                "description": "Optional: specific knowledge base ID"
            }
        },
        "required": ["question"]
    }
}


# ─── Handlers ──────────────────────────────────────────────

def elite_rag_search(query: str, knowledge_base_id: str = None, top_k: int = 5, task_id: str = None) -> str:
    client = EliteClient.get()
    body = {"query": query, "top_k": min(top_k, 20)}
    if knowledge_base_id:
        path = f"/rag/knowledge-bases/{knowledge_base_id}/search"
    else:
        path = "/rag/search"
    try:
        result = client.request("POST", path, json=body)
        return json.dumps({"success": True, "results": result.get("results", [])})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def elite_rag_query(question: str, knowledge_base_id: str = None, task_id: str = None) -> str:
    client = EliteClient.get()
    body = {"question": question}
    if knowledge_base_id:
        path = f"/rag/knowledge-bases/{knowledge_base_id}/query"
    else:
        path = "/rag/query"
    try:
        result = client.request("POST", path, json=body)
        return json.dumps({"success": True, "answer": result.get("answer", ""), "sources": result.get("sources", [])})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ─── Registration ──────────────────────────────────────────

registry.register(
    name="elite_rag_search",
    toolset="elite",
    schema=ELITE_RAG_SEARCH_SCHEMA,
    handler=lambda args, **kw: elite_rag_search(
        query=args.get("query", ""),
        knowledge_base_id=args.get("knowledge_base_id"),
        top_k=args.get("top_k", 5),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_elite_available,
    requires_env=["ELITE_API_TOKEN"],
    emoji="🔎",
    max_result_size_chars=50_000,
)

registry.register(
    name="elite_rag_query",
    toolset="elite",
    schema=ELITE_RAG_QUERY_SCHEMA,
    handler=lambda args, **kw: elite_rag_query(
        question=args.get("question", ""),
        knowledge_base_id=args.get("knowledge_base_id"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_elite_available,
    requires_env=["ELITE_API_TOKEN"],
    emoji="💡",
    max_result_size_chars=50_000,
)
```

### 4.3 Toolset 注册 (`toolsets.py` 变更)

```python
# 在 TOOLSETS dict 中新增：
"elite": {
    "description": "Elite enterprise backend tools (RAG, workflow, tables, agents)",
    "tools": [
        "elite_rag_search",
        "elite_rag_query",
        "elite_workflow_list",
        "elite_workflow_execute",
        "elite_workflow_status",
        "elite_table_query",
        "elite_table_write",
        "elite_agents_create_task",
        "elite_agents_task_status",
        "elite_doc_extract",
    ],
    "includes": []
},
```

并将 `"elite_rag_search"` 等加入 `_HERMES_CORE_TOOLS` 列表（或按需仅加入特定平台 toolset）。

### 4.4 配置注册 (`hermes_cli/config.py` 变更)

```python
# OPTIONAL_ENV_VARS 新增：
"ELITE_BASE_URL": {
    "description": "Elite backend base URL (e.g. http://127.0.0.1:8080)",
    "prompt": "Elite backend URL",
    "url": None,
    "password": False,
    "category": "tool",
    "advanced": True,
},
"ELITE_API_TOKEN": {
    "description": "Elite API token (long-lived service token)",
    "prompt": "Elite API token",
    "url": None,
    "password": True,
    "tools": ["elite_rag_search", "elite_rag_query", "elite_workflow_execute",
              "elite_table_query", "elite_agents_create_task"],
    "category": "tool",
},
"ELITE_USERNAME": {
    "description": "Elite username (alternative to API token)",
    "prompt": "Elite username",
    "url": None,
    "password": False,
    "category": "tool",
    "advanced": True,
},
"ELITE_PASSWORD": {
    "description": "Elite password (used with ELITE_USERNAME)",
    "prompt": "Elite password",
    "url": None,
    "password": True,
    "category": "tool",
    "advanced": True,
},
"ELITE_DOC_SERVICE_URL": {
    "description": "Elite doc_service URL for PDF/PPTX parsing (default: http://127.0.0.1:8001)",
    "prompt": "Elite doc service URL",
    "url": None,
    "password": False,
    "category": "tool",
    "advanced": True,
},

# DEFAULT_CONFIG 新增：
"elite": {
    "base_url": "",          # 优先级低于 ELITE_BASE_URL 环境变量
    "doc_service_url": "",   # 优先级低于 ELITE_DOC_SERVICE_URL
},
```

---

## 5. 完整工具清单与 Elite API 映射

### 5.1 RAG 模块 (`tools/elite_rag_tool.py`)

| 工具名 | HTTP 方法 | Elite 路径 | 用途 |
|--------|-----------|-----------|------|
| `elite_rag_search` | POST | `/rag/search` 或 `/rag/knowledge-bases/:id/search` | 检索文档片段 |
| `elite_rag_query` | POST | `/rag/query` 或 `/rag/knowledge-bases/:id/query` | 基于知识库问答 |
| `elite_kb_list` | GET | `/rag/knowledge-bases` | 列出知识库 |
| `elite_kb_create` | POST | `/rag/knowledge-bases` | 创建知识库 |
| `elite_doc_upload` | POST | `/rag/knowledge-bases/:id/documents/upload` | 上传文档到知识库 |

### 5.2 工作流模块 (`tools/elite_workflow_tool.py`)

| 工具名 | HTTP 方法 | Elite 路径 | 用途 |
|--------|-----------|-----------|------|
| `elite_workflow_list` | GET | `/workflows/` | 列出工作流 |
| `elite_workflow_execute` | POST | `/workflows/:id/execute` | 执行工作流 |
| `elite_workflow_status` | GET | `/workflows/executions/:id/status` | 查询执行状态 |
| `elite_workflow_logs` | GET | `/workflows/executions/:id/logs` | 获取执行日志 |
| `elite_workflow_stop` | POST | `/workflows/executions/:id/stop` | 停止执行 |

### 5.3 表格模块 (`tools/elite_table_tool.py`)

| 工具名 | HTTP 方法 | Elite 路径 | 用途 |
|--------|-----------|-----------|------|
| `elite_table_list` | GET | `/tables/` | 列出表格 |
| `elite_table_query` | GET | `/tables/:id/rows` | 查询行数据（支持过滤/分页） |
| `elite_table_write` | POST | `/tables/:id/rows` | 写入行（需审批） |

### 5.4 Agent 模块 (`tools/elite_agents_tool.py`)

| 工具名 | HTTP 方法 | Elite 路径 | 用途 |
|--------|-----------|-----------|------|
| `elite_agents_list` | GET | `/agents/` | 列出 Agent |
| `elite_agents_create_task` | POST | `/agents/tasks` | 创建任务 |
| `elite_agents_execute_task` | POST | `/agents/tasks/:id/execute` | 执行任务 |
| `elite_agents_task_status` | GET | `/agents/tasks/:id` | 查询任务状态 |
| `elite_agents_sessions` | GET | `/agents/sessions` | 列出会话 |

### 5.5 文档解析 (`tools/elite_doc_tool.py`)

| 工具名 | HTTP 方法 | 目标服务 | 用途 |
|--------|-----------|---------|------|
| `elite_doc_extract` | POST | doc_service `:8001` | 解析 PDF/PPTX 为文本块 |

---

## 6. 安全与审批策略

### 6.1 认证优先级

```
ELITE_API_TOKEN (静态长期 token)
    ↓ 未设置时
ELITE_USERNAME + ELITE_PASSWORD → 自动登录获取 JWT → 内存缓存
```

### 6.2 Token 安全

- Token 仅存于进程内存，不写入轨迹/日志
- 工具返回结果中脱敏处理（不回显 token 值）
- 建议 Elite 侧为 Hermes 创建专用服务账号，权限最小化

### 6.3 危险操作审批

以下操作复用 hermes-agent 的 `approval` 机制（`tools/approval.py`）：

| 操作 | 审批级别 |
|------|---------|
| `elite_workflow_execute` | 首次执行需确认 |
| `elite_workflow_stop` | 需确认 |
| `elite_table_write` | 始终需确认 |
| `elite_kb_create` | 首次需确认 |
| `elite_doc_upload` | 需确认 |
| `elite_agents_execute_task` | 需确认 |

只读操作（search、query、list、status）无需审批。

---

## 7. 错误处理与韧性

```python
# 统一错误处理模式
def _safe_call(fn, *args, **kwargs) -> str:
    try:
        return fn(*args, **kwargs)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Token 过期，清除缓存重试一次
            EliteClient._token = None
            return fn(*args, **kwargs)
        return json.dumps({"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"})
    except httpx.ConnectError:
        return json.dumps({"success": False, "error": "Cannot connect to Elite backend. Check ELITE_BASE_URL."})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)[:300]})
```

关键策略：
- **401 自动重试**：Token 过期时清除缓存，重新认证后重试一次
- **连接失败友好提示**：明确告知用户检查 URL 配置
- **结果截断**：`max_result_size_chars=50_000` 防止上下文爆炸
- **分页参数**：表格/列表类工具支持 `page`/`page_size` 参数

---

## 8. 测试策略

### 8.1 单元测试（mock HTTP）

```python
# tests/tools/test_elite_rag.py
import pytest
from unittest.mock import patch, MagicMock
from tools.elite_rag_tool import elite_rag_search

@pytest.fixture
def mock_elite_client():
    with patch("tools.elite_rag_tool.EliteClient") as mock:
        client = MagicMock()
        mock.get.return_value = client
        yield client

def test_rag_search_success(mock_elite_client):
    mock_elite_client.request.return_value = {
        "results": [{"text": "chunk1", "score": 0.95}]
    }
    result = elite_rag_search(query="test query")
    assert '"success": true' in result
    mock_elite_client.request.assert_called_once_with(
        "POST", "/rag/search", json={"query": "test query", "top_k": 5}
    )

def test_rag_search_with_kb_id(mock_elite_client):
    mock_elite_client.request.return_value = {"results": []}
    elite_rag_search(query="test", knowledge_base_id="kb-123")
    mock_elite_client.request.assert_called_once_with(
        "POST", "/rag/knowledge-bases/kb-123/search",
        json={"query": "test", "top_k": 5}
    )
```

### 8.2 集成测试（需 Elite 运行）

```python
# tests/tools/test_elite_integration.py
import pytest
import os

pytestmark = pytest.mark.skipif(
    not os.getenv("ELITE_INTEGRATION_TEST"),
    reason="Set ELITE_INTEGRATION_TEST=1 to run"
)

def test_health_check():
    from tools.elite_client import EliteClient
    client = EliteClient.get()
    assert client.health_check() is True

def test_rag_search_e2e():
    from tools.elite_rag_tool import elite_rag_search
    result = elite_rag_search(query="test")
    assert '"success": true' in result
```

### 8.3 运行命令

```bash
# 单元测试（无需 Elite）
python -m pytest tests/tools/test_elite_*.py -q

# 集成测试（需 Elite 运行）
ELITE_INTEGRATION_TEST=1 ELITE_BASE_URL=http://127.0.0.1:8080 \
    python -m pytest tests/tools/test_elite_integration.py -v
```

---

## 9. 分阶段实施计划

### Phase 0：基础设施（1-2 天）

- [ ] 实现 `tools/elite_client.py`（HTTP 客户端 + 认证）
- [ ] 修改 `hermes_cli/config.py`（环境变量注册）
- [ ] 修改 `toolsets.py`（注册 elite toolset）
- [ ] 健康检查验证连通性
- [ ] 单元测试骨架

### Phase 1：只读能力（2-3 天）

- [ ] `tools/elite_rag_tool.py` — search + query
- [ ] `tools/elite_workflow_tool.py` — list + status + logs
- [ ] `tools/elite_table_tool.py` — list + query
- [ ] `tools/elite_agents_tool.py` — list + task_status
- [ ] 端到端验证：CLI 中对话完成「查知识库 → 看工作流状态」

### Phase 2：写操作 + 审批（2-3 天）

- [ ] `elite_workflow_execute` + `elite_workflow_stop`（带审批）
- [ ] `elite_table_write`（带审批）
- [ ] `elite_kb_create` + `elite_doc_upload`
- [ ] `elite_agents_create_task` + `elite_agents_execute_task`
- [ ] `tools/elite_doc_tool.py`（doc_service 解析）
- [ ] 审批流程集成测试

### Phase 3：Skill 固化 + 优化（1-2 天）

- [ ] 编写 Hermes Skill：「知识库问答流程」「工作流执行流程」
- [ ] 结果分页与摘要优化
- [ ] 错误重试与降级策略完善
- [ ] 完整测试套件通过

### Phase 4（可选）：MCP Server

- [ ] Elite 侧实现 MCP stdio/HTTP server
- [ ] Hermes `config.yaml` 增加 `mcp_servers.elite` 配置
- [ ] 验证 MCP 路径与 REST 工具集共存

---

## 10. 验收标准

| 场景 | 预期行为 |
|------|---------|
| 用户问「帮我搜索知识库中关于 XX 的内容」 | 模型调用 `elite_rag_search`，返回相关片段 |
| 用户问「执行工作流 wf-123」 | 模型调用 `elite_workflow_execute`，触发审批确认后执行 |
| 用户问「查看表格 tbl-456 的数据」 | 模型调用 `elite_table_query`，返回分页行数据 |
| 未配置 `ELITE_*` 环境变量 | elite 工具集不出现在可用工具中，无报错 |
| Elite 后端不可达 | 工具返回友好错误信息，不中断对话 |
| Token 过期 | 自动刷新，用户无感知 |

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Elite API 变更导致工具失效 | 契约测试 + 版本标注；工具描述注明已验证版本 |
| Token 泄露 | 环境变量存储、轨迹脱敏、短生命周期 |
| 返回数据过大撑爆上下文 | `max_result_size_chars` 截断 + 分页参数 |
| 与 Elite 内置 Agent 职责重叠 | 明确分工：Hermes = 对话编排，Elite = 业务权威 |
| 网络延迟影响对话体验 | httpx 超时 30s + 异步工具标记 |

---

## 12. 目录结构预览（实施后）

```
tools/
├── elite_client.py          # HTTP 客户端 + JWT 缓存
├── elite_rag_tool.py        # RAG: search, query, kb_list, kb_create, doc_upload
├── elite_workflow_tool.py   # Workflow: list, execute, status, logs, stop
├── elite_table_tool.py      # Table: list, query, write
├── elite_agents_tool.py     # Agents: list, create_task, execute_task, status, sessions
├── elite_doc_tool.py        # Doc: extract (doc_service)
└── ...

tests/tools/
├── test_elite_client.py
├── test_elite_rag.py
├── test_elite_workflow.py
├── test_elite_table.py
├── test_elite_agents.py
└── test_elite_integration.py  # 需 Elite 运行
```

---

*本文档为可执行实施计划，覆盖代码骨架、配置变更、测试策略和分阶段里程碑。实施时按 Phase 顺序推进即可。*
