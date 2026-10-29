from ..skills import AmbiguousResource, Skill, read
from .registry import Tool, register

# 启动时由 configure 注入已发现的技能，handler 通过技能名查找。
_skills: dict[str, Skill] = {}


def configure(skills: list[Skill]) -> None:
    _skills.clear()
    _skills.update({skill.name: skill for skill in skills})


def _load_skill(raw: dict) -> str:
    name = str(raw.get("name", "")).strip()
    skill = _skills.get(name)
    if skill is None:
        available = "、".join(_skills) or "（无）"
        return f"错误: 未找到技能 '{name}'，可用技能: {available}"

    filename = str(raw.get("filename", "") or "").strip() or None
    try:
        return read(skill, filename)
    except AmbiguousResource as exc:
        lines = [f"错误: 技能 '{name}' 中有多个名为 '{exc.filename}' 的文件，"
                 "请用 filename 指定其中一个："]
        lines += [f"- {candidate}" for candidate in exc.candidates]
        return "\n".join(lines)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return f"错误: {exc}"


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
