"""中文注释审计脚本的回归测试，防止 UI 文案被误判为源码说明。"""

import subprocess
import sys
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


def test_english_only_comment_is_not_accepted_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        '"""Runtime helper that only documents behavior in English."""\n',
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese
    assert result.explanation_comment_count == 1


def test_cli_reports_english_only_comments_separately(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text('"""English-only module comment."""\n', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "scripts/check_chinese_comments.py", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "只有非中文说明的文件" in completed.stdout
    assert str(path) in completed.stdout


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


def test_python_requires_module_level_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        "def run() -> None:\n"
        '    """函数说明：这里只解释局部函数，不能替代模块职责。"""\n'
        "    return None\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese


def test_collects_script_config_and_ros_interface_files(tmp_path: Path) -> None:
    expected_names = {
        ".env.example",
        ".gitignore",
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


def test_collects_extensionless_python_entrypoint(tmp_path: Path) -> None:
    path = tmp_path / "console_entry"
    path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    collected = {item.name for item in _collect_files([tmp_path])}

    assert "console_entry" in collected


def test_hash_comment_file_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "run.sh"
    path.write_text(
        "#!/usr/bin/env bash\n# 脚本说明：这里只做环境检查，不启动真实硬件。\nset -euo pipefail\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_dotfile_hash_comment_counts_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text(
        "# 配置说明：示例环境变量不保存真实密钥。\nAPP_ENV=development\n",
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


def test_placeholder_chinese_comment_is_not_accepted_as_suitable_explanation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "placeholder.py"
    path.write_text(
        '"""simulation 模块实现，补充该层业务逻辑的中文说明。"""\n',
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese


def test_typescript_needs_file_level_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "Widget.tsx"
    path.write_text(
        "import { Button } from 'antd';\n"
        "\n"
        "export function Widget() {\n"
        "  // 组件内部说明：这里只解释局部按钮，不说明文件职责。\n"
        "  return <Button>Run</Button>;\n"
        "}\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese
