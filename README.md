# 项目集合

本仓库包含 5 个项目/目录，各自独立：

```text
.
├── pet-hospital/        # 宠物医院 REST API（仓库内仅文档，发行包见 Releases）
├── pet-hospital-mcp/    # 宠物医院 MCP 服务
├── anythingllm-mcp/     # AnythingLLM MCP 服务
├── agent/
│   ├── ZAgent/          # 终端 AI Agent（Textual TUI）
│   └── Practice01-02/   # 入门对话脚本
└── office/              # 办公技能与工具素材
```

## 1. pet-hospital

用 Go 标准库编写的本地宠物医院管理系统：网页界面已内嵌进可执行文件，数据存在单个 `data/pet.db` 文件中，无鉴权、无第三方依赖。

- 发行包（`pethospital.exe` + 演示数据库）请从 [GitHub Releases](https://github.com/k-7-6/LLM/releases) 下载；**Go 源码不在本仓库**
- 运行说明见 [pet-hospital/README-Windows.md](pet-hospital/README-Windows.md)
- 接口与数据模型见 [pet-hospital/README.md](pet-hospital/README.md)
- `upload.html` 是把文档上传到 AnythingLLM 的辅助页面，使用前需在页面中填入自己的 API Key

## 2. pet-hospital-mcp

通过 MCP 协议把宠物医院 REST API 暴露给大模型，使用 Streamable HTTP 传输。目前提供 `list_pets` 工具（过滤、排序、分页、结构化错误码）。

```bash
cd pet-hospital-mcp
pip install -e ".[dev,serve]"
PET_HOSPITAL_BASE_URL=http://127.0.0.1:8080 MCP_PORT=8001 pet-hospital-mcp
```

依赖运行中的 pet-hospital 服务（默认 `127.0.0.1:8080`）。工具参数、错误码与 `.mcp.json` 示例见 [pet-hospital-mcp/README.md](pet-hospital-mcp/README.md)。

## 3. anythingllm-mcp

通过 MCP 协议访问 AnythingLLM：工作区问答、工作区列表/创建、文档上传并向量化。

```bash
cd anythingllm-mcp
pip install -e ".[dev]"
ANYTHINGLLM_API_KEY=<你的 key> python -m anythingllm_mcp
```

配置全部走环境变量：`ANYTHINGLLM_BASE_URL`、`ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_WORKSPACE_SLUG`、`MCP_HOST`、`MCP_PORT`、`MCP_PATH`。缺少 API Key 时服务会在启动阶段直接报错。工具说明与调用示例见 [anythingllm-mcp/README.md](anythingllm-mcp/README.md)。

## 4. agent/ZAgent

运行在终端里的通用 AI Agent：Textual 聊天界面、流式输出、工具调用循环、技能按需加载、MCP 接入、会话持久化与上下文压缩。

```bash
cd agent/ZAgent
pip install -r requirements.txt
python main.py
```

首次运行自动生成 `config.ini`，填写 `[llm] api_key` 后重启即可。完整配置字段、内置工具、斜杠命令与安全说明见 [agent/ZAgent/README.md](agent/ZAgent/README.md)。

`agent/Practice01`、`agent/Practice02` 是更早的入门对话脚本，配置同样放在各自的 `config.ini`。

## 5. office

办公场景的技能与工具素材：

- `.agents/skills/`：示例技能包（PPT 生成、每日星座、通知、加密、浏览器操作）
- `AgentBrowser_#SULP#_630wxw/`、`OfficeCli_#SULP#_26sc1d/`：第三方浏览器 / Office 命令行工具及其说明
- `DeepSeek-Balance-Whale-Widget-main/`：DeepSeek 余额鲸鱼挂件（第三方项目）
- `通知预览.png`：通知技能效果预览

## 配置与密钥

- 各项目的 `config.ini` 已被 `.gitignore` 忽略，不会提交；新环境需按各项目 README 自行创建
- MCP 的 `.mcp.json` 同样不提交
- 若曾把密钥写入示例文件，请先轮换密钥再推送

## 许可证

MIT，见 [pet-hospital/LICENSE](pet-hospital/LICENSE)。第三方目录保留各自许可证。
