"""本轮文档检查；仅标准库、文件读取和只读 Git，不导入产品代码。"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
TARGETS = [
    "docs/plan.md",
    "docs/开题报告_集成电路工程_20261024.md",
    "docs/README.md",
]
sha = lambda value: hashlib.sha256(value).hexdigest()
manifest = json.loads((ROUND / "input-manifest.json").read_text())
plan = json.loads((ROUND / "plan.json").read_text())
checks = []
def record(name, passed, detail):
    checks.append({"name": name, "passed": bool(passed), "detail": detail})

record("plan_hash", sha((ROUND / "plan.md").read_bytes()) == plan["plan_markdown_sha256"], "Astra plan.md unchanged")
record("manifest_hash", sha((ROUND / "input-manifest.json").read_bytes()) == plan["input_manifest_sha256"], "Astra input manifest unchanged")
for item in manifest["inputs"]:
    frozen = ROUND / item["snapshot"]
    record("original:" + item["path"], sha(frozen.read_bytes()) == item["sha256"], item["snapshot"])
    if item["path"] not in TARGETS:
        record("unchanged_input:" + item["path"], sha((ROOT / item["path"]).read_bytes()) == item["sha256"], "read-only input unchanged")

old_plan = (ROUND / "inputs/original/docs/plan.md").read_bytes()
new_plan = (ROOT / TARGETS[0]).read_bytes()
separator = "## 历史原文（逐字保留；不作为现行模型、排期与交付定位）\n\n".encode()
history = new_plan.split(separator, 1)
record("historical_plan_exact", len(history) == 2 and history[1] == old_plan, {"bytes": len(old_plan), "sha256": sha(old_plan)})

after = []
for name in TARGETS:
    path = ROOT / name
    body = path.read_text()
    before = next(i for i in manifest["inputs"] if i["path"] == name)
    after.append({"path": name, "before_sha256": before["sha256"], "after_sha256": sha(path.read_bytes()), "bytes": path.stat().st_size})
    destinations = re.findall(r"\]\(([^)]+)\)", body)
    definitions = dict(re.findall(r"^\[([^\]]+)\]:\s+(\S+)", body, re.M))
    used = re.findall(r"\]\[([^\]]+)\]", body)
    record("references:" + name, all(label in definitions for label in used), sorted(set(used)))
    missing = []
    for dest in destinations + list(definitions.values()):
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", dest) or dest.startswith("#"):
            continue
        target = unquote(dest.split("#", 1)[0])
        if not (path.parent / target).exists():
            missing.append(dest)
    record("local_links:" + name, not missing, {"checked": len(destinations), "missing": missing})
    record("markdown_fences:" + name, len(re.findall(r"^\x60\x60\x60", body, re.M)) % 2 == 0, "balanced triple-backtick fences")
    table_mismatches = []
    width = None
    for n, line in enumerate(body.splitlines(), 1):
        if line.startswith("|") and line.endswith("|"):
            columns = len(line.split("|")) - 2
            if width is not None and columns != width:
                table_mismatches.append(n)
            width = columns
        else:
            width = None
    record("table_columns:" + name, not table_mismatches, table_mismatches)

current = history[0].decode()
report = (ROOT / TARGETS[1]).read_text()
record("current_model", "gpt-6.1-sol" in current and "gpt-6.1-sol" in report and "Qwen3.8-Max" not in current + report, "historic model remains only in preserved old plan")
record("thesis_title_unchanged", "| 论文题目 | 面向边缘智能场景的小型机械臂云边协同控制系统的设计 |" in report, "original thesis title")
record("scope_label", all("Harness" in text and "2027" in text and "INITIAL/METHOD/FINAL" in text for text in [current, report]), "product framing, conditional schedule and research freeze separation")

diff = subprocess.run(["git", "diff", "--check", "--", *TARGETS], cwd=ROOT, capture_output=True, text=True)
record("git_diff_check", diff.returncode == 0, diff.stdout + diff.stderr)
changed = [path for path in subprocess.run(["git", "diff", "--name-only", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\0") if path]
initial = {
    "src/cloud_edge_robot_arm/simulation/config.py",
    "artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-baseline",
    "artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-h3",
}
record("tracked_change_scope", not (set(changed) - set(TARGETS) - initial), changed)
result = {
    "date": "2026-11-17",
    "scope": "documentation_only",
    "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
    "checks": checks,
    "target_hashes": after,
    "product_tests": "NOT_RUN",
    "api_physics_hardware": "NOT_EXECUTED",
    "research_acceptance": "NO_NEW_ACCEPTANCE",
    "reproduction_boundary": "Frozen inputs and full source responses remain local; a fresh clone alone cannot rerun snapshot checks.",
}
(ROUND / "implementation/validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], "checks": len(checks), "failed": [c for c in checks if not c["passed"]]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
