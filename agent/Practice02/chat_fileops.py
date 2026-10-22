import configparser
import json
import mimetypes
import os
import subprocess
import sys
import traceback

from openai import OpenAI

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")


def tool(name, desc, props=None, required=None):
    schema = {"type": "object", "properties": props or {}}
    if required:
        schema["required"] = required
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": schema}}


tools = [
    tool("getdate", "获取当前电脑的日期和时间"),
    tool("get_cwd", "获取当前工作目录"),
    tool("list_dir", "列出指定目录下的所有文件和子目录", {"path": {"type": "string", "description": "目录路径"}}, ["path"]),
    tool("get_file_type", "获取指定文件的类型", {"path": {"type": "string", "description": "文件路径"}}, ["path"]),
    tool("read_file", "读取纯文本文件的内容", {"path": {"type": "string", "description": "文件路径"}}, ["path"]),
    tool("create_file", "在指定目录下创建新文件（已存在则失败）",
         {"directory": {"type": "string", "description": "目录路径"},
          "filename": {"type": "string", "description": "文件名"}}, ["directory", "filename"]),
    tool("edit_file", "用新内容覆盖写入纯文本文件", {"path": {"type": "string", "description": "文件路径"},
         "content": {"type": "string", "description": "要写入的完整内容"}}, ["path", "content"]),
    tool("create_dir", "创建新目录（含父目录）", {"path": {"type": "string", "description": "目录路径"}}, ["path"]),
    tool("delete_dir", "删除空目录（非空会失败）", {"path": {"type": "string", "description": "目录路径"}}, ["path"]),
    tool("delete_file", "删除指定文件", {"path": {"type": "string", "description": "文件路径"}}, ["path"]),
    tool("rename", "重命名文件或目录（new_name 可以是新名字，也可以是新路径）",
         {"path": {"type": "string", "description": "原路径"},
          "new_name": {"type": "string", "description": "新名字或新路径"}}, ["path", "new_name"]),
]


def get_cwd(a):
    return os.getcwd()


def list_dir(a):
    p = a["path"]
    items = sorted(os.listdir(p))
    return "\n".join(("[D] " if os.path.isdir(os.path.join(p, i)) else "[F] ") + i for i in items) or "(空目录)"


def get_file_type(a):
    p = a["path"]
    if not os.path.isfile(p):
        return "文件不存在"
    mime, _ = mimetypes.guess_type(p)
    ext = os.path.splitext(p)[1] or "(无扩展名)"
    return f"扩展名: {ext}, MIME: {mime or '未知'}"


def read_file(a):
    try:
        with open(a["path"], encoding="utf-8") as f:
            return f.read() or "(空文件)"
    except UnicodeDecodeError:
        return "不是纯文本文件，无法读取"


def create_file(a):
    path = os.path.join(a["directory"], a["filename"])
    try:
        open(path, "x").close()
    except FileExistsError:
        return f"{path} 已存在"
    return f"已创建 {path}"


def edit_file(a):
    with open(a["path"], "w", encoding="utf-8") as f:
        f.write(a["content"])
    return f"已写入 {a['path']}"


def create_dir(a):
    os.makedirs(a["path"], exist_ok=True)
    return f"已创建目录 {a['path']}"


def delete_dir(a):
    os.rmdir(a["path"])
    return f"已删除目录 {a['path']}"


def delete_file(a):
    os.remove(a["path"])
    return f"已删除文件 {a['path']}"


def rename(a):
    src = a["path"]
    dst = a["new_name"]
    if not os.path.isabs(dst) and os.path.dirname(dst) == "":
        dst = os.path.join(os.path.dirname(src), dst)
    os.rename(src, dst)
    return f"已重命名 {src} -> {dst}"


handlers = {
    "get_cwd": get_cwd,
    "list_dir": list_dir,
    "get_file_type": get_file_type,
    "read_file": read_file,
    "create_file": create_file,
    "edit_file": edit_file,
    "create_dir": create_dir,
    "delete_dir": delete_dir,
    "delete_file": delete_file,
    "rename": rename,
}

try:
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")

    base_url = config["llm"]["base_url"]
    api_key = config["llm"]["api_key"]
    model = config["llm"]["model"]

    client = OpenAI(base_url=base_url, api_key=api_key)
    messages = []

    print("按 Ctrl+C 退出")
    while True:
        prompt = input("你好请提出你的问题: ")
        messages.append({"role": "user", "content": prompt})
        print("-----")

        while True:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                stream=True,
            )
            reply = ""
            calls = {}
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    reply += delta.content
                    print(delta.content, end="", flush=True)
                for tc in delta.tool_calls or []:
                    c = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        c["id"] = tc.id
                    if tc.function.name:
                        c["name"] += tc.function.name
                    if tc.function.arguments:
                        c["arguments"] += tc.function.arguments

            if not calls:
                messages.append({"role": "assistant", "content": reply})
                print()
                break

            messages.append({
                "role": "assistant",
                "content": reply or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls.values()
                ],
            })
            for c in calls.values():
                try:
                    if c["name"] == "getdate":
                        out = subprocess.run(
                            "date /T && time /T",
                            shell=True, capture_output=True, text=True, errors="replace",
                        )
                        result = out.stdout.strip() or out.stderr.strip()
                    else:
                        result = handlers[c["name"]](json.loads(c["arguments"] or "{}"))
                except Exception as e:
                    result = f"错误: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": result,
                })
except Exception:
    traceback.print_exc()
    try:
        input("\n出错了，按回车键关闭窗口...")
    except EOFError:
        pass
