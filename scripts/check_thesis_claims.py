#!/usr/bin/env python
"""检查论文正文是否存在越级验收、真机或真实模型夸大声明。"""

from __future__ import annotations

import argparse
import json
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
