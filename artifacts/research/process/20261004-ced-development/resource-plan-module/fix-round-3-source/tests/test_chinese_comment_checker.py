"""中文注释审计脚本的回归测试，防止 UI 文案被误判为源码说明。"""

import ast
import subprocess
import sys
from pathlib import Path

import scripts.check_chinese_comments as chinese_comments
from scripts.check_chinese_comments import DEFAULT_AUDIT_PATHS, _audit_file, _collect_files


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _public_python_api_without_chinese_docstrings(root: Path) -> list[str]:
    missing: list[str] = []
    paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            docstring = ast.get_docstring(node, clean=False) or ""
            if not _has_chinese(docstring):
                missing.append(f"{path}:{node.lineno}:{node.name}")
    return missing


def test_model_control_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(
        Path("src/cloud_edge_robot_arm/model_control")
    )

    assert missing == []


def test_auto_mode_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(
        Path("src/cloud_edge_robot_arm/auto_mode")
    )

    assert missing == []


def test_risk_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(Path("src/cloud_edge_robot_arm/risk"))

    assert missing == []


def test_root_utility_public_api_has_chinese_docstrings() -> None:
    missing: list[str] = []
    for path in (
        Path("src/cloud_edge_robot_arm/config.py"),
        Path("src/cloud_edge_robot_arm/errors.py"),
        Path("src/cloud_edge_robot_arm/logging_utils.py"),
    ):
        missing.extend(_public_python_api_without_chinese_docstrings(path))

    assert missing == []


def test_skill_cache_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(
        Path("src/cloud_edge_robot_arm/skill_cache")
    )

    assert missing == []


def test_contracts_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(
        Path("src/cloud_edge_robot_arm/contracts")
    )

    assert missing == []


def test_simulation_workbench_public_api_has_chinese_docstrings() -> None:
    missing = _public_python_api_without_chinese_docstrings(
        Path("src/cloud_edge_robot_arm/simulation_workbench")
    )

    assert missing == []


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


def test_xml_comment_file_needs_leading_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "package.xml"
    path.write_text(
        '<?xml version="1.0"?>\n'
        "<package>\n"
        "  <name>demo</name>\n"
        "  <!-- 局部依赖说明：这里只解释依赖，不说明包职责。 -->\n"
        "</package>\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese


def test_yaml_string_does_not_count_as_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "ci.yml"
    path.write_text("name: 中文流水线\n", encoding="utf-8")

    result = _audit_file(path)

    assert not result.has_chinese


def test_hash_comment_file_needs_leading_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "ci.yml"
    path.write_text(
        "name: ci\n"
        "jobs:\n"
        "  test:\n"
        "    # 局部步骤说明：这里只解释测试步骤，不说明整个流水线职责。\n"
        "    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )

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


def test_markdown_python_fence_requires_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text(
        "# Guide\n\n```python\ndef run() -> None:\n    return None\n```\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert not result.has_chinese
    assert result.explanation_comment_count == 0


def test_markdown_python_fence_chinese_docstring_counts(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text(
        "# Guide\n\n"
        "```python\n"
        '"""示例说明：该代码块只展示仿真调用，不触碰真实硬件。"""\n'
        "def run() -> None:\n"
        "    return None\n"
        "```\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_collects_markdown_only_when_it_contains_supported_code_fence(tmp_path: Path) -> None:
    plain = tmp_path / "plain.md"
    fenced = tmp_path / "fenced.md"
    plain.write_text("# 说明\n\n这里只是中文文档正文。\n", encoding="utf-8")
    fenced.write_text(
        '# 示例\n\n```python\n"""示例说明：该片段只展示只读查询。"""\nprint(\'ok\')\n```\n',
        encoding="utf-8",
    )

    collected = {path.name for path in _collect_files([tmp_path])}

    assert "plain.md" not in collected
    assert "fenced.md" in collected


def test_markdown_empty_language_fence_is_ignored_without_crashing(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\n\n```\nplain text\n```\n", encoding="utf-8")

    collected = _collect_files([tmp_path])
    result = _audit_file(path)

    assert collected == []
    assert not result.has_chinese


def test_collects_dockerfile_for_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "Dockerfile"
    path.write_text("FROM python:3.12-slim\n", encoding="utf-8")

    collected = {item.name for item in _collect_files([tmp_path])}
    result = _audit_file(path)

    assert "Dockerfile" in collected
    assert not result.has_chinese


def test_dockerfile_leading_hash_comment_counts(tmp_path: Path) -> None:
    path = tmp_path / "Dockerfile.console"
    path.write_text(
        "# 容器说明：只启动仿真控制台，不包含真实机械臂驱动。\nFROM python:3.12-slim\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_collects_cmake_lists_for_chinese_explanation(tmp_path: Path) -> None:
    path = tmp_path / "CMakeLists.txt"
    path.write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")

    collected = {item.name for item in _collect_files([tmp_path])}
    result = _audit_file(path)

    assert "CMakeLists.txt" in collected
    assert not result.has_chinese


def test_cmake_leading_hash_comment_counts(tmp_path: Path) -> None:
    path = tmp_path / "CMakeLists.txt"
    path.write_text(
        "# CMake 说明：只声明 ROS 2 仿真接口构建规则，不连接真实控制器。\n"
        "cmake_minimum_required(VERSION 3.20)\n",
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_json_config_uses_neighbor_chinese_note(tmp_path: Path) -> None:
    path = tmp_path / "package.json"
    note = tmp_path / "package.json.zh.md"
    path.write_text('{"scripts": {"test": "vitest run"}}\n', encoding="utf-8")
    note.write_text(
        "# package.json 说明\n\n该配置只声明前端脚本和依赖，不保存密钥。\n",
        encoding="utf-8",
    )

    collected = {item.name for item in _collect_files([tmp_path])}
    result = _audit_file(path)

    assert "package.json" in collected
    assert result.has_chinese


def test_json_config_without_neighbor_note_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "package.json"
    path.write_text('{"scripts": {"test": "vitest run"}}\n', encoding="utf-8")

    result = _audit_file(path)

    assert not result.has_chinese


def test_jsonc_leading_slash_comment_counts(tmp_path: Path) -> None:
    path = tmp_path / "tsconfig.jsonc"
    path.write_text(
        "// 配置说明：这里只约束 TypeScript 编译，不连接运行时服务。\n"
        '{"compilerOptions": {"strict": true}}\n',
        encoding="utf-8",
    )

    result = _audit_file(path)

    assert result.has_chinese


def test_default_paths_collect_dashboard_root_configs() -> None:
    collected = {
        str(path) for path in _collect_files([Path(value) for value in DEFAULT_AUDIT_PATHS])
    }

    assert "dashboard/package.json" in collected
    assert "dashboard/tsconfig.json" in collected
    assert "dashboard/eslint.config.js" in collected
    assert "dashboard/index.html" in collected
    assert "ros2_ws/src/bigsmall_interfaces/CMakeLists.txt" in collected
    assert "configs/models/small_model_catalog.yaml" in collected
    assert "configs/phase1_mock.json" in collected
    assert "contracts/examples/valid/pick_red_cube.json" in collected
    assert "contracts/examples/invalid/unsupported_skill.json" in collected
    assert "simulation/README.md" in collected
    assert "experiments/baselines/phase8_1/run_manifest.json" in collected
    assert "experiments/baselines/phase9/phase9_smoke_mujoco/config.json" in collected


def test_default_paths_cover_all_tracked_code_files() -> None:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    expected: list[Path] = []
    for name in tracked:
        path = Path(name)
        # 覆盖说明：文档中的可执行代码块也要审计，只排除生成的验收 artifacts。
        if path.parts and path.parts[0] == "artifacts":
            continue
        if (
            path.parts
            and path.parts[0] == "dashboard"
            and len(path.parts) > 1
            and path.parts[1] in {"node_modules", "dist"}
        ):
            continue
        if chinese_comments._is_audited_file(path):
            expected.append(path)

    collected = set(_collect_files([Path(value) for value in DEFAULT_AUDIT_PATHS]))
    missing = [path for path in expected if path not in collected]

    assert missing == []
