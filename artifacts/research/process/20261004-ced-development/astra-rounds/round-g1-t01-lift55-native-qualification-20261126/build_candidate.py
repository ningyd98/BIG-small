"""Create a locked child runtime without editing the selected parent."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = json.loads((HERE / "plan.json").read_bytes())
PARENT = ROOT / PLAN["parent_runtime"]
OUT = ROOT / PLAN["output"]
MODULE = "scripts/graduation/g1_lift55_qualification.py"
ENTRY = "scripts/graduation/g1_lift55_entry.json"
CAMERA = "src/cloud_edge_robot_arm/simulation/mujoco/camera.py"
SERVO = "src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py"
WORKER = "scripts/graduation/g1_complete_worker.py"
SCORER = "scripts/graduation/g1_clearance_score.py"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def encoded(data):
    return (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def replace(text, before, after):
    require(text.count(before) == 1, "frozen insertion anchor differed: " + before[:65])
    return text.replace(before, after, 1)


def prepare_entry():
    old = ROOT / PLAN["original_case"] / "instance"
    seal = json.loads((old / "local-clearance-seal.json").read_bytes())
    path = old / "local-clearance.json"
    require(sha(path) == seal["local_clearance_sha256"], "original local clearance differs")
    (pre,) = [
        r
        for r in json.loads(path.read_bytes())["rows"]
        if r["skill"] == "LIFT" and r["phase"] == "PRE"
    ]
    require(
        pre["status"] == "CLEAR" and pre["physics_step"] == PLAN["qualification"]["entry_step"],
        "original LIFT entry did not clear",
    )
    return encoded(
        {
            "source_sha256": sha(path),
            "step": pre["physics_step"],
            "target": pre["target_xyz"],
            "command_seq": pre["robot"]["handoff"]["entry_command_seq"],
            "robot": pre["robot"],
            "drive": pre["robot"]["handoff"],
        }
    )


def camera_recording(source):
    source = replace(
        source, "import struct\n", "import struct\nfrom contextvars import ContextVar\n"
    )
    source = replace(
        source,
        "class MuJoCoRGBDCamera:",
        """# Independent request budget for this development process. Pixel generation is original.
_qualification_capture_counts: ContextVar[list[int] | None] = ContextVar(
    "qualification_capture_counts", default=None,
)


class MuJoCoRGBDCamera:""",
    )
    return replace(
        source,
        "        captured_at = datetime.now(UTC)\n",
        """        counts = _qualification_capture_counts.get()
        if counts is not None:
            if counts[0] >= counts[1]:
                raise ValueError("qualification native camera request budget exceeded")
            counts[0] += 1
        captured_at = datetime.now(UTC)
""",
    )


def servo_changes(source):
    source = replace(source, "import math\n", "import hashlib\nimport math\n")
    source = replace(
        source,
        "            reference = CartesianMotionReference(\n",
        """            reference_type = CartesianMotionReference
            if path is not None and path.skill == "LIFT":
                from scripts.graduation.g1_lift55_qualification import reference_class

                reference_type = reference_class(path)
            reference = reference_type(
""",
    )
    return replace(
        source,
        "            while backend.total_physics_steps - start < max_steps:\n",
        """            if path is not None and path.skill == "LIFT" and reference is not None:
                proof = hashlib.sha256()
                for values in (reference.positions, reference.velocities, reference.accelerations):
                    proof.update(np.asarray(values, dtype="<f8").tobytes())
                session.qualification_lift_reference = {
                    "seconds": reference.duration_s,
                    "settle_s": reference.settle_s,
                    "start_step": int(start),
                    "phase": path.skill,
                    "array_sha256": proof.hexdigest(),
                }
            while backend.total_physics_steps - start < max_steps:
""",
    )


def worker_changes(source):
    source = replace(
        source,
        "from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD\n",
        """from scripts.graduation.g1_lift55_qualification import (
    CAPTURE_REQUEST_LIMIT, CASE_ID, QUALIFICATION_LABEL, LiftTrace,
)

from cloud_edge_robot_arm.simulation.mujoco.camera import _qualification_capture_counts
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
""",
    )
    source = replace(
        source,
        "        self.payload_samples = payload_samples\n",
        "        self.payload_samples = payload_samples\n        self.lift_trace = LiftTrace(self)\n",
    )
    source = replace(
        source,
        "    def run(self):\n",
        """    def execute(self, index):
        skill = self.report["actions"][index]["skill"]
        if index >= 4:
            if self.report["actions"][3]["status"] != "PASS" or skill != "MOVE_TO_REGION":
                raise ValueError("unexpected qualification boundary")
            self.action = None
            self.phase = "QUALIFICATION_BOUNDARY"
            raise native.ComponentStopped("DEVELOPMENT_LIFT_QUALIFICATION_BOUNDARY")
        if skill != "LIFT":
            return super().execute(index)
        try:
            with self.backend.observe_actuator_steps(self.lift_trace.before_step):
                return super().execute(index)
        finally:
            self.lift_trace.publish()

    def run(self):
""",
    )
    source = replace(
        source,
        "        finish = time.perf_counter_ns()\n",
        """        if skill == "LIFT" and phase in ("PRE", "FEEDBACK"):
            self.lift_trace.decision(frame, phase, robot, target, status)
        finish = time.perf_counter_ns()
""",
    )
    source = replace(
        source,
        "def run(repo, label, allocation_sha, case_id, *, preflight=False):\n",
        """def run(repo, label, allocation_sha, case_id, *, preflight=False):
    trials.require(
        label == QUALIFICATION_LABEL and case_id == CASE_ID and not preflight,
        "the 5.5 s generation is restricted to its single registered t01 qualification",
    )
    counts = [0, CAPTURE_REQUEST_LIMIT]
    token = _qualification_capture_counts.set(counts)
    try:
        return run_qualification(repo, label, allocation_sha, case_id, preflight=preflight)
    finally:
        _qualification_capture_counts.reset(token)
        case = repo / trials.PRIVATE / "batches" / label / case_id
        if (case / "attempt.json").exists():
            trials.write_once(
                case / "qualification-native-camera.json",
                {"native_camera_requests": counts[0], "limit": counts[1]},
            )


def run_qualification(repo, label, allocation_sha, case_id, *, preflight=False):
""",
    )
    return source


def scorer_change(source):
    anchor = """        passive["current_pixel_replay"] = replay_payload_pixels(
            raw,
            index,
            allocation,
            receipt,
            batch["runtime_build_sha256"],
            events,
            physics,
            commands,
        )
"""
    return replace(
        source,
        anchor,
        '        with bind_scene(row["scene_id"]):\n'
        + "".join("    " + line for line in anchor.splitlines(keepends=True)),
    )


def verify_tree(tree, files):
    for name, expected in files.items():
        path = tree / name
        require(
            path.resolve().is_relative_to(tree) and sha(path) == expected,
            f"runtime member changed: {name}",
        )


def build():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(head == PLAN["head"], "candidate planning head changed")
    for path, expected in PLAN["input_sha256"].items():
        require(sha(ROOT / path) == expected, f"unbound candidate input: {path}")
    lock = json.loads((PARENT / "runtime-build.json").read_bytes())
    verify_tree(PARENT, lock["runtime_files_sha256"])
    changes = {
        MODULE: (HERE / "qualification_trace.py").read_bytes(),
        ENTRY: prepare_entry(),
        CAMERA: camera_recording((PARENT / CAMERA).read_text()).encode(),
        SERVO: servo_changes((PARENT / SERVO).read_text()).encode(),
        WORKER: worker_changes((PARENT / WORKER).read_text()).encode(),
        SCORER: scorer_change((PARENT / SCORER).read_text()).encode(),
    }
    for name, data in changes.items():
        if name.endswith(".py"):
            compile(data, name, "exec")
        h = digest(data)
        lock["runtime_files_sha256"][name] = h
        lock["overrides_sha256"][name] = h
        for field in ("scorer_files_sha256", "detector_files_sha256"):
            if name in lock[field]:
                lock[field][name] = h
    lock_bytes = encoded(lock)
    generation = digest(lock_bytes)
    dest = PARENT.parents[1] / generation
    require(not dest.exists() and not OUT.exists(), "candidate output already used")
    with TemporaryDirectory(dir=dest.parent, prefix=".lift55-build-") as tmp:
        staged = Path(tmp) / "assembled"
        tree = staged / "runtime-source"
        tree.mkdir(parents=True)
        for name in lock["runtime_files_sha256"]:
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name in changes:
                target.write_bytes(changes[name])
            else:
                shutil.copyfile(PARENT / name, target)
        (tree / "runtime-build.json").write_bytes(lock_bytes)
        verify_tree(tree, lock["runtime_files_sha256"])
        staged.rename(dest)
    OUT.mkdir()
    (OUT / "build.json").write_bytes(
        encoded(
            {
                "parent": PARENT.parent.name,
                "generation": generation,
                "plan_sha256": sha(HERE / "plan.json"),
                "source_sha256": {
                    name: sha(HERE / name)
                    for name in ("build_candidate.py", "qualification_trace.py")
                },
                "changed_runtime_members": {name: digest(data) for name, data in changes.items()},
                "native_runtime_members": len(lock["runtime_files_sha256"]),
            }
        )
    )
    print(generation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build()
