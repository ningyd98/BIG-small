"""Run one allocated G1 development slot in its own frozen interpreter source tree."""

import argparse
import json
import os
import re
import subprocess
import sys

from scripts.graduation import g1_complete_trials as trials
from scripts.graduation.perception_io import ROOT, pinned, sha


def launch(label, case_id):
    root = ROOT / trials.PRIVATE
    registration = pinned(
        root / "registration.json",
        sha(ROOT / trials.ROUND / "development-registration.public.json"),
    )
    slots = trials.select_slots(registration, label)
    trials.require(case_id in [row["id"] for row in slots], "case is outside the registered scope")
    directory = root / "batches" / label
    path = directory / "allocation.json"
    batch_sha = sha(path)
    batch = pinned(path, batch_sha)
    generation = batch["runtime_build_sha256"]
    trials.require(
        re.fullmatch("[0-9a-f]{64}", generation) and batch["label"] == label,
        "unexpected allocation",
    )
    tree = root / "builds" / generation / "runtime-source"
    lock = pinned(tree / "runtime-build.json", generation)
    trials.require(lock["plan_sha256"] == trials.PLAN_SHA, "unregistered runtime")
    args = [
        sys.executable,
        "-B",
        "-m",
        "scripts.graduation.g1_complete_worker",
        str(ROOT),
        label,
        batch_sha,
        case_id,
    ]
    if label.startswith("train-preflight-"):
        args.append("--preflight")
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join((str(tree), str(tree / "src"))),
        MUJOCO_GL="egl",
        PYOPENGL_PLATFORM="egl",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    subprocess.run(args, cwd=tree, env=env, check=True)
    instance = directory / case_id / "instance"
    run = json.loads((instance / "run.json").read_bytes())
    return {
        "case": case_id,
        "generation": generation,
        "receipt_sha256": sha(instance / "receipt.json"),
        "dispatched": sum(a.get("dispatched") is True for a in run["actions"]),
        "stop": run.get("stop"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    parser.add_argument("case")
    args = parser.parse_args()
    print(json.dumps(launch(args.batch, args.case), ensure_ascii=False))
