"""论文声明自检测试。

这些测试确保论文生成流程不会把 validation 级证据写成 full、真机或真实模型结论。
"""

from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from scripts.build_thesis import _load_figure_index
from scripts.check_model_control_secrets import DEFAULT_ROOTS
from scripts.check_thesis_claims import check_claims


def test_claim_checker_rejects_full_and_real_robot_claims_without_evidence(
    tmp_path: Path,
) -> None:
    """没有 full/真机 evidence 时，正文不得出现最终封板和真机完成声明。"""

    manuscript = tmp_path / "论文报告_完整版.md"
    manuscript.write_text(
        "\n".join(
            [
                "本文已经达到 PHASE12_FINAL_EVALUATION_ACCEPTED。",
                "真实机械臂实验完成。",
                "BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED。",
            ]
        ),
        encoding="utf-8",
    )

    result = check_claims(paths=[manuscript], evidence_root=tmp_path)

    assert result.passed is False
    assert any("PHASE12_FINAL_EVALUATION_ACCEPTED" in item.message for item in result.failures)
    assert any("真实机械臂实验完成" in item.message for item in result.failures)


def test_claim_checker_allows_explicit_llm_only_design_boundary(tmp_path: Path) -> None:
    """仅大模型章节可写设计和待验证边界，但不能写成真实性能结论。"""

    manuscript = tmp_path / "仅大模型基线设计.md"
    manuscript.write_text(
        "仅大模型方案当前为 fake-provider pipeline test，真实大模型实验待验证。",
        encoding="utf-8",
    )

    result = check_claims(paths=[manuscript], evidence_root=tmp_path)

    assert result.passed is True


def test_secret_scanner_includes_thesis_outputs() -> None:
    """论文正文、构建产物和 LLM-only artifact 必须进入默认 secret 扫描范围。"""

    assert "docs/thesis" in DEFAULT_ROOTS
    assert "thesis" in DEFAULT_ROOTS
    assert "artifacts/thesis_report" in DEFAULT_ROOTS
    assert "artifacts/thesis_baselines" in DEFAULT_ROOTS


def test_thesis_figure_index_loader_normalizes_design_diagrams(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """设计图索引缺省 name 字段时，正文生成器应使用文件名生成可读名称。"""

    generated = tmp_path / "generated.json"
    generated.write_text("[]", encoding="utf-8")
    thesis_index = tmp_path / "thesis" / "figures" / "figure_index.json"
    thesis_index.parent.mkdir(parents=True)
    thesis_index.write_text(
        '{"figures":[{"path":"thesis/figures/svg/system_architecture.svg",'
        '"type":"svg","data_source":"design_diagram"}]}',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    figures = _load_figure_index(generated)

    assert figures == [
        {
            "name": "system_architecture",
            "path": "thesis/figures/svg/system_architecture.svg",
            "type": "svg",
            "data_source": "design_diagram",
        }
    ]
