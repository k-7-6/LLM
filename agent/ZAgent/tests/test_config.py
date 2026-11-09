import os
import textwrap

from core.config import load_config


def write_config(tmp_path, body: str) -> str:
    path = tmp_path / "config.ini"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_defaults_for_new_safety_options(tmp_path):
    config = load_config(write_config(tmp_path, "[llm]\napi_key = k\n"))

    assert config.max_steps == 30
    assert config.loop_timeout == 600.0
    assert config.skill_max_load_chars == 20_000
    assert config.file_max_read_chars == 200_000
    assert config.files_root == ""
    assert config.files_allow_dangerous is False


def test_agent_and_files_options_are_parsed(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    config = load_config(
        write_config(
            tmp_path,
            """
            [agent]
            max_steps = 0
            loop_timeout = 15
            [files]
            root = workspace
            allow_dangerous_ops = yes
            max_read_chars = 1234
            [skills]
            max_load_chars = 4321
            """,
        )
    )

    assert config.max_steps == 0
    assert config.loop_timeout == 15.0
    assert config.files_root == str(root)
    assert config.files_allow_dangerous is True
    assert config.file_max_read_chars == 1234
    assert config.skill_max_load_chars == 4321


def test_relative_files_root_is_relative_to_config_file(tmp_path):
    config = load_config(
        write_config(tmp_path, "[files]\nroot = data/files\n")
    )

    assert config.files_root == os.path.normpath(
        os.path.join(str(tmp_path), "data", "files")
    )


def test_boolean_accepts_common_truthy_values(tmp_path):
    for raw, expected in (
        ("true", True), ("YES", True), ("1", True), ("on", True),
        ("false", False), ("0", False), ("maybe", False),
    ):
        config = load_config(
            write_config(
                tmp_path, f"[files]\nallow_dangerous_ops = {raw}\n"
            )
        )
        assert config.files_allow_dangerous is expected


def test_invalid_numbers_fall_back_to_defaults(tmp_path):
    config = load_config(
        write_config(
            tmp_path,
            """
            [agent]
            max_steps = many
            loop_timeout =
            [files]
            max_read_chars = -5
            """,
        )
    )

    assert config.max_steps == 30
    assert config.loop_timeout == 600.0
    assert config.file_max_read_chars == 1_000  # 低于下限时被夹紧
