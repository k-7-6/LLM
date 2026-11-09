# anythingllm-mcp

把本地 [AnythingLLM](https://anythingllm.com/) 的知识库能力以 **MCP（Model Context Protocol）** 工具的形式暴露给任意支持 Streamable HTTP 的 MCP 客户端。

## 提供的工具

| 工具 | 作用 | 主要参数 |
| --- | --- | --- |
| `ask_workspace` | 向工作区知识库提问，返回基于已索引文档生成的回答 | `message`、`mode`（`query` / `chat` / `automatic`） |
| `list_workspaces` | 列出所有工作区及其 slug | 无 |
| `create_workspace` | 新建工作区 | `name` |
| `upload_document` | 上传本机文件并加入工作区知识库（自动向量化） | `file_path`、`workspace_slug`（可选） |

典型流程：`list_workspaces` 找到目标工作区 → `upload_document` 上传资料 → `ask_workspace` 基于资料提问。也可以先用 `create_workspace` 建一个新工作区。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001/api` | AnythingLLM 开发者 API 根地址（注意包含 `/api`） |
| `ANYTHINGLLM_API_KEY` | 无 | **必填**。AnythingLLM → Settings → API Keys 生成 |
| `ANYTHINGLLM_WORKSPACE_SLUG` | 内置默认值 | `ask_workspace` 与 `upload_document` 的默认工作区 |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址 |
| `MCP_PORT` | `8000` | MCP 监听端口 |
| `MCP_PATH` | `/mcp` | MCP 路径 |
| `MCP_REQUEST_TIMEOUT` | `60.0` | 单次后端请求超时（秒），连接超时固定为 10 秒 |

未设置 `ANYTHINGLLM_API_KEY` 时，服务会在启动阶段直接报错退出（退出码 2），不会等到第一次工具调用才收到远端 401。

## 安装与启动

需要 Python 3.11+。

```bash
cd anythingllm-mcp
python -m venv .venv
.venv/Scripts/activate        # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"

export ANYTHINGLLM_API_KEY="your-api-key"   # Windows PowerShell: $env:ANYTHINGLLM_API_KEY="..."
python -m anythingllm_mcp
```

启动后日志会打印 `MCP endpoint: http://127.0.0.1:8000/mcp`。

## MCP 客户端配置

ZAgent 读取项目根目录的 `.mcp.json`：

```json
{
  "mcpServers": {
    "anythingllm": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Claude Code / 其他客户端使用同等的 HTTP MCP 配置即可。

## 调用示例

在接入 MCP 的对话中可以直接用自然语言驱动：

```text
列出 AnythingLLM 里的所有工作区。
```

```text
把 D:\资料\育儿指南.pdf 上传到工作区 parenting，然后总结其中的睡眠建议。
```

```text
在 parenting 工作区中查询：不同月龄的辅食添加顺序是什么？只依据工作区文档回答。
```

等价的工具参数：

```json
{"name": "upload_document", "arguments": {"file_path": "D:\\资料\\育儿指南.pdf", "workspace_slug": "parenting"}}
```

```json
{"name": "ask_workspace", "arguments": {"message": "不同月龄的辅食添加顺序是什么？", "mode": "query"}}
```

`file_path` 必须是**运行本 MCP 服务的机器**上可访问的路径。支持的格式取决于 AnythingLLM 后端配置，常见为 `pdf`、`docx`、`txt`、`md`、`csv`。

## 错误处理

所有工具失败时返回 `is_error = true` 的 MCP 结果，正文是可读的错误原因，不会让 MCP 连接崩溃。客户端覆盖以下情况：

- 缺少或错误的 API Key（HTTP 401/403）
- AnythingLLM 未启动或地址错误
- 请求超时
- 返回非 JSON 或字段结构异常
- 上传文件不存在或不可读

## 测试

```bash
cd anythingllm-mcp
pip install -e ".[dev]"
pytest
```

测试使用 `httpx.MockTransport`，不需要真实的 AnythingLLM 实例。
