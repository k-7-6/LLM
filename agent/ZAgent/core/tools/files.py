import mimetypes
import os

from .registry import Tool, register

MAX_READ_CHARS = 200_000
_max_read_chars = MAX_READ_CHARS
_root = ""
_allow_dangerous = False


def configure(config, project_root: str | None = None) -> None:
    global _max_read_chars, _root, _allow_dangerous
    _max_read_chars = max(
        1_000,
        int(getattr(config, "file_max_read_chars", MAX_READ_CHARS)
            or MAX_READ_CHARS),
    )
    root = getattr(config, "files_root", "") or project_root or ""
    _root = os.path.abspath(os.path.expanduser(root)) if root else ""
    _allow_dangerous = bool(
        getattr(config, "files_allow_dangerous", False)
    )


def _resolve(path: str) -> str:
    """将路径规范化为绝对路径，并限制在允许的根目录内。"""
    text = str(path or "").strip()
    if not text:
        raise ValueError("路径不能为空")
    target = os.path.abspath(os.path.expanduser(text))
    if not _root:
        return target
    root = os.path.realpath(_root)
    resolved = os.path.realpath(target)
    try:
        inside = os.path.commonpath([root, resolved]) == root
    except ValueError:  # Windows 不同盘符
        inside = False
    if not inside:
        raise ValueError(f"路径超出允许范围: {text}（允许根目录: {_root}）")
    return resolved


def _check_dangerous(action: str) -> None:
    if not _allow_dangerous:
        raise ValueError(
            f"{action} 已被禁用。如确需执行，请在 config.ini 的 [files] 中设置 "
            "allow_dangerous_ops = true"
        )


def _get_cwd(_args: dict) -> str:
    return os.getcwd()


def _list_dir(args: dict) -> str:
    p = _resolve(args["path"])
    items = sorted(os.listdir(p))

    def mark(name: str) -> str:
        full = os.path.join(p, name)
        if os.path.islink(full):
            return "[L] "
        return "[D] " if os.path.isdir(full) else "[F] "

    return "\n".join(mark(i) + i for i in items) or "(空目录)"


def _get_file_type(args: dict) -> str:
    p = _resolve(args["path"])
    if os.path.islink(p):
        return "符号链接"
    if os.path.isdir(p):
        return "目录"
    if not os.path.isfile(p):
        return "路径不存在"
    mime, _ = mimetypes.guess_type(p)
    ext = os.path.splitext(p)[1] or "(无扩展名)"
    return f"扩展名: {ext}, MIME: {mime or '未知'}"


def _read_file(args: dict) -> str:
    path = _resolve(args["path"])
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(_max_read_chars + 1)
    except UnicodeDecodeError:
        return "不是纯文本文件，无法读取"
    if not text:
        return "(空文件)"
    if len(text) > _max_read_chars:
        return (
            text[:_max_read_chars].rstrip()
            + f"\n\n…（文件过长，已截断，仅显示前 {_max_read_chars:,} 字符）"
        )
    return text


def _create_file(args: dict) -> str:
    directory = _resolve(args["directory"])
    path = _resolve(os.path.join(directory, args["filename"]))
    try:
        open(path, "x").close()
    except FileExistsError:
        return f"{path} 已存在"
    return f"已创建 {path}"


def _edit_file(args: dict) -> str:
    path = _resolve(args["path"])
    _check_dangerous("覆盖写入")
    with open(path, "w", encoding="utf-8") as f:
        f.write(args["content"])
    return f"已写入 {path}"


def _create_dir(args: dict) -> str:
    path = _resolve(args["path"])
    os.makedirs(path, exist_ok=True)
    return f"已创建目录 {path}"


def _delete_dir(args: dict) -> str:
    path = _resolve(args["path"])
    _check_dangerous("删除目录")
    os.rmdir(path)
    return f"已删除目录 {path}"


def _delete_file(args: dict) -> str:
    path = _resolve(args["path"])
    _check_dangerous("删除文件")
    os.remove(path)
    return f"已删除文件 {path}"


def _rename(args: dict) -> str:
    src = _resolve(args["path"])
    raw_dst = str(args["new_name"] or "").strip()
    if not raw_dst:
        raise ValueError("new_name 不能为空")
    if not os.path.isabs(raw_dst) and os.path.dirname(raw_dst) == "":
        dst = _resolve(os.path.join(os.path.dirname(src), raw_dst))
    else:
        dst = _resolve(raw_dst)
    if os.path.exists(dst):
        _check_dangerous("覆盖重命名")
    os.rename(src, dst)
    return f"已重命名 {src} -> {dst}"


_PATH = {"type": "string", "description": "路径"}

register(Tool("get_cwd", "获取当前工作目录", {"type": "object", "properties": {}}, _get_cwd))

register(Tool("list_dir", "列出指定目录下的所有文件和子目录",
              {"type": "object", "properties": {"path": {"type": "string", "description": "目录路径"}},
               "required": ["path"]}, _list_dir))

register(Tool("get_file_type", "获取指定文件的类型",
              {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}},
               "required": ["path"]}, _get_file_type))

register(Tool("read_file", "读取纯文本文件的内容",
              {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}},
               "required": ["path"]}, _read_file))

register(Tool("create_file", "在指定目录下创建新文件（已存在则失败）",
              {"type": "object", "properties": {
                  "directory": {"type": "string", "description": "目录路径"},
                  "filename": {"type": "string", "description": "文件名"}},
               "required": ["directory", "filename"]}, _create_file))

register(Tool("edit_file", "用新内容覆盖写入纯文本文件",
              {"type": "object", "properties": {
                  "path": {"type": "string", "description": "文件路径"},
                  "content": {"type": "string", "description": "要写入的完整内容"}},
               "required": ["path", "content"]}, _edit_file))

register(Tool("create_dir", "创建新目录（含父目录）",
              {"type": "object", "properties": {"path": {"type": "string", "description": "目录路径"}},
               "required": ["path"]}, _create_dir))

register(Tool("delete_dir", "删除空目录（非空会失败）",
              {"type": "object", "properties": {"path": {"type": "string", "description": "目录路径"}},
               "required": ["path"]}, _delete_dir))

register(Tool("delete_file", "删除指定文件",
              {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}},
               "required": ["path"]}, _delete_file))

register(Tool("rename", "重命名文件或目录（new_name 可以是新名字，也可以是新路径）",
              {"type": "object", "properties": {
                  "path": {"type": "string", "description": "原路径"},
                  "new_name": {"type": "string", "description": "新名字或新路径"}},
               "required": ["path", "new_name"]}, _rename))
