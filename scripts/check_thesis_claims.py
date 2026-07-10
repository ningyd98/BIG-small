#!/usr/bin/env python
"""检查论文正文是否存在越级验收、真机或真实模型夸大声明。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClaimFailure:
    """单条声明检查失败。"""

    path: str
    message: str


@dataclass(frozen=True)
class ClaimCheckResult:
    """声明检查汇总。"""

    passed: bool
    failures: list[ClaimFailure]


FORBIDDEN_PATTERNS = [
    "BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED",
    "真实机械臂实验完成",
    "真机实验已完成",
    "PHASE12_FINAL_EVALUATION_ACCEPTED",
    "PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED",
    "BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED",
    "本地模型运行已验收",
    "Ollama runtime 已验收",
    "fake provider 证明了大模型效果",
    "Mock 模型实验表明",
    "规则规划器代表大模型",
    "大模型直接控制真实机械臂",
    "大模型控制命令已发送到真机",
    "真实模型对比实验已完成",
]

REAL_LLM_RESULT_PATTERNS = [
    "仅大模型方案实验结果表明",
    "真实大模型实验表明",
    "大模型方案成功率为",
    "大模型方案平均时延为",
    "大模型方案成本为",
]

SAFE_BOUNDARY_WORDS = ["fake", "synthetic", "pipeline test", "设计值", "待验证", "尚未"]
PERFORMANCE_WORDS = ["优于", "提升", "降低百分比", "显著降低", "显著提升", "更好", "更差"]
REQUIRED_BOUNDARIES = {
    "runtime completed": "466",
    "blocked before runtime": "74",
    "synthetic sample": "0",
}


def check_claims(*, paths: list[Path], evidence_root: Path) -> ClaimCheckResult:
    """扫描给定论文文件，返回越界声明。"""

    has_runtime = _has_llm_runtime_accepted(evidence_root)
    failures: list[ClaimFailure] = []
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                failures.append(ClaimFailure(str(path), f"forbidden claim: {pattern}"))
        if not has_runtime:
            for pattern in REAL_LLM_RESULT_PATTERNS:
                if pattern in text and not _line_has_safe_boundary(text, pattern):
                    failures.append(
                        ClaimFailure(
                            str(path), f"real LLM result claim without evidence: {pattern}"
                        )
                    )
        failures.extend(_check_runtime_count_semantics(path, text))
        failures.extend(_check_fake_provider_semantics(path, text, has_runtime))
        failures.extend(_check_required_boundary_presence(path, text))
    failures.extend(_check_traceability(evidence_root))
    return ClaimCheckResult(passed=not failures, failures=failures)


def _has_llm_runtime_accepted(root: Path) -> bool:
    candidates = [
        root / "artifacts/thesis_baselines/llm_only/verification/llm_only_verification.json",
        root / "verification/llm_only_verification.json",
        root / "llm_only/verification/llm_only_verification.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("runtime_status") == "LLM_ONLY_BASELINE_RUNTIME_ACCEPTED":
            return True
    return False


def _line_has_safe_boundary(text: str, pattern: str) -> bool:
    for line in text.splitlines():
        if pattern in line and any(word in line for word in SAFE_BOUNDARY_WORDS):
            return True
    return False


def _check_runtime_count_semantics(path: Path, text: str) -> list[ClaimFailure]:
    failures: list[ClaimFailure] = []
    suspicious = [
        r"540\s*(条|个|rows?|records?)?\s*(真实运行|runtime[- ]?completed|运行完成|有效运行)",
        r"(真实运行|runtime[- ]?completed|运行完成|有效运行)\s*(为|=|:|：)?\s*540",
        r"blocked before runtime\s*[=：:]\s*74.{0,20}(计入|纳入).{0,20}(性能|runtime)",
    ]
    for pattern in suspicious:
        if re.search(pattern, text, re.I):
            failures.append(ClaimFailure(str(path), "runtime count semantics are overstated"))
    return failures


def _check_fake_provider_semantics(
    path: Path,
    text: str,
    has_runtime: bool,
) -> list[ClaimFailure]:
    failures: list[ClaimFailure] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "fake" not in line.lower() and "FAKE_PROVIDER_PIPELINE_TEST" not in line:
            continue
        if any(word in line for word in PERFORMANCE_WORDS):
            failures.append(
                ClaimFailure(str(path), f"fake provider performance claim on line {line_no}")
            )
    if not has_runtime and re.search(r"大模型.*(优于|提升|降低|成功率为|平均时延为|成本为)", text):
        if not any(
            boundary in text for boundary in ["NOT_AVAILABLE", "待验证", "尚未形成", "pipeline"]
        ):
            failures.append(
                ClaimFailure(
                    str(path), "real model performance conclusion without runtime evidence"
                )
            )
    return failures


def _check_required_boundary_presence(path: Path, text: str) -> list[ClaimFailure]:
    if path.name not in {"论文报告_完整版.md", "论文报告.md"}:
        return []
    if "# 第九章" not in text and "runtime completed" not in text:
        return []
    failures: list[ClaimFailure] = []
    for label, value in REQUIRED_BOUNDARIES.items():
        if label not in text or value not in text:
            failures.append(
                ClaimFailure(str(path), f"missing required boundary count: {label}={value}")
            )
    if "full profile 尚未" not in text and "full profile remains future work" not in text:
        failures.append(ClaimFailure(str(path), "missing full profile boundary"))
    return failures


def _check_traceability(root: Path) -> list[ClaimFailure]:
    failures: list[ClaimFailure] = []
    claim_path = root / "thesis/generated/claim_evidence.json"
    if not claim_path.exists():
        return []
    try:
        claims = json.loads(claim_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [ClaimFailure(str(claim_path), "claim evidence matrix is not valid JSON")]
    required_metrics = {
        "runtime_completion_count": "466",
        "blocked_before_runtime_count": "74",
        "synthetic_sample_count": "0",
        "real_controller_contacted": "False",
        "hardware_motion_observed": "False",
    }
    for metric, value in required_metrics.items():
        if not any(
            str(row.get("指标")) == metric and str(row.get("数值")) == value for row in claims
        ):
            failures.append(
                ClaimFailure(
                    str(claim_path), f"missing traceable quantitative claim: {metric}={value}"
                )
            )
    return failures


def _default_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for rel in ["docs/thesis", "thesis", "artifacts/thesis_report"]:
        base = root / rel
        if base.exists():
            paths.extend(item for item in base.rglob("*") if item.suffix in {".md", ".tex"})
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Check thesis claims against evidence boundary.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    root = args.root.resolve()
    paths = [Path(item) for item in args.paths] or _default_paths(root)
    paths = [path if path.is_absolute() else root / path for path in paths]
    result = check_claims(paths=paths, evidence_root=root)
    if result.failures:
        for failure in result.failures:
            print(f"{failure.path}: {failure.message}")
        return 1
    print("thesis claim scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
