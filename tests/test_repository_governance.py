"""仓库回归回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path


def test_check_docs_reports_missing_markdown_link(tmp_path: Path) -> None:
    from scripts.check_docs import check_repository_docs

    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")
    (tmp_path / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")

    result = check_repository_docs(tmp_path)

    assert result.ok is False
    assert any(item.check_id == "markdown_link_exists" for item in result.failures)


def test_check_docs_reports_sensitive_absolute_path(tmp_path: Path) -> None:
    from scripts.check_docs import check_repository_docs

    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(
        "local path: /home/ningyd/private/controller.yaml\n",
        encoding="utf-8",
    )

    result = check_repository_docs(tmp_path)

    assert result.ok is False
    assert any(item.check_id == "sensitive_content" for item in result.failures)


def test_verify_project_ci_profile_is_ci_safe() -> None:
    from scripts.verify_project import profile_commands

    commands = profile_commands("ci")
    joined = "\n".join(" ".join(command.argv) for command in commands)

    assert "scripts/check_docs.py" in joined
    assert "scripts/check_chinese_comments.py" in joined
    assert "scripts/check_model_control_secrets.py" in joined
    assert "scripts/verify_phase10_0.py" in joined
    assert "scripts/verify_phase10_1.py" in joined
    assert "scripts/verify_phase10_2a.py" in joined
    assert "--skip-runtime" in joined
    assert "artifacts/project_verification/phase10/phase10_0" in joined
    assert "artifacts/project_verification/phase10/phase10_1" in joined
    assert "artifacts/project_verification/phase10/phase10_2a" in joined
    assert "verify_phase10_moveit_dry_run.py" not in joined
    assert "run_phase10_acceptance_level.py" not in joined
    assert "run_phase9_2_cross_backend.py" not in joined


def test_testing_docs_describe_current_ci_quality_gates() -> None:
    docs = Path("docs/testing.md").read_text(encoding="utf-8")

    assert "scripts/verify_project.py --profile ci" in docs
    assert "scripts/check_chinese_comments.py" in docs
    assert "scripts/check_model_control_secrets.py" in docs
    assert "Phase 12 smoke" in docs
    assert "Phase 3-6 验证脚本" not in docs
