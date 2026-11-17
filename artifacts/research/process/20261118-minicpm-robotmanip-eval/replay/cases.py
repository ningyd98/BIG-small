"""Frozen inputs for the offline RobotManip versus Molmo2-ER probe."""
import hashlib
import json
from pathlib import Path

WORKTREE = Path("/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall")
MAIN = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ARCHIVE = WORKTREE / "experiments/results/phase9"
_FIXED = (ARCHIVE / "grasp-lift-stop-20261117" /
          "worker-checks/worker-01/test_real_worker_runs_explicit0/worker-run")
FRAMES = {
    "fixed-top": _FIXED / "before",
    "varied-top": (ARCHIVE / "grasp-place-repair-20261117" /
                   "baseline-cloud/test_actual_worker_cloud_image0/worker-run/before"),
    "oblique-held": _FIXED / "component/frames/pre-05-place",
}
TARGET = "visible top center of red block"
DESTINATION = "interior of green region"
CASES = [
    (f"{frame}/{role}", frame, phrase, label)
    for frame in FRAMES
    for role, phrase, label in (
        ("target", TARGET, "object_geom"),
        ("destination", DESTINATION, "target_region_geom"),
    )
] + [
    ("fixed-top/absent-object", "fixed-top", "visible top center of blue block", None),
    ("varied-top/absent-region", "varied-top", "interior of yellow region", None),
]
INSTRUCTION = "Pick up the red block and place it in the green region."

def sha(content):
    return hashlib.sha256(content).hexdigest()

def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

def rgb_sha(frame):
    return sha((FRAMES[frame] / "rgb.png").read_bytes())
