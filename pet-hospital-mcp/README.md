# pet-hospital-mcp

把 [pet-hospital](../pet-hospital/) 的宠物档案 REST API 包装成 **MCP 工具**，通过 Streamable HTTP 提供给大模型。服务本身无状态，所有数据仍由 pet-hospital 后端的 `data/pet.db` 持有。

## 提供的工具

### `list_pets`

查询宠物档案列表，支持过滤、排序和分页。输入字段与后端 `GET /api/v1/pets` 对齐：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `q` | string | 全文检索（跨字段） |
| `name` | string | 宠物名 |
| `ownerName` / `ownerPhone` | string | 主人姓名 / 电话 |
| `species` | enum | `犬` `猫` `兔` `鸟` `仓鼠` `爬宠` `其他` |
| `doctor` | string | 主治医生 |
| `disease` | string | 疾病 / 诊断 |
| `status` | enum | `待就诊` `就诊中` `住院中` `已康复` `慢性病随访` |
| `min` / `max` | number | 总花费区间，`min <= max` |
| `sortBy` | enum | `id` `name` `ownerName` `species` `doctor` `disease` `status` `totalCost` `visitCount` `createdAt` `updatedAt` |
| `order` | enum | `asc` / `desc` |
| `page` | int | 页码，从 1 开始 |
| `pageSize` | int | 每页条数，1–500，默认 20 |

返回 `items`（含病历 `records`、消费明细 `charges`、汇总 `totalCost` / `visitCount`）、`total`、`page`、`pageSize`、`totalPages`、`totalCost`。

调用示例：

```json
{
  "name": "list_pets",
  "arguments": {
    "species": "犬",
    "status": "住院中",
    "sortBy": "totalCost",
    "order": "desc",
    "page": 1,
    "pageSize": 10
  }
}
```

成功时文本内容为 `Retrieved N pets (page X/Y)`，结构化结果在 `structuredContent` 中。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | 宠物医院 REST API 地址 |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址 |
| `MCP_PORT` | `8000` | MCP 监听端口 |
| `MCP_PATH` | `/mcp` | MCP 路径 |
| `MCP_REQUEST_TIMEOUT` | `10.0` | 单次后端请求超时（秒） |
| `MCP_MAX_RETRIES` | `2` | 后端失败重试次数 |

同时运行 `anythingllm-mcp` 时请为两者分配不同端口，例如 `MCP_PORT=8001`。

## 安装与启动

需要 Python 3.11+，并先启动 pet-hospital：

```bash
# 终端 1：宠物医院服务
cd pet-hospital
./pethospital.exe            # Windows；或从 GitHub Releases 下载发行包

# 终端 2：MCP 服务
cd pet-hospital-mcp
python -m venv .venv
.venv/Scripts/activate       # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev,serve]"

PET_HOSPITAL_BASE_URL=http://127.0.0.1:8080 MCP_PORT=8001 pet-hospital-mcp
```

启动后日志会打印 `MCP endpoint: http://127.0.0.1:8001/mcp`。

## MCP 客户端配置

在客户端项目根目录的 `.mcp.json` 中加入：

```json
{
  "mcpServers": {
    "pet-hospital": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

ZAgent 会自动发现并加载其中的工具。

## 自然语言示例

```text
列出所有住院中的犬，按总花费从高到低排序，只看前 10 条。
```

```text
查一下主治医生是李医生的猫，总花费在 500 到 2000 元之间的档案。
```

## 错误处理

工具失败时返回 `is_error = true`，正文与 `structuredContent` 都是统一错误信封：

```json
{
  "error": {
    "code": "BACKEND_UNAVAILABLE",
    "message": "Backend is unreachable",
    "details": {}
  }
}
```

| 错误码 | 含义 |
| --- | --- |
| `VALIDATION_ERROR` | 输入不合法（枚举值、金额区间、分页范围等） |
| `BACKEND_TIMEOUT` | pet-hospital 响应超时 |
| `BACKEND_UNAVAILABLE` | 无法连接 pet-hospital |
| `BACKEND_API_ERROR` | 后端返回非 2xx |
| `BACKEND_INVALID_RESPONSE` | 后端响应结构无法解析 |
| `INTERNAL_ERROR` | 服务内部异常 |

## 测试

```bash
cd pet-hospital-mcp
pip install -e ".[dev]"
pytest
```

测试使用 `respx` 模拟后端，不要求 pet-hospital 正在运行。
