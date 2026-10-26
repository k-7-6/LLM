import subprocess
import urllib.parse

import trafilatura

from .registry import Tool, register

MAX_CHARS = 20000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch_web(args: dict) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        return "错误: 网页 URL 不能为空"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "错误: 仅支持 http/https 网址"

    command = [
        "curl",
        "--location",
        "--compressed",
        "--silent",
        "--show-error",
        "--max-time", "20",
        "--connect-timeout", "10",
        "--proto", "=http,https",
        "--proto-redir", "=http,https",
        "--user-agent", USER_AGENT,
        "--write-out", "\n__STATUS__%{http_code}",
        url,
    ]

    try:
        result = subprocess.run(command, capture_output=True, timeout=30)
    except FileNotFoundError:
        return "错误: 未找到 curl 命令，请确认系统已安装 curl"
    except subprocess.TimeoutExpired:
        return "错误: 获取网页超时（30 秒）"
    except OSError as exc:
        return f"错误: 无法执行 curl：{exc}"

    raw = result.stdout or b""
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        return f"错误: 网页访问失败（curl 退出码 {result.returncode}）：{detail[:300] or '无详细信息'}"

    status = ""
    marker = b"\n__STATUS__"
    if marker in raw:
        raw, _, tail = raw.rpartition(marker)
        status = tail.strip().decode("ascii", errors="ignore")
    if status and not status.startswith(("2", "3")):
        return f"错误: 网页返回 HTTP {status}"

    if not raw.strip():
        return "错误: 网页返回了空内容"

    try:
        text = trafilatura.extract(
            raw,
            url=url,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_images=False,
            include_comments=False,
        )
    except Exception as exc:
        return f"错误: HTML 解析失败：{exc}"

    if not text or not text.strip():
        return "错误: 未能从该网页提取到正文（可能是动态渲染页面、登录页或非文章页面）"

    text = text.strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "\n\n…（内容过长，已截断）"

    return f"来源: {url}\n\n{text}"


register(Tool(
    name="fetchWeb",
    description="获取指定网页的正文并转换为 Markdown。当需要阅读某个网址的具体内容时使用，会自动去除导航、广告和页脚。",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的网页网址（http/https）"},
        },
        "required": ["url"],
    },
    handler=_fetch_web,
))
