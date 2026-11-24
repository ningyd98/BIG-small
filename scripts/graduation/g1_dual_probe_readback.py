"""Independently check zero-step RGB-D, online outputs, per-trial source locks and allocation."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.g1_dual_trials import PLAN_SHA as PLAN
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

if __package__:
    from scripts.graduation.g1_dual_pixel_readback import dual_read
else:
    from g1_dual_pixel_readback import dual_read

if not __debug__:
    raise RuntimeError("run the independent readback with assertions enabled")


def envelope(model, data, name):
    geom = model.geom(name)
    frame = data.geom(name)
    axes = np.reshape(frame.xmat, (3, 3))
    if geom.type[0] == mujoco.mjtGeom.mjGEOM_BOX:
        radius = np.sum(np.abs(axes * geom.size), axis=1)
    else:
        align = np.abs(axes[:, 2])
        if geom.type[0] == mujoco.mjtGeom.mjGEOM_CAPSULE:
            radial = np.ones(3)
        elif geom.type[0] == mujoco.mjtGeom.mjGEOM_CYLINDER:
            radial = np.sqrt(np.maximum(0, 1 - align**2))
        else:
            raise ValueError("unsupported shape in archived fixture")
        radius = geom.size[0] * radial + geom.size[1] * align
    return np.array([frame.xpos - radius, frame.xpos + radius])


def legacy_bounds(row, a, b):
    required = {
        "name",
        "other",
        "original_mj_geomDistance_m",
        "conservative_world_aabb_lower_bound_m",
    }
    paired = {"aabb_a_m", "aabb_b_m"}
    recorded = row.get("other") == "table"
    if not required <= row.keys() or (paired & row.keys()) != (paired if recorded else set()):
        raise ValueError("inconsistent original geometry measurement fields")
    if recorded and any(
        not np.allclose(row[k], v, rtol=0, atol=1e-12)
        for k, v in [("aabb_a_m", a), ("aabb_b_m", b)]
    ):
        raise ValueError("archived bounds disagree with independently reconstructed geometry")
    distance = float(np.linalg.norm(np.maximum(0, np.maximum(a[0] - b[1], b[0] - a[1]))))
    if abs(distance - row["conservative_world_aabb_lower_bound_m"]) > 1e-12 or not math.isfinite(
        row["conservative_world_aabb_lower_bound_m"]
    ):
        raise ValueError("archived separation differs from independent reconstruction")
    return distance, recorded


def first_model(private, sha_expected, asset_name):
    tree = private / "reset-clearance-first-generation/runtime-source"
    lock = pinned(
        tree / "runtime-build.json",
        "a6fbe28715b6e86e4c3de2456d46bf65fb50fc2ac4d5bd8512c737c5fec49d07",
    )
    for k, h in lock["runtime_files_sha256"].items():
        if sha(tree / k) != h:
            raise ValueError("archived model or dependency differs from its build seal")
    if sha_expected != lock["runtime_files_sha256"][asset_name]:
        raise ValueError("incorrect original asset SHA256")
    return mujoco.MjModel.from_xml_path(str(tree / asset_name))


def restored(model, pose):
    data = mujoco.MjData(model)
    for name, value in (
        ("joint1", -0.8),
        ("finger_left_joint", 0.04),
        ("finger_right_joint", 0.04),
    ):
        data.qpos[model.joint(name).qposadr[0]] = value
    start = model.joint("object_free").qposadr[0]
    x, y, z, yaw = pose
    data.qpos[start : start + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
    mujoco.mj_forward(model, data)
    return data


def clearance(private, public):
    reference = private / "vision/clearance-failure-readback.json"
    old = pinned(reference, "fc729367fe71e0ee5ff91f428cdfac553d0cbf10ce1ceca63f800b813c5beab2")
    geometry = read(public / "compiled-geometry.public.json")
    assert geometry["asset_sha256"] == old["asset_sha256"]
    model = first_model(private, old["asset_sha256"], geometry["geometry"]["asset_path"])
    archived, deviations = 0, []
    discrepancies, bounds, table = [], [], []
    poses = pinned(public / "plan.json", PLAN)["zero_step_poses"]
    if [r["xyz_yaw"] for r in old["poses"]] != poses:
        raise ValueError("unexpected or repeated initial pose")
    for before, after in zip(old["poses"], geometry["reset_fk"], strict=True):
        assert before["xyz_yaw"] == after["xyz_yaw"]
        data = restored(model, before["xyz_yaw"])
        rows = after["shape_pair_evidence"]
        assert len(rows) == len(before["pairs"]) == 44
        assert set(rows) == {v["name"] + "/" + v["other"] for v in before["pairs"]}
        for item in before["pairs"]:
            name = item["name"] + "/" + item["other"]
            row = rows[name]
            a, b = (envelope(model, data, item[k]) for k in ("name", "other"))
            tight, stored = legacy_bounds(item, a, b)
            archived += stored
            error = abs(tight - item["conservative_world_aabb_lower_bound_m"])
            deviations.append(error)
            assert abs(tight - row["raw_aabb_lower_bound_m"]) < 1e-12
            bound = row["expanded_aabb_lower_bound_m"]
            low_a, low_b = (np.nextafter(t[0] - 1e-12, -np.inf) for t in (a, b))
            hi_a, hi_b = (np.nextafter(t[1] + 1e-12, np.inf) for t in (a, b))
            expanded = np.linalg.norm(np.maximum(0, np.maximum(low_a - hi_b, low_b - hi_a)))
            assert abs(expanded - bound) < 1e-12
            measured = mujoco.mj_geomDistance(
                model, data, model.geom(item["name"]).id, model.geom(item["other"]).id, 3, None
            )
            assert abs(measured - item["original_mj_geomDistance_m"]) < 1e-12
            assert 0 < bound <= tight + 1e-14 and tight - bound < 1e-10
            assert row["raw_distmax_m"] == 3 and not row["contact_observed"]
            assert abs(row["raw_mj_geomDistance_m"] - item["original_mj_geomDistance_m"]) < 1e-12
            assert row["raw_zero_despite_separation"] == (item["original_mj_geomDistance_m"] == 0)
            if row["raw_zero_despite_separation"]:
                discrepancies.append(
                    {"pose": after["xyz_yaw"], "pair": name, "lower_bound_m": bound}
                )
            bounds.append(bound)
            if item["other"] == "table":
                gap = a[0, 2] - b[1, 2]
                assert gap > 0 and abs(gap - row["table_vertical_gap_m"]) < 1e-12
                table.append(gap)
    assert len(bounds) == 88 and len(discrepancies) == 3 and len(table) == archived == 8
    return {
        "schema": "g1.dual-marker.independent-clearance-readback.v1",
        "first_geometry_readback_sha256": sha(reference),
        "compiled_geometry_sha256": sha(public / "compiled-geometry.public.json"),
        "asset_sha256": geometry["asset_sha256"],
        "pairs_checked": len(bounds),
        "original_pairs_with_bounds": archived,
        "original_pairs_with_scalar_and_rederived_bounds": len(bounds) - archived,
        "maximum_scalar_difference_m": max(deviations),
        "minimum_conservative_separation_m": min(bounds),
        "minimum_table_vertical_gap_m": min(table),
        "raw_zero_with_separation": discrepancies,
    }


def effective_geometry(private, public):
    geo = read(public / "compiled-geometry.public.json")
    asset = geo["geometry"]["asset_path"]
    generation = sha(public / "runtime-build.public.json")
    tree = private / "runtime-source"
    lock = pinned(tree / "runtime-build.json", generation)
    h = sha(tree / asset)
    assert h == geo["asset_sha256"] == lock["runtime_files_sha256"][asset]
    model = mujoco.MjModel.from_xml_path(str(tree / asset))
    versions = {
        "5c8e97f5dd17cf719d579d1badeab85de2e8f52dd14f6be0ef5dd2ff28159e66": (0.10036, 88),
        "a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803": (0.10078432, 132),
    }
    if h not in versions:
        raise ValueError("unregistered physical carrier assembly")
    expected_mass, expected_pairs = versions[h]
    assert math.isclose(model.body("object").mass[0], expected_mass, abs_tol=1e-12, rel_tol=0)
    assert math.isclose(geo["compiled_body_mass_kg"], expected_mass, abs_tol=1e-12, rel_tol=0)
    assert geo["physics_steps"] == geo["dispatched_commands"] == 0
    actual_supports = {
        model.geom(i).name
        for i in range(model.ngeom)
        if model.geom_bodyid[i] == model.body("object").id
        and model.geom(i).name != "object_geom"
        and (model.geom_contype[i] or model.geom_conaffinity[i])
    }
    external = {
        "base",
        *(f"link{i}" for i in range(1, 7)),
        "hand",
        "left_finger_geom",
        "right_finger_geom",
        "table",
    }
    expected = {a + "/" + b for a in actual_supports for b in external}
    poses = pinned(public / "plan.json", PLAN)["zero_step_poses"]
    assert len(expected) * len(poses) == expected_pairs
    values = []
    for pose, published in zip(poses, geo["reset_fk"], strict=True):
        assert pose == published["xyz_yaw"] and set(published["shape_pair_evidence"]) == expected
        data = restored(model, pose)
        for key, r in published["shape_pair_evidence"].items():
            a, b = (envelope(model, data, name) for name in key.split("/"))
            low_a, low_b = (np.nextafter(t[0] - 1e-12, -np.inf) for t in (a, b))
            high_a, high_b = (np.nextafter(t[1] + 1e-12, np.inf) for t in (a, b))
            dist = float(np.linalg.norm(np.maximum(0, np.maximum(low_a - high_b, low_b - high_a))))
            assert dist > 0 and abs(dist - r["expanded_aabb_lower_bound_m"]) < 1e-12
            assert not r["contact_observed"]
            values.append(dist)
    return {
        "runtime_build_sha256": generation,
        "asset_sha256": h,
        "mass_kg": expected_mass,
        "support_and_carrier_geoms": sorted(actual_supports),
        "verified_clearances": len(values),
        "minimum_clearance_lower_bound_m": min(values),
        "compiled_sha256": sha(public / "compiled-geometry.public.json"),
    }


def qualification(private, public):
    pinned(public / "plan.json", PLAN)
    digest = sha(public / "zero-step-probes.public.json")
    probe = pinned(private / "probes/zero-step-probes.json", digest)
    geom = probe["geometry"]
    assert probe["eligible"] and probe["physics_steps"] == probe["dispatched_actions"] == 0
    assert probe["plan_sha256"] == PLAN and probe["gate"]["static_decision_sha256"] == sha(
        public / "refusal-decision.public.json"
    )
    assert probe["gate"]["cross_readback_sha256"] == sha(public / "cross-readback.public.json")
    build = pinned(
        private / "runtime-source/runtime-build.json", sha(public / "runtime-build.public.json")
    )
    assert all(
        sha(private / "runtime-source" / n) == h for n, h in build["runtime_files_sha256"].items()
    )
    geometry = pinned(private / "probes/compiled-geometry.json", probe["compiled_geometry_sha256"])
    assembly = effective_geometry(private, public)
    assert (
        geometry["camera_fovy_deg"] == 50
        and geometry["plate_overlap_m2"] == 0
        and np.isclose(geometry["compiled_body_mass_kg"], assembly["mass_kg"], rtol=0, atol=1e-12)
    )
    assert (
        geom == geometry["geometry"] and geom["camera"]["calibration_version"] == "f33940579c533afe"
    )
    assert (
        sha(private / "runtime-source" / probe["asset"]["asset_path"]) == geometry["asset_sha256"]
    )
    measures = []
    for row in probe["results"]:
        dest = private / "probes" / (row["pose"] + "-" + row["kind"])
        files = pinned(dest / "seal.json", row["private_seal_sha256"])
        for file, expected in files.items():
            assert sha(dest / file) == expected
        assert dict(read(dest / "result.json"), private_seal_sha256=sha(dest / "seal.json")) == row
        assert row["commands"] == row["physics_steps"] == 0
        trace = read(dest / "probe-trace.json")
        brief = {
            k: row[k]
            for k in ("kind", "pose", "control_demonstrated", "path_success", "private_seal_sha256")
        }
        if (dest / "tested-current.json").exists():
            frame = RGBDObservation.model_validate(
                pinned(dest / "tested-current.json", files["tested-current.json"])
            )
            pixel = dual_read(frame, geom)
            online = trace["measured"]
            assert frame.checksum_sha256 == online["checksum"]
            assert all(
                pixel[k] == online[k]
                for k in ("reason", "selected_id", "usable", "usable_ids", "observed_ids")
            )
            brief.update(
                rgbd_sha256=files["tested-current.json"],
                selected_id=pixel["selected_id"],
                observed_ids=pixel["observed_ids"],
                usable_ids=pixel["usable_ids"],
            )
            if row["path_success"]:
                actual = trace["current_registered_target"]["inputs"]
                assert actual["observation_checksum_sha256"] == frame.checksum_sha256
                assert np.allclose(actual["grasp_tcp_world_m"], pixel["tcp_m"], rtol=0, atol=1e-10)
                assert all(x["matches"] for x in trace["board_instance_match"].values())
                selection = trace["current_servo_samples"][-1]["development_dual_marker"]
                assert (
                    selection["frame_id"] == frame.frame_id
                    and selection["selected_id"] == pixel["selected_id"]
                )
                assert np.allclose(selection["grasp_world_m"], pixel["tcp_m"], rtol=0, atol=1e-10)
        measures.append(brief)
    positive = {r["kind"] for r in measures if r["path_success"]}
    negative = {r["kind"] for r in measures if r["control_demonstrated"]}
    assert positive == {"both", "only-7", "only-8"}
    assert negative >= {
        "no-marker",
        "no-depth",
        "duplicate-id",
        "unknown-id",
        "wrong-asset",
        "wrong-transform",
        "wrong-source",
        "conflict",
        "stale",
        "wrong-scene",
        "wrong-calibration",
    }
    return {
        "schema": "g1.dual-marker.independent-zero-step-readback.v1",
        "plan_sha256": PLAN,
        "probe_sha256": digest,
        "runtime_build_sha256": probe["runtime_build_sha256"],
        "positive_conditions": sorted(positive),
        "negative_conditions": sorted(negative),
        "evidence": measures,
        "compiled_assembly": assembly,
        "physics_steps": 0,
        "dispatched_actions": 0,
    }


def verify(private, public):
    check = qualification(private, public)
    assert read(public / "zero-step-readback.public.json") == check
    plan = pinned(public / "plan.json", PLAN)
    digest = check["probe_sha256"]
    probe = pinned(private / "probes/zero-step-probes.json", digest)
    build = pinned(private / "runtime-source/runtime-build.json", check["runtime_build_sha256"])
    trials = private / "trials"
    allocation_sha = sha(public / "trial-allocation.public.json")
    batch = pinned(trials / "allocation.json", allocation_sha)
    assert (
        batch["zero_step_probes_sha256"] == digest
        and batch["gate"] == probe["gate"]
        and batch["attempts_per_slot"] == 1
    )
    for slot, row in zip(plan["slots"], batch["cases"], strict=True):
        assert all(row[k] == v for k, v in slot.items())
        alloc = pinned(trials / row["allocation_file"], row["allocation_sha256"])
        assert (
            alloc["zero_step_probes_sha256"] == digest
            and alloc["runtime_build_sha256"] == probe["runtime_build_sha256"]
        )
        assert all(alloc["case"][k] == v for k, v in slot.items())
        assert (
            row["asset_sha256"]
            == alloc["asset_sha256"]
            == sha(private / "runtime-source" / row["asset_path"])
        )
        assert all(
            build["runtime_files_sha256"][n] == h for n, h in alloc["sources_sha256"].items()
        )
    write(
        public / "allocation-readback.public.json",
        {
            "schema": "g1.dual-marker.independent-allocation-readback.v1",
            "plan_sha256": PLAN,
            "probe_sha256": digest,
            "capture_allocation_sha256": allocation_sha,
            "runtime_build_sha256": probe["runtime_build_sha256"],
            "preregistered_motion_slots": len(batch["cases"]),
            "qualification_readback_sha256": sha(public / "zero-step-readback.public.json"),
            "physics_steps": 0,
            "dispatched_actions": 0,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("private", type=Path)
    cli.add_argument("public", type=Path)
    stage = cli.add_mutually_exclusive_group()
    stage.add_argument("--geometry-only", action="store_true")
    stage.add_argument("--effective-geometry", action="store_true")
    stage.add_argument("--qualification-only", action="store_true")
    args = cli.parse_args()
    if args.geometry_only:
        write(args.public / "clearance-readback.public.json", clearance(args.private, args.public))
    elif args.effective_geometry:
        write(
            args.public / "assembly-readback.public.json",
            effective_geometry(args.private, args.public),
        )
    elif args.qualification_only:
        write(
            args.public / "zero-step-readback.public.json", qualification(args.private, args.public)
        )
    else:
        verify(args.private, args.public)
