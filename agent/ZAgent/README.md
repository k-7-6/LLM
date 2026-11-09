# ZAgent

一个运行在终端里的通用 AI Agent：Textual 聊天界面、流式输出、工具调用循环、技能（Skills）按需加载、MCP 工具接入、会话持久化与上下文压缩。

## 功能

- **终端聊天界面**：DeepSeek 风格深色主题，支持多行输入、斜杠命令补全、工具调用过程展示
- **流式工具循环**：解析 OpenAI 兼容接口的 `tool_calls`，执行工具并把结果回填给模型，支持多轮
- **安全边界**：单轮最大步数 / 总超时、文件工具路径白名单、危险写操作默认关闭
- **技能系统**：启动时只扫描 `SKILL.md` 的 Frontmatter，按需用 `loadSkill` 加载全文（渐进式披露）
- **MCP 客户端**：读取项目根目录 `.mcp.json`，把外部 MCP Server 的工具合并进工具列表
- **会话与上下文**：JSONL 事件日志、历史会话恢复、超长上下文自动摘要与归档
- **项目约定**：启动时把 `AGENTS.md` 注入为固定的 system 消息

## 环境要求

- Python 3.11+
- 可访问的 OpenAI 兼容大模型接口（默认 DeepSeek）
- 可选：百度千帆搜索 API Key、AnythingLLM / pet-hospital 等 MCP 服务

## 安装与启动

```bash
cd agent/ZAgent
python -m venv .venv
.venv/Scripts/activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

首次运行会在**当前目录**生成 `config.ini`（若不可写则生成在 `agent/ZAgent/` 下），并在界面顶部提示填写密钥。修改 `[llm]` 中的 `api_key` 后重新启动即可。

```bash
python main.py --config path/to/config.ini   # 指定配置文件
python main.py --project path/to/workspace   # 指定项目根目录
```

配置查找顺序：`--config` → `ZAGENT_CONFIG` → 当前目录 `config.ini` → 程序目录 `config.ini`。

项目根目录优先级：`--project` → `ZAGENT_PROJECT_ROOT` → `[project] root` → 当前目录。启动后进程会 `chdir` 到项目根目录，因此技能、`.mcp.json`、`AGENTS.md` 和文件工具都以它为基准。

## 配置字段

`config.ini` 的所有字段都有内置默认值，可只保留需要修改的部分。

| 段 | 字段 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `[llm]` | `base_url` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| | `api_key` | 空 | 模型 API Key，**必填** |
| | `model` | `deepseek-v4-flash` | 模型名称 |
| | `request_timeout` | `120` | 单次请求超时（秒） |
| | `max_retries` | `2` | 请求失败重试次数 |
| `[project]` | `root` | 空 | 项目根目录；相对路径以配置文件所在目录为基准 |
| `[agent]` | `max_steps` | `30` | 单轮任务最多模型调用次数，`0` 表示不限制 |
| | `loop_timeout` | `600` | 单轮任务总超时（秒），`0` 表示不限制 |
| `[context]` | `window` | `0` | 上下文窗口；`0` 表示使用 `default_window` |
| | `default_window` | `128000` | 默认上下文窗口（token） |
| | `warn_ratio` | `0.7` | 超过该比例时提示压缩 |
| | `summary_target_tokens` | `5000` | 摘要目标长度 |
| | `summary_max_tokens` | `6000` | 摘要最大长度 |
| | `archive_dir` | `.agents/context` | 压缩后原文归档目录 |
| `[sessions]` | `dir` | `.agents/sessions` | 会话 JSONL 目录 |
| | `title_length` | `40` | 会话标题截断长度 |
| | `agents_file` | `AGENTS.md` | 项目约定文件名 |
| `[skills]` | `dir` | `.agents/skills` | 技能目录 |
| | `file` | `SKILL.md` | 技能入口文件名 |
| | `max_description_length` | `200` | 注入 System Prompt 的描述长度上限 |
| | `max_load_chars` | `20000` | `loadSkill` 单次返回字符上限，超出截断 |
| `[mcp]` | `config_file` | `.mcp.json` | MCP Server 配置文件 |
| | `connect_timeout` | `20` | 连接超时（秒） |
| | `call_timeout` | `60` | 工具调用超时（秒） |
| | `max_tool_name_length` | `64` | 工具名长度上限 |
| `[files]` | `max_read_chars` | `200000` | `read_file` 单次返回字符上限 |
| | `root` | 空 | 文件工具允许访问的根目录；空表示项目根目录 |
| | `allow_dangerous_ops` | `false` | 是否允许覆盖写入、删除、覆盖重命名 |
| `[search]` | `url` / `baidu_qianfan_api_key` / `baidu_qianfan_model` | 千帆默认值 | 联网搜索配置 |
| | `top_k` / `timeout` / `snippet_chars` | `5` / `30` / `120` | 搜索结果数量、超时、摘要长度 |
| `[fetch]` | `max_chars` / `max_time` / `connect_timeout` / `process_timeout` | `20000` / `20` / `10` / `30` | 网页抓取限制 |
| `[cli]` | `timeout` / `max_output_chars` / `head_chars` / `tail_chars` | `30` / `8000` / `6000` / `2000` | 命令执行与输出截断 |
| `[recall]` | `max_results` / `max_output_chars` / `snippet_radius` | `20` / `6000` / `180` | 历史上下文检索 |

## 内置工具

| 类别 | 工具 |
| --- | --- |
| 系统 | `getdate`、`isleapyear`、`get_cwd` |
| 文件 | `list_dir`、`get_file_type`、`read_file`、`create_file`、`edit_file`、`create_dir`、`delete_dir`、`delete_file`、`rename` |
| 网络 | `searchWeb`、`fetchWeb` |
| 命令 | `RunCli` |
| 技能 | `loadSkill`、`createSkill` |
| 上下文 | `recallContext` |

### 文件工具的安全行为

- 所有路径都会规范化并检查是否位于 `[files] root`（默认项目根目录）内，越界直接报错
- `edit_file`（覆盖写入）、`delete_file`、`delete_dir`、覆盖式 `rename` 默认禁用；确需使用时在配置中设置：

```ini
[files]
allow_dangerous_ops = true
```

- `read_file` 与 `loadSkill` 都有字符上限，避免一次把超大内容塞进上下文

## 技能（Skills）

在 `<项目根>/.agents/skills/<name>/SKILL.md` 放一个带 YAML Frontmatter 的 Markdown：

```markdown
---
name: weather-report
description: 查询并总结指定城市的天气
---

# 使用步骤
1. 调用 searchWeb 查询天气……
```

启动时只把 `name` 与 `description` 注入 System Prompt；模型需要时再调用 `loadSkill` 读取全文。也可以让模型用 `createSkill` 在对话中新建技能，重启后生效。

## MCP 接入

项目根目录的 `.mcp.json` 使用流式 HTTP：

```json
{
  "mcpServers": {
    "anythingllm": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8000/mcp"
    },
    "pet-hospital": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

MCP 工具会在界面侧栏异步加载，`/mcp` 可查看连接状态与工具列表。仓库中的 [`anythingllm-mcp`](../../anythingllm-mcp/README.md) 与 [`pet-hospital-mcp`](../../pet-hospital-mcp/README.md) 可直接作为服务端。

## 斜杠命令

| 命令 | 作用 |
| --- | --- |
| `/new` | 新建会话并保存当前会话 |
| `/resume` | 打开历史会话列表并恢复 |
| `/save` | 保存当前会话 |
| `/compact` | 压缩上下文并归档原文 |
| `/status` | 查看会话、上下文和 MCP 状态 |
| `/mcp` | 查看 MCP 服务器与可用工具 |
| `/help` | 显示全部斜杠命令 |
| `/quit` | 保存会话并退出 |

## 会话与上下文

- 每条消息立即追加到 `<项目根>/.agents/sessions/<id>.jsonl`
- `/resume` 从 JSONL 回放消息；`AGENTS.md` 作为固定 system 消息随会话保存
- 上下文超过 `warn_ratio` 后可用 `/compact` 生成摘要，原文归档到 `.agents/context`
- `AGENTS.md` 在会话首次加载时注入一次，后续轮次复用

## 测试

```bash
cd agent/ZAgent
pip install -r requirements-dev.txt
pytest
```

测试覆盖配置解析、文件工具路径边界与危险操作开关、技能创建/加载/截断、日期与闰年工具，全部使用临时目录，不需要真实 API Key。

## 安全说明

- `config.ini` 含 API Key，已被 `.gitignore` 忽略，不会提交
- `files.allow_dangerous_ops` 默认关闭；开启后模型可覆盖或删除 `files.root` 内的文件
- `RunCli` 会执行本机命令，请只在可信项目中使用
- 会话与上下文归档可能包含隐私内容，保存在 `.agents/` 下，同样被 `.gitignore` 忽略
