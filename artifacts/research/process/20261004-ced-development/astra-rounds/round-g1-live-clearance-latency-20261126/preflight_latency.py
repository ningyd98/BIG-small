"""Validate exact digest extraction and episode-owned reference lifetime without EGL."""

# ruff: noqa: E402
import gzip
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from latency_components import INTEGRATION_FIELD, EpisodeRobotReference, integration_sha256
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
sys.path.insert(0, str(ROOT / PLAN["source_round"]))

import entry_probe as source


def verify_inputs():
    for path, expected in PLAN["input_sha256"].items():
        source.require(sha(ROOT / path) == expected, f"frozen input differs: {path}")
    original = ROOT / PLAN["source_private"]
    seal = read(original / "capture-seal.json")
    source.require(seal["complete"], "unsealed source")
    source.original.verified_tree(original, seal["members"])
    return original


def digest_proof(original):
    context = source.dwell.import_terminal()
    original_plan, roots = context.design()
    case = next(item for item in original_plan["cases"] if item["id"] == "dense-fit-03")
    reset = read(source.dwell.FIT / "native-resets.json")[0]["parameters"]["requested"]
    backend = source.native.MuJoCoPhysicsBackend()
    try:
        context.prepare_backend(backend, reset, case, roots, original_plan)
        wanted = {0, 2840, 5085, 5325, 5565}
        rows_used = []
        with gzip.open(original / "physical.jsonl.gz", "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row["tick"] not in wanted:
                    continue
                data = backend._data
                data.qpos[:9] = row["q"]
                data.qvel[:9] = row["dq"]
                data.qvel[9:15] = row["object_qvel"]
                data.ctrl[:] = row["control"]
                data.time = row["time_s"]
                # Take two different, finite integration states at each clock.
                for warmstart in (0.0, 0.0025):
                    data.qacc_warmstart[0] = warmstart
                    same = context.integration_digest(backend, source.mujoco)[INTEGRATION_FIELD]
                    source.require(integration_sha256(backend) == same, "digest bytes differ")
                rows_used.append(row["tick"])
        source.require(
            set(rows_used) == wanted
            and backend._camera is None
            and backend.total_physics_steps == 0,
            "unexpected integration, frame or missing state",
        )
        data.qacc_warmstart[0] = 0.125
        first = integration_sha256(backend)
        data.qacc_warmstart[0] = 0.0
        second = integration_sha256(backend)
        source.require(first != second, "warm-start state lost")
        return {"source_steps": rows_used, "identical_pairs": len(rows_used) * 2}
    finally:
        backend.shutdown()


def projection_proof(original):
    observed = read(original / "observable.json")
    identity, geometry = source.original.reader.fixture(observed["reset"])
    records = []

    class Reference:
        def __init__(self, asset, width, height):
            records.append(("create", asset.name, width, height))

        def project(self, joints, fingers):
            records.append(("project", tuple(joints), tuple(fingers)))
            return tuple(joints) + tuple(fingers)

        def close(self):
            records.append(("close",))

    def certificate(binding=identity, cameras=geometry):
        return SimpleNamespace(
            optical_identity=binding,
            geometry=cameras,
            asset_sha=identity.asset_sha256,
            calibration_sha=identity.calibration_sha256,
            asset_path=source.native.ASSET,
            robot_raster=None,
        )

    def refusal(call, *args):
        try:
            call(*args)
        except ValueError:
            return
        raise ValueError("an invalid reference-resource use was accepted")

    owner = EpisodeRobotReference(Reference)
    before, after = certificate(), certificate()
    owner.attach(before)
    owner.attach(after)
    q0, q1 = np.zeros(7), np.ones(7)
    f = np.full(2, 0.039)
    source.require(
        before.robot_raster.project(q0, f) == (*q0, *f),
        "first borrow did not forward the current inputs",
    )
    before.robot_raster.close()
    source.require(
        after.robot_raster.project(q1, f) == (*q1, *f),
        "same-episode borrower reused a projection or closed the resource",
    )
    refusal(owner.attach, certificate(replace(identity, episode_id=identity.episode_id + "-wrong")))
    refusal(owner.attach, certificate(replace(identity, scene_id=identity.scene_id + "-wrong")))
    refusal(owner.attach, certificate(replace(identity, calibration_version="wrong")))
    refusal(owner.attach, before)
    owner.close()
    refusal(after.robot_raster.project, q1, f)
    source.require(
        [row[0] for row in records] == ["create", "project", "project", "close"],
        "renderer ownership operations changed",
    )
    return {"initializations": 1, "distinct_project_inputs": owner.projections, "close_calls": 1}


def main():
    original = verify_inputs()
    print(
        json.dumps({"integration": digest_proof(original), "ownership": projection_proof(original)})
    )


if __name__ == "__main__":
    main()
