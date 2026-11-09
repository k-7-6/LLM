import configparser
import os
from dataclasses import dataclass

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILENAME = "config.ini"

DEFAULT_CONFIG_TEMPLATE = """# ZAgent 配置文件
# 首次运行自动生成。请填写真实信息后重新启动 ZAgent。
# 未填写的项目会自动使用程序内置的默认值。

[llm]
base_url = https://api.deepseek.com/v1
api_key = mock-api-key-please-replace
model = deepseek-v4-flash
request_timeout = 120
max_retries = 2

[project]
# 项目根目录；留空表示当前目录。相对路径以本配置文件所在目录为基准。
root =

[agent]
# 单轮任务最多允许多少次模型调用（0 表示不限制）
max_steps = 30
# 单轮任务的总超时秒数（0 表示不限制）
loop_timeout = 600

[context]
# 0 表示使用 default_window，并在界面上标记为“默认”
window = 0
default_window = 128000
warn_ratio = 0.7
summary_target_tokens = 5000
summary_max_tokens = 6000
archive_dir = .agents/context

[sessions]
dir = .agents/sessions
title_length = 40
agents_file = AGENTS.md

[skills]
dir = .agents/skills
file = SKILL.md
max_description_length = 200
# loadSkill 单次返回的最大字符数，超出会截断
max_load_chars = 20000

[mcp]
config_file = .mcp.json
connect_timeout = 20
call_timeout = 60
max_tool_name_length = 64

[search]
url = https://qianfan.baidubce.com/v2/ai_search/chat/completions
baidu_qianfan_api_key = mock-search-key-please-replace
baidu_qianfan_model = ernie-4.5-turbo-32k
top_k = 5
timeout = 30
snippet_chars = 120

[fetch]
max_chars = 20000
user_agent = Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
max_time = 20
connect_timeout = 10
process_timeout = 30

[cli]
timeout = 30
max_output_chars = 8000
head_chars = 6000
tail_chars = 2000

[recall]
max_results = 20
max_output_chars = 6000
snippet_radius = 180

[files]
max_read_chars = 200000
# 文件工具允许访问的根目录；留空表示项目根目录
root =
# 是否允许覆盖写入、删除等危险操作；默认关闭
allow_dangerous_ops = false
"""


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    model: str

    request_timeout: float = 120.0
    max_retries: int = 2

    max_steps: int = 30
    loop_timeout: float = 600.0

    search_api_key: str = ""
    search_model: str = "ernie-4.5-turbo-32k"
    search_url: str = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    search_top_k: int = 5
    search_timeout: float = 30.0
    search_snippet_chars: int = 120

    project_root: str = ""
    context_window: int = 0
    default_context_window: int = 128_000
    context_warn_ratio: float = 0.70
    summary_target_tokens: int = 5_000
    summary_max_tokens: int = 6_000
    archive_dir: str = ".agents/context"

    sessions_dir: str = ".agents/sessions"
    session_title_length: int = 40
    agents_file: str = "AGENTS.md"

    skills_dir: str = ".agents/skills"
    skill_file: str = "SKILL.md"
    skill_description_length: int = 200
    skill_max_load_chars: int = 20_000

    mcp_config_file: str = ".mcp.json"
    mcp_connect_timeout: float = 20.0
    mcp_call_timeout: float = 60.0
    mcp_max_tool_name_length: int = 64

    fetch_max_chars: int = 20_000
    fetch_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    fetch_max_time: int = 20
    fetch_connect_timeout: int = 10
    fetch_process_timeout: float = 30.0

    cli_timeout: float = 30.0
    cli_max_output_chars: int = 8_000
    cli_head_chars: int = 6_000
    cli_tail_chars: int = 2_000

    recall_max_results: int = 20
    recall_max_output_chars: int = 6_000
    recall_snippet_radius: int = 180

    file_max_read_chars: int = 200_000
    files_root: str = ""
    files_allow_dangerous: bool = False


def app_config_path() -> str:
    return os.path.join(APP_DIR, DEFAULT_CONFIG_FILENAME)


def cwd_config_path() -> str:
    return os.path.join(os.getcwd(), DEFAULT_CONFIG_FILENAME)


def find_config_path(explicit: str | None = None) -> str | None:
    """按 --config/环境变量/当前目录/程序目录 的顺序查找已有配置文件。"""
    env_path = os.environ.get("ZAGENT_CONFIG", "").strip()
    for candidate in (explicit, env_path, cwd_config_path(), app_config_path()):
        if not candidate:
            continue
        path = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isfile(path):
            return path
    return None


def create_default_config(path: str) -> str:
    """创建一个包含全部配置项和 mock 值的完整配置文件。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as file:
            file.write(DEFAULT_CONFIG_TEMPLATE)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        pass
    return path


def ensure_config(explicit: str | None = None) -> tuple["Config", str | None]:
    """加载配置；当前目录没有 config.ini 时创建完整模板并返回其路径。"""
    candidate = explicit or os.environ.get("ZAGENT_CONFIG", "").strip()
    if candidate:
        path = os.path.abspath(os.path.expanduser(candidate))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        return load_config(path), None

    target = cwd_config_path()
    if os.path.isfile(target):
        return load_config(target), None

    try:
        create_default_config(target)
    except OSError:
        target = app_config_path()
        create_default_config(target)
    return load_config(target), os.path.abspath(target)


def load_config(path: str | None = None) -> Config:
    path = os.path.abspath(path or find_config_path() or app_config_path())
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8-sig")
    except configparser.Error:
        pass

    root = _text(parser, "project", "root", "")
    if root and not os.path.isabs(root):
        root = os.path.normpath(os.path.join(os.path.dirname(path), root))

    files_root = _text(parser, "files", "root", "")
    if files_root and not os.path.isabs(files_root):
        files_root = os.path.normpath(
            os.path.join(os.path.dirname(path), files_root)
        )

    context_window = _int(parser, "context", "window", 0, minimum=0)
    summary_max = _int(parser, "context", "summary_max_tokens", 6_000, minimum=100)
    summary_target = _int(
        parser, "context", "summary_target_tokens", 5_000, minimum=100,
    )
    summary_target = min(summary_target, summary_max)

    cli_max = _int(parser, "cli", "max_output_chars", 8_000, minimum=100)
    cli_head = _int(parser, "cli", "head_chars", 6_000, minimum=0)
    cli_tail = _int(parser, "cli", "tail_chars", 2_000, minimum=0)
    cli_max = max(cli_max, cli_head + cli_tail)

    return Config(
        base_url=_text(parser, "llm", "base_url", "https://api.deepseek.com/v1"),
        api_key=_text(parser, "llm", "api_key", ""),
        model=_text(parser, "llm", "model", "deepseek-v4-flash"),
        request_timeout=_float(
            parser, "llm", "request_timeout", 120.0, minimum=1.0,
        ),
        max_retries=_int(parser, "llm", "max_retries", 2, minimum=0),

        max_steps=_int(parser, "agent", "max_steps", 30, minimum=0),
        loop_timeout=_float(
            parser, "agent", "loop_timeout", 600.0, minimum=0.0,
        ),

        search_api_key=_text(parser, "search", "baidu_qianfan_api_key", ""),
        search_model=_text(
            parser, "search", "baidu_qianfan_model", "ernie-4.5-turbo-32k",
        ),
        search_url=_text(
            parser, "search", "url",
            "https://qianfan.baidubce.com/v2/ai_search/chat/completions",
        ),
        search_top_k=_int(parser, "search", "top_k", 5, minimum=1, maximum=50),
        search_timeout=_float(parser, "search", "timeout", 30.0, minimum=1.0),
        search_snippet_chars=_int(
            parser, "search", "snippet_chars", 120, minimum=20,
        ),

        project_root=root,
        context_window=context_window,
        default_context_window=_int(
            parser, "context", "default_window", 128_000, minimum=1_000,
        ),
        context_warn_ratio=_float(
            parser, "context", "warn_ratio", 0.70, minimum=0.05, maximum=0.99,
        ),
        summary_target_tokens=summary_target,
        summary_max_tokens=summary_max,
        archive_dir=_text(parser, "context", "archive_dir", ".agents/context"),

        sessions_dir=_text(parser, "sessions", "dir", ".agents/sessions"),
        session_title_length=_int(
            parser, "sessions", "title_length", 40, minimum=10, maximum=200,
        ),
        agents_file=_text(parser, "sessions", "agents_file", "AGENTS.md"),

        skills_dir=_text(parser, "skills", "dir", ".agents/skills"),
        skill_file=_text(parser, "skills", "file", "SKILL.md"),
        skill_description_length=_int(
            parser, "skills", "max_description_length", 200, minimum=20,
        ),
        skill_max_load_chars=_int(
            parser, "skills", "max_load_chars", 20_000, minimum=1_000,
        ),

        mcp_config_file=_text(parser, "mcp", "config_file", ".mcp.json"),
        mcp_connect_timeout=_float(
            parser, "mcp", "connect_timeout", 20.0, minimum=1.0,
        ),
        mcp_call_timeout=_float(
            parser, "mcp", "call_timeout", 60.0, minimum=1.0,
        ),
        mcp_max_tool_name_length=_int(
            parser, "mcp", "max_tool_name_length", 64, minimum=8, maximum=64,
        ),

        fetch_max_chars=_int(parser, "fetch", "max_chars", 20_000, minimum=500),
        fetch_user_agent=_text(
            parser, "fetch", "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ),
        fetch_max_time=_int(parser, "fetch", "max_time", 20, minimum=1),
        fetch_connect_timeout=_int(
            parser, "fetch", "connect_timeout", 10, minimum=1,
        ),
        fetch_process_timeout=_float(
            parser, "fetch", "process_timeout", 30.0, minimum=1.0,
        ),

        cli_timeout=_float(parser, "cli", "timeout", 30.0, minimum=1.0),
        cli_max_output_chars=cli_max,
        cli_head_chars=cli_head,
        cli_tail_chars=cli_tail,

        recall_max_results=_int(
            parser, "recall", "max_results", 20, minimum=1, maximum=100,
        ),
        recall_max_output_chars=_int(
            parser, "recall", "max_output_chars", 6_000, minimum=200,
        ),
        recall_snippet_radius=_int(
            parser, "recall", "snippet_radius", 180, minimum=20,
        ),

        file_max_read_chars=_int(
            parser, "files", "max_read_chars", 200_000, minimum=1_000,
        ),
        files_root=files_root,
        files_allow_dangerous=_bool(
            parser, "files", "allow_dangerous_ops", False,
        ),
    )


def _text(parser: configparser.ConfigParser, section: str, key: str,
          default: str) -> str:
    try:
        value = parser.get(section, key, fallback="")
    except configparser.Error:
        return default
    value = value.strip()
    return value or default


def _int(parser: configparser.ConfigParser, section: str, key: str,
         default: int, minimum: int | None = None,
         maximum: int | None = None) -> int:
    value = _number(parser, section, key, default, int)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return int(value)


def _float(parser: configparser.ConfigParser, section: str, key: str,
           default: float, minimum: float | None = None,
           maximum: float | None = None) -> float:
    value = _number(parser, section, key, default, float)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return float(value)


def _bool(parser: configparser.ConfigParser, section: str, key: str,
          default: bool = False) -> bool:
    try:
        raw = parser.get(section, key, fallback="").strip().lower()
    except configparser.Error:
        return default
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _number(parser: configparser.ConfigParser, section: str, key: str,
            default, cast):
    try:
        raw = parser.get(section, key, fallback="").strip()
    except configparser.Error:
        return default
    if not raw:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default
