from types import SimpleNamespace

import pytest

from core.tools import files


def configure(root, *, dangerous=False, max_read=1_000):
    files.configure(
        SimpleNamespace(
            file_max_read_chars=max_read,
            files_root=str(root),
            files_allow_dangerous=dangerous,
        )
    )


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    configure(root)
    return root, outside


def test_create_list_read_and_type(workspace):
    root, _ = workspace

    assert "已创建" in files._create_file({"directory": str(root), "filename": "a.txt"})
    assert files._read_file({"path": str(root / "a.txt")}) == "(空文件)"

    listing = files._list_dir({"path": str(root)})
    assert "[F] a.txt" in listing

    assert files._get_file_type({"path": str(root)}) == "目录"
    assert "扩展名: .txt" in files._get_file_type({"path": str(root / "a.txt")})
    assert files._get_file_type({"path": str(root / "missing.txt")}) == "路径不存在"


def test_read_truncates_long_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    configure(root, max_read=1_000)
    (root / "long.txt").write_text("x" * 1_500, encoding="utf-8")

    text = files._read_file({"path": str(root / "long.txt")})

    assert len(text) < 1_500
    assert "已截断" in text


def test_paths_outside_root_are_blocked(workspace):
    root, outside = workspace

    with pytest.raises(ValueError, match="超出允许范围"):
        files._read_file({"path": str(outside / "secret.txt")})

    with pytest.raises(ValueError, match="超出允许范围"):
        files._read_file({"path": str(root / ".." / "outside" / "secret.txt")})

    with pytest.raises(ValueError, match="超出允许范围"):
        files._create_file({"directory": str(root), "filename": "../escape.txt"})


def test_dangerous_operations_disabled_by_default(workspace):
    root, _ = workspace
    path = root / "a.txt"
    path.write_text("old", encoding="utf-8")

    with pytest.raises(ValueError, match="覆盖写入.*已被禁用"):
        files._edit_file({"path": str(path), "content": "new"})
    with pytest.raises(ValueError, match="删除文件.*已被禁用"):
        files._delete_file({"path": str(path)})
    with pytest.raises(ValueError, match="删除目录.*已被禁用"):
        files._delete_dir({"path": str(root)})

    assert path.read_text(encoding="utf-8") == "old"


def test_dangerous_operations_can_be_enabled(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    configure(root, dangerous=True)
    path = root / "a.txt"
    path.write_text("old", encoding="utf-8")

    files._edit_file({"path": str(path), "content": "new"})
    assert path.read_text(encoding="utf-8") == "new"

    files._delete_file({"path": str(path)})
    assert not path.exists()


def test_rename_within_root_and_overwrite_gate(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    configure(root)
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")

    files._rename({"path": str(root / "a.txt"), "new_name": "c.txt"})
    assert (root / "c.txt").exists()

    with pytest.raises(ValueError, match="覆盖重命名.*已被禁用"):
        files._rename({"path": str(root / "c.txt"), "new_name": "b.txt"})
    assert (root / "b.txt").read_text(encoding="utf-8") == "b"

    files._rename({"path": str(root / "c.txt"), "new_name": "d.txt"})
    assert (root / "d.txt").exists()


def test_rename_outside_root_is_blocked(workspace):
    root, outside = workspace
    (root / "a.txt").write_text("a", encoding="utf-8")

    with pytest.raises(ValueError, match="超出允许范围"):
        files._rename(
            {"path": str(root / "a.txt"), "new_name": str(outside / "a.txt")}
        )


def test_configure_without_root_uses_project_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    files.configure(
        SimpleNamespace(
            file_max_read_chars=1_000,
            files_root="",
            files_allow_dangerous=False,
        ),
        project_root=str(root),
    )

    assert "已创建" in files._create_file({"directory": str(root), "filename": "a.txt"})
    with pytest.raises(ValueError, match="超出允许范围"):
        files._read_file({"path": str(tmp_path / "outside.txt")})
