from types import SimpleNamespace

from core.tools import skill


def configure(root, *, max_load=20_000):
    skill.configure(
        [],
        project_root=str(root),
        config=SimpleNamespace(
            skills_dir=".agents/skills",
            skill_file="SKILL.md",
            skill_description_length=200,
            skill_max_load_chars=max_load,
        ),
    )


def test_create_skill_writes_skill_md(tmp_path):
    configure(tmp_path)

    result = skill._create_skill(
        {
            "name": "weather-report",
            "skillContext": "---\ndescription: 查询天气\n---\n\n按城市查询天气。",
        }
    )

    path = tmp_path / ".agents" / "skills" / "weather-report" / "SKILL.md"
    assert "已创建" in result
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "name: weather-report" in content
    assert "description: 查询天气" in content
    assert "按城市查询天气。" in content


def test_create_skill_derives_description_from_body(tmp_path):
    configure(tmp_path)

    result = skill._create_skill(
        {"name": "daily-note", "skillContext": "# 每日记录\n\n记录今天的事情。"}
    )

    assert "已创建" in result
    content = (
        tmp_path / ".agents" / "skills" / "daily-note" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "description: 每日记录" in content


def test_create_skill_rejects_duplicates_and_invalid_names(tmp_path):
    configure(tmp_path)
    context = {"name": "keep-me", "skillContext": "正文"}

    assert "已创建" in skill._create_skill(context)
    path = tmp_path / ".agents" / "skills" / "keep-me" / "SKILL.md"
    original = path.read_text(encoding="utf-8")

    result = skill._create_skill(
        {"name": "keep-me", "skillContext": "新正文"}
    )
    assert "已存在" in result
    assert path.read_text(encoding="utf-8") == original

    assert "小写字母" in skill._create_skill(
        {"name": "Bad Name", "skillContext": "正文"}
    )
    assert "不能为空" in skill._create_skill({"name": "ok", "skillContext": "  "})
    assert "不能为空" in skill._create_skill({"name": " ", "skillContext": "正文"})


def test_load_skill_returns_content_and_reports_missing(tmp_path):
    configure(tmp_path)
    skill._create_skill(
        {
            "name": "greeting",
            "skillContext": "---\ndescription: 打招呼\n---\n\n说你好。",
        }
    )

    text = skill._load_skill({"name": "greeting"})
    assert "说你好。" in text

    missing = skill._load_skill({"name": "nope"})
    assert "错误: 未找到技能 'nope'" in missing
    assert "greeting" in missing


def test_load_skill_truncates_to_configured_limit(tmp_path):
    configure(tmp_path, max_load=1_000)
    skill._create_skill(
        {"name": "long-skill", "skillContext": "y" * 3_000}
    )

    text = skill._load_skill({"name": "long-skill"})

    assert len(text) < 3_000
    assert "已截断到 1,000 字符" in text


def test_load_skill_rejects_files_outside_skill_dir(tmp_path):
    configure(tmp_path)
    skill._create_skill(
        {"name": "safe", "skillContext": "正文"}
    )
    secret = tmp_path / "secret.md"
    secret.write_text("top secret", encoding="utf-8")

    result = skill._load_skill({"name": "safe", "filename": str(secret)})

    assert result.startswith("错误:")
    assert "top secret" not in result
