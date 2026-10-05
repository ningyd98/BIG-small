"""登记本物理修复直接相关回归；不执行模型推理或渲染。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from restore_private_git_context import ROOT, PHYSICS, digest, verify_source, file_map, git

COMMON = [
    "tests/test_rgbd_physical_skills.py",
    "tests/test_rgbd_top_grasp.py",
    "tests/test_rgbd_grasp_scope.py",
    "tests/test_rgbd_runtime_control.py",
    "tests/test_rgbd_shared_capture.py",
    "tests/test_rgbd_motion_safety.py",
    "tests/test_rgbd_backend_contact_policy.py",
    "tests/test_rgbd_motion_success_hold.py",
]
ADDED = ["tests/test_rgbd_gripper_aperture.py"]


def main() -> None:
    output = PHYSICS / "relevant-regression-registration.json"
    if output.exists():
        raise FileExistsError(output)
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": "FROZEN_RESEARCH_PHYSICS_PATCH_DIRECT_RELEVANT_REGRESSION", "root_scope_decision": "Do not restart entire 1730/1735 suite; baseline common129, H3 common129 plus5 counterexamples. Full suite remains incomplete, two shared annotation defects separately documented.", "full_suite_completion_claim": False, "formal_g1": False, "online_models": False, "execute_only_after_root_point_gpu_release": True, "patch_sha256": digest(PHYSICS / "final-h3-review.patch"), "shared_tests": COMMON, "h3_added_tests": ADDED, "roles": {}}
    context = {}
    for role in ("baseline", "h3"):
        workspace = PHYSICS / f"workspace-{role}"
        selected = (ADDED if role == "h3" else []) + COMMON
        collection = (PHYSICS / "logs" / f"corrected-context-{role}-collection.log").read_text().splitlines()
        nodes = [line for line in collection if line.split("::")[0] in selected and "::" in line]
        expected = 134 if role == "h3" else 129
        if len(nodes) != expected:
            raise RuntimeError(f"Incorrect node allocation: {role}: {len(nodes)}")
        snapshot = file_map(workspace)
        manifest = PHYSICS / f"relevant-regression-{role}-context-sha256.json"
        manifest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        env = {"MUJOCO_GL": "egl", "PYTHONPATH": str(workspace / "src"), "GIT_OPTIONAL_LOCKS": "0", "MODEL_CONTROL_DB": str(PHYSICS / "regression-runtime" / f"{role}-relevant-v1-model-control.db"), "PYTHONDONTWRITEBYTECODE": "1", "PATH": str(ROOT / ".venv/bin") + os.pathsep + os.environ["PATH"]}
        record["roles"][role] = {"workspace": str(workspace), "source_verified": verify_source(workspace, role), "private_git_head": git(workspace, "rev-parse", "HEAD"), "context_manifest": str(manifest), "context_manifest_sha256": digest(manifest), "expected_nodes": nodes, "expected_count": expected, "command": [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-vv", "--tb=short", "--durations=15", *selected], "environment_overrides": env, "source_patch_unchanged": True}
        context[role] = snapshot
    patch_names = {item["path"] for item in json.loads((PHYSICS / "patch-file-manifest.json").read_text())["files"]}
    unexpected = [name for name in set(context["baseline"]) | set(context["h3"]) if context["baseline"].get(name) != context["h3"].get(name) and name not in patch_names]
    if unexpected:
        raise RuntimeError(f"Paired context mismatch: {unexpected}")
    record["paired_context_only_six_file_patch_differences"] = True
    baseline_nodes = set(record["roles"]["baseline"]["expected_nodes"])
    h3_nodes = set(record["roles"]["h3"]["expected_nodes"])
    if not baseline_nodes <= h3_nodes or len(h3_nodes - baseline_nodes) != 5:
        raise RuntimeError("Paired node identities mismatch")
    record["shared_nodeid_count"] = len(baseline_nodes)
    record["h3_only_nodeids"] = sorted(h3_nodes - baseline_nodes)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: record[key] for key in ("shared_nodeid_count", "h3_only_nodeids", "paired_context_only_six_file_patch_differences")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
