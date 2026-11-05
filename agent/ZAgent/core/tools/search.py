import json
import urllib.error
import urllib.request

from .registry import Tool, register

SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
DEFAULT_MODEL = "ernie-4.5-turbo-32k"
DEFAULT_TOP_K = 5
DEFAULT_TIMEOUT = 30.0
DEFAULT_SNIPPET_CHARS = 120

_api_key = ""
_model = DEFAULT_MODEL
_url = SEARCH_URL
_top_k = DEFAULT_TOP_K
_timeout = DEFAULT_TIMEOUT
_snippet_chars = DEFAULT_SNIPPET_CHARS


def configure(config) -> None:
    global _api_key, _model, _url, _top_k, _timeout, _snippet_chars
    _api_key = (getattr(config, "search_api_key", "") or "").strip()
    _model = (
        getattr(config, "search_model", "") or DEFAULT_MODEL
    ).strip() or DEFAULT_MODEL
    _url = (getattr(config, "search_url", "") or SEARCH_URL).strip() or SEARCH_URL
    _top_k = max(1, int(getattr(config, "search_top_k", DEFAULT_TOP_K) or DEFAULT_TOP_K))
    _timeout = max(
        1.0, float(getattr(config, "search_timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
    )
    _snippet_chars = max(
        20,
        int(getattr(config, "search_snippet_chars", DEFAULT_SNIPPET_CHARS)
            or DEFAULT_SNIPPET_CHARS),
    )


def _search_web(args: dict) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "错误: 搜索关键词不能为空"
    if not _api_key:
        return "错误: 未配置百度千帆 API Key，请在 config.ini 的 [search] 中设置 baidu_qianfan_api_key"

    payload = {
        "model": _model,
        "messages": [{"role": "user", "content": query}],
        "stream": False,
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": _top_k}],
    }
    request = urllib.request.Request(
        _url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key}",
            "X-Appbuilder-Authorization": f"Bearer {_api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=_timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"错误: 搜索服务返回 HTTP {exc.code}，详情：{detail[:500]}"
    except urllib.error.URLError as exc:
        return f"错误: 无法连接搜索服务：{exc.reason}"
    except TimeoutError:
        return "错误: 搜索请求超时"
    except json.JSONDecodeError:
        return "错误: 搜索服务返回了无法解析的数据"
    except Exception as exc:
        return f"错误: 搜索失败：{exc}"

    if data.get("code") not in (None, 0, "0"):
        return f"错误: 搜索服务返回错误：{data.get('message') or data.get('code')}"

    choices = data.get("choices") or []
    references = data.get("references") or []

    if not choices and not references:
        return f"错误: 搜索服务未返回结果：{json.dumps(data, ensure_ascii=False)[:500]}"

    answer = ""
    if choices:
        answer = (choices[0].get("message") or {}).get("content") or ""

    lines = [answer or "（未返回摘要）", "", "参考来源："]
    if references:
        for i, ref in enumerate(references, 1):
            title = ref.get("title") or "(无标题)"
            url = ref.get("url") or ""
            snippet = (ref.get("content") or "").strip()
            if len(snippet) > _snippet_chars:
                snippet = snippet[:_snippet_chars] + "…"
            lines.append(f"{i}. {title}")
            if url:
                lines.append(f"   {url}")
            if snippet:
                lines.append(f"   {snippet}")
    else:
        lines.append("（无）")

    return "\n".join(lines)


register(Tool(
    name="searchWeb",
    description="联网搜索最新信息。当问题涉及实时动态、最新消息或你不确定的事实时使用。返回搜索摘要和参考来源。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词或问题"},
        },
        "required": ["query"],
    },
    handler=_search_web,
))
