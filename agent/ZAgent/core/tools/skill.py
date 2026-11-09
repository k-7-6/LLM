import os
import re

import yaml

from ..skills import SKILL_FILE, SKILLS_DIR, AmbiguousResource, Skill, read
from .registry import Tool, register

# 启动时由 configure 注入已发现的技能与项目根目录，handler 通过技能名查找。
_skills: dict[str, Skill] = {}
_project_root = ""
_skills_dir = SKILLS_DIR
_skill_file = SKILL_FILE
_max_derived_description = 200
_max_load_chars = 20_000

_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def configure(skills: list[Skill], project_root: str | None = None,
              config=None) -> None:
    global _project_root, _skills_dir, _skill_file
    global _max_derived_description, _max_load_chars
    _skills.clear()
    _skills.update({skill.name: skill for skill in skills})
    _project_root = os.path.abspath(project_root or os.getcwd())
    _skills_dir = getattr(config, "skills_dir", SKILLS_DIR) or SKILLS_DIR
    _skill_file = getattr(config, "skill_file", SKILL_FILE) or SKILL_FILE
    _max_derived_description = max(
        20,
        int(getattr(config, "skill_description_length", 200) or 200),
    )
    _max_load_chars = max(
        1_000,
        int(getattr(config, "skill_max_load_chars", 20_000) or 20_000),
    )


def _load_skill(raw: dict) -> str:
    name = str(raw.get("name", "")).strip()
    skill = _skills.get(name)
    if skill is None:
        available = "、".join(_skills) or "（无）"
        return f"错误: 未找到技能 '{name}'，可用技能: {available}"

    filename = str(raw.get("filename", "") or "").strip() or None
    try:
        text = read(skill, filename)
    except AmbiguousResource as exc:
        lines = [f"错误: 技能 '{name}' 中有多个名为 '{exc.filename}' 的文件，"
                 "请用 filename 指定其中一个："]
        lines += [f"- {candidate}" for candidate in exc.candidates]
        return "\n".join(lines)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return f"错误: {exc}"

    if len(text) > _max_load_chars:
        text = (
            text[:_max_load_chars].rstrip()
            + f"\n\n…（内容过长，已截断到 {_max_load_chars:,} 字符；"
            "可用 filename 读取具体文件）"
        )
    return text


def _create_skill(raw: dict) -> str:
    name = str(raw.get("name", "")).strip().lower()
    context = str(raw.get("skillContext", "") or "")

    if not name:
        return "错误: name 不能为空"
    if not _NAME_PATTERN.fullmatch(name):
        return "错误: Skill 名称必须由小写字母、数字和连字符组成，例如 'weather-report'"
    if not context.strip():
        return "错误: skillContext 不能为空"
    if name in _skills:
        return f"错误: Skill '{name}' 已存在，未创建任何文件"

    root = _project_root or os.path.abspath(os.getcwd())
    skill_dir = os.path.join(root, _skills_dir, name)
    if os.path.exists(skill_dir):
        return f"错误: Skill '{name}' 已存在，未创建任何文件"

    try:
        meta, body, description = _prepare(name, context)
        content = _render(meta, body)
    except (ValueError, yaml.YAMLError) as exc:
        return f"错误: {exc}"

    try:
        os.makedirs(skill_dir, exist_ok=False)
    except FileExistsError:
        return f"错误: Skill '{name}' 已存在，未创建任何文件"
    except OSError as exc:
        return f"错误: 无法创建技能目录 {skill_dir}: {exc}"

    path = os.path.join(skill_dir, _skill_file)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(content)
    except OSError as exc:
        try:
            os.rmdir(skill_dir)
        except OSError:
            pass
        return f"错误: 写入 {path} 失败: {exc}"

    _skills[name] = Skill(name=name, description=description, path=path, root=root)
    return (
        f"已创建 Skill '{name}': {path}\n"
        "SKILL.md 已生成；references/、scripts/ 等辅助文件请继续使用文件操作工具创建。"
        "重启 ZAgent 后，新技能会出现在系统提示的技能列表中。"
    )


def _prepare(name: str, context: str) -> tuple[dict, str, str]:
    """校验/补全 Frontmatter，返回 (元信息, 正文, description)。"""
    meta, body = _split_frontmatter(context)

    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        description = " ".join(description.split())
    else:
        description = _derive_description(body)
    if not description:
        raise ValueError("无法确定 description，请在 Frontmatter 中提供，或确保正文非空")

    body = body.strip()
    if not body:
        raise ValueError("skillContext 缺少正文内容")

    extra = {key: value for key, value in meta.items()
             if key not in ("name", "description")}
    merged = {"name": name, "description": description}
    merged.update(extra)
    return merged, body, description


def _split_frontmatter(context: str) -> tuple[dict, str]:
    text = context.lstrip(chr(0xFEFF))
    lines = text.splitlines()

    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        return {}, text

    for end in range(start + 1, len(lines)):
        if lines[end].strip() != "---":
            continue
        try:
            meta = yaml.safe_load("\n".join(lines[start + 1:end]))
        except yaml.YAMLError as exc:
            raise ValueError(f"skillContext 的 YAML Frontmatter 无效: {exc}") from exc
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            raise ValueError("skillContext 的 YAML Frontmatter 必须是映射")
        return meta, "\n".join(lines[end + 1:])

    raise ValueError("skillContext 的 YAML Frontmatter 未闭合")


def _derive_description(body: str) -> str:
    for line in body.splitlines():
        text = " ".join(line.strip().lstrip("#>*-").split())
        if text:
            return text[:_max_derived_description]
    return ""


def _render(meta: dict, body: str) -> str:
    header = yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False, width=1_000_000,
    ).strip()
    return f"---\n{header}\n---\n\n{body}\n"


register(Tool(
    name="loadSkill",
    description=(
        "加载指定技能。只提供 name 时返回该技能 SKILL.md 的全文；提供 filename 时"
        "只读取该附加文件，不再加载 SKILL.md。filename 可以是绝对路径、相对技能目录"
        "的路径或相对项目根目录的路径，且必须位于该技能目录内。只给文件名时会递归"
        "搜索技能目录：唯一匹配直接返回，多个同名文件则返回候选路径供你选择。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名称，见系统提示中的技能列表"},
            "filename": {
                "type": "string",
                "description": "可选，要加载的附加文件路径或文件名；省略则加载 SKILL.md",
            },
        },
        "required": ["name"],
    },
    handler=_load_skill,
))

register(Tool(
    name="createSkill",
    description=(
        "当用户要求创建一个新 Skill 时调用。在项目 .agents/skills/<name>/ 下创建目录并生成 "
        "SKILL.md。name 必须是小写字母、数字和连字符，例如 weather-report。skillContext 是"
        "要写入的完整内容：建议包含带 name、description 的 YAML Frontmatter；缺少 description "
        "时会用正文首行生成，name 始终以参数为准。同名 Skill 已存在时不会覆盖。references/、"
        "scripts/ 等辅助文件请继续用文件操作工具创建。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill 名称，小写字母、数字和连字符"},
            "skillContext": {"type": "string", "description": "SKILL.md 的完整内容（Frontmatter + 正文）"},
        },
        "required": ["name", "skillContext"],
    },
    handler=_create_skill,
))
