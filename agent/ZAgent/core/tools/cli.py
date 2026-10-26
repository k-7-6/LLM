import locale
import subprocess

from .registry import Tool, register

TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 8000
HEAD_CHARS = 6000
TAIL_CHARS = 2000


def _decode(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return data.decode(encoding).replace("\r\n", "\n")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _clip(text: str) -> str:
    text = text.strip("\n")
    if not text:
        return "（空）"
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    omitted = len(text) - HEAD_CHARS - TAIL_CHARS
    return (
        text[:HEAD_CHARS].rstrip()
        + f"\n…（输出过长，中间省略 {omitted} 字符）…\n"
        + text[-TAIL_CHARS:].lstrip()
    )


def _run_cli(raw: dict) -> str:
    command = str(raw.get("command", "")).strip()
    raw_args = raw.get("args") or []
    if not command:
        return "错误: 程序名称 command 不能为空"
    if not isinstance(raw_args, (list, tuple)):
        return "错误: args 必须是字符串列表"

    argv = [command] + [str(item) for item in raw_args]
    shown = " ".join(argv)

    try:
        result = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_SECONDS)
    except FileNotFoundError:
        return f"错误: 未找到命令 '{command}'，请确认程序已安装并加入 PATH"
    except PermissionError:
        return f"错误: 没有权限执行 '{command}'"
    except subprocess.TimeoutExpired as exc:
        return (
            f"命令: {shown}\n退出码: 无（执行超过 {TIMEOUT_SECONDS} 秒，已终止）\n"
            f"标准输出:\n{_clip(_decode(exc.stdout or b''))}\n\n"
            f"标准错误:\n{_clip(_decode(exc.stderr or b''))}"
        )
    except OSError as exc:
        return f"错误: 无法执行 '{command}'：{exc}"

    return (
        f"命令: {shown}\n退出码: {result.returncode}\n"
        f"标准输出:\n{_clip(_decode(result.stdout))}\n\n"
        f"标准错误:\n{_clip(_decode(result.stderr))}"
    )


register(Tool(
    name="RunCli",
    description="在本地执行已安装的命令行程序，返回标准输出、标准错误和退出码。需要运行命令行工具时使用。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "程序名称，例如 git、python、node"},
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参数列表，例如 [\"--version\"]",
            },
        },
        "required": ["command", "args"],
    },
    handler=_run_cli,
))
