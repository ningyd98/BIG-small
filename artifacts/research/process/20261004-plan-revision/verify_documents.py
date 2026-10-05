"""Verify the plan-revision documents; no product or experiment execution."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).with_name("verification.json")
SPEC = "docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md"
PLAN = "docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md"
DOCUMENTS = [
    "README.md",
    "docs/plan.md",
    "docs/roadmap.md",
    "docs/current_authoritative_status.md",
    "docs/superpowers/specs/2026-10-03-rgbd-evidence-research-design.md",
    "docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md",
    SPEC,
    PLAN,
    "docs/research/process/README.md",
    "docs/research/process/phase_progress.md",
    "docs/research/process/validation_matrix.md",
    "docs/research/process/handover.md",
    "docs/research/process/decisions_and_risks.md",
    "docs/research/process/change_record.md",
    "docs/research/process/execution_log.md",
    "docs/research/process/continuation_20261004.md",
    "artifacts/research/process/20261004-plan-revision/plan-update.md",
]


def heading_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    duplicates: dict[str, int] = {}
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if fenced:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        label = match[1].lower().replace("`", "").replace("*", "")
        slug = "".join(
            c for c in label
            if c in "- _" or unicodedata.category(c)[0] in "LN"
        ).replace(" ", "-")
        count = duplicates.get(slug, 0)
        duplicates[slug] = count + 1
        ids.add(slug if count == 0 else f"{slug}-{count}")
    return ids


errors: list[str] = []
link_count = 0
anchor_count = 0
hashes: dict[str, str] = {}
texts: dict[str, str] = {}
for relative in DOCUMENTS:
    path = ROOT / relative
    if not path.is_file():
        errors.append(f"Missing document: {relative}")
        continue
    data = path.read_bytes()
    hashes[relative] = hashlib.sha256(data).hexdigest()
    body = data.decode("utf-8")
    texts[relative] = body
    for match in re.finditer(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", body):
        target = match[1].strip("<>")
        if "://" in target or target.startswith("mailto:"):
            continue
        filename, _, anchor = target.partition("#")
        dest = (path.parent / unquote(filename)).resolve() if filename else path
        link_count += 1
        if not dest.exists():
            errors.append(f"Missing link: {relative} -> {target}")
        elif anchor:
            anchor_count += 1
            if dest.is_file() and dest.suffix == ".md" and unquote(anchor) not in heading_ids(dest):
                errors.append(f"Missing anchor: {relative} -> {target}")

spec = texts.get(SPEC, "")
plan = texts.get(PLAN, "")
checks: dict[str, bool] = {}
checks["new_tasks_remain_unchecked"] = bool(re.search(r"^- \[ \]", plan, re.M)) and not bool(re.search(r"^- \[[xX]\]", plan, re.M))
checks["edge_model_choice_deferred"] = "边缘模型型号暂不固定" in spec and "当前不锁Qwen3.5-4B" in plan
checks["current_research_gate_preserved"] = all(term in plan for term in ("T8为IN_PROGRESS", "5成功、静态4/40", "NO_FEASIBLE_BASELINE"))
checks["samples_preserved"] = all(term in spec for term in ("100/1000/10000", "80/5/5/10", "600/1200/1800/2400", "恢复200", "300域外组×3训练seed", "基础先导120", "功效先导另120"))
checks["quantitative_targets_preserved"] = all(term in spec for term in ("P90≤10mm", "成功≥90%", "减少≥30%", "下界>−3", "上界≤+1", "减少≥25%", "P95减少≥15%", "减少≥50%", "绝对≤2%", "拒绝≤5%", "成功≥80%", "提高≥5"))
checks["statistical_rules_preserved"] = all(term in spec for term in ("α=0.05", "功效0.8", "Holm", "bootstrap≥10000", "Wilson", "区间排除0", "[120,600]", "Rcap=60"))
checks["freeze_dependencies_decoupled"] = all(term in plan for term in ("不等待T13在线恢复", "不等待T11统一适配", "不得用于视觉开发或阈值选择", "受控的版本变更回归"))
checks["documentation_scope_explicit"] = "此次交付只更新设计、计划和过程文档" in spec and "新三层路径尚未实现" in plan

# The dotted model-change regression is optional, so exclude it from required edges.
graph_block = plan.split("```mermaid", 1)[-1].split("```", 1)[0]
graph: dict[str, list[str]] = {}
for line in graph_block.splitlines():
    match = re.match(r"\s*(\w+)(?:\[[^\]]*\])?\s*-->\s*(\w+)", line)
    if match:
        graph.setdefault(match[1], []).append(match[2])
visiting: set[str] = set()
visited: set[str] = set()


def visit(node: str) -> bool:
    if node in visiting:
        return False
    if node in visited:
        return True
    visiting.add(node)
    if not all(visit(child) for child in graph.get(node, [])):
        return False
    visiting.remove(node)
    visited.add(node)
    return True


checks["required_task_graph_acyclic"] = len(graph) >= 10 and all(visit(node) for node in graph)
source_requirements = {
    "src/cloud_edge_robot_arm/contracts/models.py": ("class RobotState",),
    "src/cloud_edge_robot_arm/edge/evidence/conditions.py": (
        "class ConditionVerdict", "class OnlineEvidenceSnapshot", "def evaluate_conditions", "visual_facts",
    ),
    "src/cloud_edge_robot_arm/cloud/replanning/apply_service.py": ("class ReplanApplyService",),
    "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py": ("def get_state",),
}
checks["reused_source_interfaces_exist"] = all(
    (ROOT / path).is_file() and all(term in (ROOT / path).read_text(encoding="utf-8") for term in terms)
    for path, terms in source_requirements.items()
)
errors.extend(name for name, passed in checks.items() if not passed)
diff = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True, check=False)
if diff.returncode:
    errors.append("git diff --check failed")
result = {
    "scope": "documentation-only; not product or research acceptance",
    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "synchronized_document_count": 16,
    "checked_markdown_document_count": len(DOCUMENTS),
    "local_link_count": link_count,
    "anchor_count": anchor_count,
    "checks": checks,
    "document_sha256": hashes,
    "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "git_diff_check": {"exit_code": diff.returncode, "stdout": diff.stdout, "stderr": diff.stderr},
    "errors": errors,
    "passed": not errors,
    "exit_code": 1 if errors else 0,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ("checked_markdown_document_count", "local_link_count", "anchor_count", "checks", "errors", "passed", "exit_code")}, ensure_ascii=False))
raise SystemExit(result["exit_code"])
