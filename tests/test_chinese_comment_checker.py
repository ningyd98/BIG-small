"""中文注释审计脚本的回归测试，防止 UI 文案被误判为源码说明。"""

from pathlib import Path

from scripts.check_chinese_comments import _audit_file, _collect_files


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


def test_collects_script_config_and_ros_interface_files(tmp_path: Path) -> None:
    expected_names = {
        "run.sh",
        "ci.yml",
        "package.xml",
        "pyproject.toml",
        "style.css",
        "index.html",
        "setup.js",
        "Move.action",
        "Fault.msg",
        "Reset.srv",
    }
    for name in expected_names:
        path = tmp_path / name
        path.write_text("# 临时测试文件\n", encoding="utf-8")

    collected = {path.name for path in _collect_files([tmp_path])}

    assert expected_names <= collected


def test_hash_comment_file_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "run.sh"
    path.write_text(
        "#!/usr/bin/env bash\n# 脚本说明：这里只做环境检查，不启动真实硬件。\nset -euo pipefail\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_xml_comment_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "package.xml"
    path.write_text(
        "<!-- ROS 包说明：只声明仿真桥接依赖，不授权硬件运动。 -->\n"
        "<package><name>demo</name></package>\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_yaml_string_does_not_count_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "ci.yml"
    path.write_text("name: 中文流水线\n", encoding="utf-8")

    result = _audit_file(path)

    assert not result.has_chinese
