from pathlib import Path

from scripts.check_chinese_comments import _audit_file


def test_typescript_ui_text_does_not_count_as_chinese_comment(tmp_path: Path) -> None:
    path = tmp_path / "Widget.tsx"
    path.write_text(
        "export function Widget() {\n"
        '  return <button aria-label="保存配置">保存配置</button>;\n'
        "}\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese


def test_typescript_comment_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "Widget.tsx"
    path.write_text(
        "// 前端组件说明：这里只展示配置入口，不保存敏感信息。\n"
        "export function Widget() {\n"
        '  return <button aria-label="Save">Save</button>;\n'
        "}\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_python_string_does_not_count_as_chinese_comment(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text('message = "运行成功"\n', encoding="utf-8")

    result = _audit_file(path)

    assert not result.has_chinese


def test_python_docstring_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        '"""运行时说明：该模块只检查仿真任务，不触碰真实硬件。"""\n'
        "\n"
        "def run() -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese
