import mimetypes
import os

from .registry import Tool, register


def _get_cwd(_args: dict) -> str:
    return os.getcwd()


def _list_dir(args: dict) -> str:
    p = args["path"]
    items = sorted(os.listdir(p))
    return "\n".join(("[D] " if os.path.isdir(os.path.join(p, i)) else "[F] ") + i for i in items) or "(空目录)"


def _get_file_type(args: dict) -> str:
    p = args["path"]
    if not os.path.isfile(p):
        return "文件不存在"
    mime, _ = mimetypes.guess_type(p)
    ext = os.path.splitext(p)[1] or "(无扩展名)"
    return f"扩展名: {ext}, MIME: {mime or '未知'}"


def _read_file(args: dict) -> str:
    try:
        with open(args["path"], encoding="utf-8") as f:
            return f.read() or "(空文件)"
    except UnicodeDecodeError:
        return "不是纯文本文件，无法读取"


def _create_file(args: dict) -> str:
    path = os.path.join(args["directory"], args["filename"])
    try:
        open(path, "x").close()
    except FileExistsError:
        return f"{path} 已存在"
    return f"已创建 {path}"


def _edit_file(args: dict) -> str:
    with open(args["path"], "w", encoding="utf-8") as f:
        f.write(args["content"])
    return f"已写入 {args['path']}"


def _create_dir(args: dict) -> str:
    os.makedirs(args["path"], exist_ok=True)
    return f"已创建目录 {args['path']}"


def _delete_dir(args: dict) -> str:
    os.rmdir(args["path"])
    return f"已删除目录 {args['path']}"


def _delete_file(args: dict) -> str:
    os.remove(args["path"])
    return f"已删除文件 {args['path']}"


def _rename(args: dict) -> str:
    src = args["path"]
    dst = args["new_name"]
    if not os.path.isabs(dst) and os.path.dirname(dst) == "":
        dst = os.path.join(os.path.dirname(src), dst)
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
