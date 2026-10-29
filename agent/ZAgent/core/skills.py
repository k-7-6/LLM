"""技能发现：启动时扫描项目根目录下的 .agents/skills。

每个 Skill 子目录至少包含一个 SKILL.md，开头用 YAML Frontmatter 声明
name 和 description。初始化阶段只读取这两个字段，不读取正文。
"""

import logging
import os
from dataclasses import dataclass

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(".agents", "skills")
SKILL_FILE = "SKILL.md"
DELIMITER = "---"
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class Skill:
    """一个技能的元信息。正文留到使用时按 path 读取。"""
    name: str
    description: str
    path: str
    root: str = ""


def discover(project_root: str | None = None) -> list[Skill]:
    """扫描 <项目根>/.agents/skills，返回所有有效的技能元信息。

    无效的技能（缺少 SKILL.md、Frontmatter 不合法等）会被跳过并记录警告，
    不影响其他技能加载。
    """
    root = os.path.abspath(project_root or os.getcwd())
    base = os.path.join(root, SKILLS_DIR)
    if not os.path.isdir(base):
        logger.warning("未找到技能目录: %s（项目根: %s）", base, root)
        return []

    skills: list[Skill] = []
    seen: set[str] = set()
    for entry in sorted(os.listdir(base)):
        skill_dir = os.path.join(base, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_file = os.path.join(skill_dir, SKILL_FILE)
        if not os.path.isfile(skill_file):
            logger.warning("技能目录 %s 缺少 %s，已跳过", skill_dir, SKILL_FILE)
            continue
        try:
            skill = _load(skill_file, root)
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
            logger.warning("技能 %s 加载失败，已跳过：%s", skill_file, exc)
            continue
        if skill.name in seen:
            logger.warning("技能名称 %s 重复，已跳过 %s", skill.name, skill_file)
            continue
        seen.add(skill.name)
        skills.append(skill)
    return skills


def _load(path: str, root: str) -> Skill:
    meta = _read_frontmatter(path)
    if not isinstance(meta, dict):
        raise ValueError("Frontmatter 必须是 YAML 映射")
    name = _required(meta, "name")
    description = _required(meta, "description")
    return Skill(name=name, description=description, path=path, root=root)


def _required(meta: dict, key: str) -> str:
    value = meta.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少必需的 {key} 字段")
    return value.strip()


def _read_frontmatter(path: str) -> dict:
    """二进制逐行读到结束分隔符为止，正文不会被解码或载入。"""
    with open(path, "rb") as f:
        first = f.readline()
        if first.startswith(BOM):
            first = first[len(BOM):]
        if not _is_delimiter(first):
            raise ValueError("开头缺少 YAML Frontmatter")
        header = []
        for line in f:
            if _is_delimiter(line):
                return yaml.safe_load(b"".join(header))
            header.append(line)
    raise ValueError("YAML Frontmatter 未闭合")


def _is_delimiter(line: bytes) -> bool:
    # 容忍被转义的 Markdown 分隔符（\---），常见于复制粘贴产生的文件。
    return line.strip().removeprefix(b"\\") == DELIMITER.encode()


def system_prompt(skills: list[Skill]) -> str:
    """把技能列表整理成 System Prompt；没有技能时返回空串。"""
    if not skills:
        return ""
    lines = ["You have access to the following skills:"]
    lines += [f"- '{skill.name}': {skill.description}" for skill in skills]
    lines.append(
        "Use the 'loadSkill' tool to load the full instructions of a skill when needed. "
        "You can also load additional files referenced by a skill by passing their 'filename'."
    )
    return "\n".join(lines)


class AmbiguousResource(ValueError):
    """只给文件名却匹配到多个文件，需要调用方指定具体路径。"""

    def __init__(self, filename: str, candidates: list[str]):
        self.filename = filename
        self.candidates = candidates
        super().__init__(f"找到多个名为 {filename} 的文件")


def read(skill: Skill, filename: str | None = None) -> str:
    """读取 SKILL.md 或技能目录内的附加文件。

    filename 省略时返回 SKILL.md 全文；否则只读取该文件，支持绝对路径、
    相对技能目录、相对项目根目录，纯文件名会在技能目录内递归查找。
    所有读取都限制在技能目录内部。
    """
    if not filename:
        return _read_text(skill.path)
    return _read_text(_resolve(skill, filename))


def _resolve(skill: Skill, filename: str) -> str:
    base = os.path.realpath(os.path.dirname(os.path.abspath(skill.path)))

    if os.path.isabs(filename):
        target = os.path.realpath(filename)
        if not _inside(base, target):
            raise ValueError(f"只能读取技能目录内的文件: {filename}")
        if os.path.isfile(target):
            return target
        raise ValueError(f"文件不存在: {filename}")

    # 精确路径优先：先按技能目录解析，再按项目根目录解析。
    roots = [base]
    if skill.root:
        roots.append(os.path.realpath(skill.root))
    for root in roots:
        target = os.path.realpath(os.path.join(root, filename))
        if _inside(base, target) and os.path.isfile(target):
            return target

    # 只给文件名时，在技能目录内递归查找。
    if os.path.basename(filename) == filename:
        matches = _search(base, filename)
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise AmbiguousResource(
                filename,
                [os.path.relpath(path, base).replace(os.sep, "/") for path in matches],
            )
    raise ValueError(f"文件不存在或不在技能目录内: {filename}")


def _search(base: str, filename: str) -> list[str]:
    wanted = os.path.normcase(filename)
    matches = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            if os.path.normcase(name) != wanted:
                continue
            target = os.path.realpath(os.path.join(dirpath, name))
            if _inside(base, target) and os.path.isfile(target):
                matches.append(target)
    return sorted(matches)


def _inside(base: str, target: str) -> bool:
    try:
        return os.path.commonpath([base, target]) == base
    except ValueError:  # Windows 下目标位于不同盘符
        return False


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return f.read() or "（空文件）"
