# 项目集合

本仓库包含 4 个独立项目，各自放在独立子目录中。

## 目录结构

```text
.
├── pet-hospital/       # 宠物医院 · Go REST API（Windows 发行版）
├── pet-hospital-mcp/   # 宠物医院 MCP 服务
├── anythingllm-mcp/    # AnythingLLM MCP 服务
└── agent/              # 大模型对话脚本练习
```

## 1. pet-hospital

用 Go 标准库编写的本地宠物医院管理系统，无第三方依赖、无鉴权，浏览器打开即用的网页界面已内嵌进可执行文件，数据存在单个 `data/pet.db` 文件里。

- 可执行文件：`pet-hospital/pethospital.exe`（64 位 Windows），双击后访问 <http://127.0.0.1:8080/>
- Windows 运行说明见 [pet-hospital/README-Windows.md](pet-hospital/README-Windows.md)
- 完整接口与开发文档见 [pet-hospital/README.md](pet-hospital/README.md)

`upload.html` 是把文档上传到 AnythingLLM 的辅助页面，首次使用需在文件里填入自己的 API Key。

## 2. pet-hospital-mcp

通过 MCP 协议把宠物医院 REST API 暴露给大模型，使用 Streamable HTTP 传输。

```bash
cd pet-hospital-mcp
pip install -e ".[dev,serve]"
PET_HOSPITAL_BASE_URL=http://127.0.0.1:8080 pet-hospital-mcp
```

依赖运行中的 pet-hospital 服务（默认 `127.0.0.1:8080`）。

## 3. anythingllm-mcp

通过 MCP 协议把任意一个 AnythingLLM 工作区暴露给大模型。

```bash
cd anythingllm-mcp
pip install -e .
ANYTHINGLLM_API_KEY=<你的 key> anythingllm-mcp
```

配置全部走环境变量：`ANYTHINGLLM_BASE_URL`、`ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_WORKSPACE_SLUG`、`MCP_HOST`、`MCP_PORT`、`MCP_PATH`。

## 4. agent

大模型对话脚本练习。`agent/Practice01/chat.py` 是一个命令行多轮对话程序，配置放在同目录 `config.ini`（`[llm]` 段：`base_url` / `api_key` / `model`）。

`config.ini` 含密钥，已被 `.gitignore` 忽略，不会提交 —— 新环境需自行创建。

## 许可证

MIT，见 [pet-hospital/LICENSE](pet-hospital/LICENSE)。
