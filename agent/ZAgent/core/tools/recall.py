"""recallContext：在 .agents/context/ 的原始对话归档中做全文检索。"""

import json
import os
import re

from ..context import archive_directory, message_text
from .registry import Tool, register

MAX_RESULTS = 20
MAX_OUTPUT_CHARS = 6_000
SNIPPET_RADIUS = 180

_project_root = ""
_archive_dir = ".agents/context"
_max_results = MAX_RESULTS
_max_output_chars = MAX_OUTPUT_CHARS
_snippet_radius = SNIPPET_RADIUS


def configure(project_root: str | None, config=None) -> None:
    global _project_root, _archive_dir, _max_results, _max_output_chars
    global _snippet_radius
    _project_root = os.path.abspath(project_root or os.getcwd())
    _archive_dir = getattr(config, "archive_dir", ".agents/context") or ".agents/context"
    _max_results = max(
        1, int(getattr(config, "recall_max_results", MAX_RESULTS)
               or MAX_RESULTS),
    )
    _max_output_chars = max(
        200, int(getattr(config, "recall_max_output_chars", MAX_OUTPUT_CHARS)
                 or MAX_OUTPUT_CHARS),
    )
    _snippet_radius = max(
        20, int(getattr(config, "recall_snippet_radius", SNIPPET_RADIUS)
                or SNIPPET_RADIUS),
    )


def _archive_files(root: str, archive_id: str | None):
    directory = archive_directory(root, _archive_dir)
    if not os.path.isdir(directory):
        return [], "当前项目还没有上下文归档（.agents/context/）。"

    if archive_id:
        if not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", archive_id):
            return [], "归档编号无效。"
        path = os.path.join(directory, archive_id + ".jsonl")
        if not os.path.isfile(path):
            return [], f"未找到编号为 {archive_id} 的归档文件。"
        return [(archive_id, path)], ""

    files = []
    for name in sorted(os.listdir(directory), reverse=True):
        if name.endswith(".jsonl"):
            files.append((name[:-6], os.path.join(directory, name)))
    if not files:
        return [], "当前项目还没有上下文归档（.agents/context/）。"
    return files, ""


def _snippet(text: str, query: str) -> str:
    index = text.casefold().find(query)
    if index < 0:
        return ""
    start = max(0, index - _snippet_radius)
    end = min(len(text), index + len(query) + _snippet_radius)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def _matches_in_file(archive_id: str, path: str, query: str) -> list[dict]:
    matches: list[dict] = []
    try:
        with open(path, encoding="utf-8") as file:
            for line_no, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                text = f"{message.get('role', '')}\n{message_text(message)}"
                count = text.casefold().count(query)
                if not count:
                    continue
                matches.append({
                    "score": count,
                    "archive_id": archive_id,
                    "line": line_no,
                    "role": message.get("role", "unknown"),
                    "snippet": _snippet(text, query),
                })
    except OSError:
        return []
    return matches


def search(project_root: str, text: str, archive_id: str | None = None) -> str:
    query = (text or "").strip()
    if not query:
        return "错误: text 参数不能为空。"

    files, error = _archive_files(project_root, archive_id)
    if error:
        return error

    needle = query.casefold()
    matches: list[dict] = []
    for current_id, path in files:
        matches.extend(_matches_in_file(current_id, path, needle))
    if not matches:
        scope = f"归档 {archive_id}" if archive_id else "全部归档"
        return f"未在{scope}中找到包含 “{query}” 的内容。"

    matches.sort(key=lambda item: item["score"], reverse=True)
    total = len(matches)
    matches = matches[:_max_results]

    lines = [f"找到 {total} 条匹配，按相关度返回前 {len(matches)} 条："]
    used = len(lines[0])
    for item in matches:
        block = (
            f"\n[归档 {item['archive_id']} · 第 {item['line']} 条消息"
            f" · {item['role']} · 匹配 {item['score']} 次]\n"
            f"{item['snippet']}"
        )
        if used + len(block) > _max_output_chars:
            lines.append(
                "\n（结果已达到长度上限，请使用更具体的关键词或指定 id 继续检索。）"
            )
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


def _recall(arguments: dict) -> str:
    text = str(arguments.get("text", "") or "").strip()
    archive_id = str(arguments.get("id", "") or "").strip() or None
    root = _project_root or os.getcwd()
    try:
        return search(root, text, archive_id)
    except Exception as exc:
        return f"错误: 检索归档失败: {exc}"


register(Tool(
    name="recallContext",
    description=(
        "在上下文压缩前保存的原始对话归档中做全文关键词检索。"
        "当历史摘要缺少细节、需要查找旧消息时使用。"
        "不传 id 时检索 .agents/context/ 下的全部归档；传入 id 时只检索对应归档。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要检索的关键词或文本，不能为空。",
            },
            "id": {
                "type": "string",
                "description": "可选，归档编号，例如 20261022-153000。",
            },
        },
        "required": ["text"],
    },
    handler=_recall,
))
