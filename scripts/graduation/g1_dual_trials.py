"""Allocate, acquire and independently audit the G1 dual-marker development trials."""

from __future__ import annotations

import argparse
import fcntl
import math
import os
import re
import shutil
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import dynamic_vision_score as vision
from scripts.graduation import g1_dual_build as builder
from scripts.graduation import g1_mount_score, g1_mount_trials, guarded_clock, proposal_scoring
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_translated_cases import TranslatedBackend, TranslatedEpisode

from cloud_edge_robot_arm.research import native_calibration_collection as native
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    evaluate_evidence,
    sample_physical_observation,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

PLAN_SHA = builder.PLAN_SHA
RELEASE = "g1-development-dual-marker-20261124"
HANDS = {"hand", "left_finger_geom", "right_finger_geom"}
FINGERS = HANDS - {"hand"}
SUPPORT_GEOMS = {
    f"g1_dual_id{code}_{part}"
    for code in (7, 8)
    for part in ("plate", "support", "crossbar", "upright")
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def bind_witnesses(decision, cross):
    require(
        decision["plan_sha256"] == cross["plan_sha256"] == PLAN_SHA
        and decision["capture_seal_sha256"] == cross["capture_seal_sha256"]
        and decision["complementary"] is True
        and cross["complementary"] is True,
        "two sealed, independently positive decisions required",
    )
    selected = {}
    for bucket in ("X_only", "Y_only"):
        witnesses = decision["witnesses"].get(bucket, [])
        if isinstance(witnesses, dict):
            witnesses = [witnesses]
        for witness in witnesses:
            found = [
                p
                for p in cross["poses"]
                if p["case"] == witness["case"]
                and p["role"] == witness["time_role"]
                and p["physics_step"] == witness["step"]
                and p["bucket"] == bucket
            ]
            if len(found) != 1:
                continue
            pose = found[0]
            if all(
                re.fullmatch(r"[a-f0-9]{64}", witness["normal_frames"][side]["sha256"])
                and pose["measurements"][side]["normal"]["rgbd_file_sha256"]
                == witness["normal_frames"][side]["sha256"]
                and pose["measurements"][side]["normal"]["usable"] is (side == bucket[0])
                for side in ("X", "Y")
            ):
                selected[bucket] = witness
                break
        require(bucket in selected, "unverified complementary normal-frame witness: " + bucket)
    return selected


def context(plan_file, private):
    plan = pinned(plan_file, PLAN_SHA)
    require(
        plan["baseline"] == builder.BASE
        and sha(plan_file.with_suffix(".md")) == plan["plan_md_sha256"]
        and ROOT == (private / "runtime-source").resolve() == Path.cwd().resolve(),
        "wrong plan, working directory or isolated runtime",
    )
    repository = next(p for p in plan_file.parents if (p / ".git").exists())
    require((repository / plan["new_private"]).resolve() == private, "wrong private generation")
    build_sha = sha(plan_file.with_name("runtime-build.public.json"))
    lock = builder.load_lock(ROOT, build_sha)
    ds = plan_file.with_name("refusal-decision.public.json")
    cs = plan_file.with_name("cross-readback.public.json")
    decision, cross = read(ds), read(cs)
    gate = {
        "static_decision_sha256": sha(ds),
        "cross_readback_sha256": sha(cs),
        "capture_seal_sha256": cross["capture_seal_sha256"],
        "witnesses": bind_witnesses(decision, cross),
    }
    for witness in gate["witnesses"].values():
        source = next(row for row in plan["source_cases"] if row["case"] == witness["case"])
        role = (
            "previous_accepted_feedback"
            if witness["time_role"] == "previous"
            else "rejected_feedback"
        )
        original = source["original_feedback"][role]
        poses = [
            p
            for p in cross["poses"]
            if p["case"] == source["case"] and p["role"] == witness["time_role"]
        ]
        require(
            len(poses) == 1
            and poses[0]["source_frame_id"] == original["frame_id"]
            and witness["source_episode"] == source["episode"]
            and witness["step"] == original["physics_step"],
            "wrong source feedback witness",
        )
    return repository, plan, lock, build_sha, gate


def arm_description(arm, lock, plan):
    from scripts.graduation import g1_dual_asset as asset

    original = plan["single_mounts"][0]
    require(original["id"] == "original", "missing registered original comparison arm")
    require(arm in ("original", "dual"), "unexpected arm")
    family = original["family"] if arm == "original" else asset.FAMILY
    name = original["asset_path"] if arm == "original" else asset.ASSET_PATH
    geometry = runtime.geometry_registration(marker_family_id=family)
    registration = NativeGeometryRegistration(geometry)
    registration.validate_asset(ROOT)
    require(
        geometry["asset_path"] == name and registration.marker_family_id == family,
        "crossed registered scene or family",
    )
    asset_sha = lock["runtime_files_sha256"][name]
    require(
        sha(ROOT / name) == asset_sha == registration.pose_marker.marked_asset_sha256,
        "wrong compiled asset source bytes",
    )
    return {
        "mount": arm,
        "family": family,
        "asset_path": name,
        "asset_sha256": asset_sha,
        "physical_object_mass_kg": 0.08 if arm == "original" else asset.BODY_MASS_KG,
    }, geometry


def catalog_for(lock, description, plan, old_native):
    """Both arms bind actual adapter bytes. Historical native hashes have their own field."""
    baseline_files, effective = lock["baseline_files_sha256"], lock["runtime_files_sha256"]
    expected = g1_mount_trials.CATALOGS[plan["single_mounts"][0]["family"]][2]
    require(
        native.digest(old_native) == expected
        and all(baseline_files.get(k) == v for k, v in old_native.items()),
        "wrong historical native source generation",
    )
    # Reuse the full historical list of source paths. Rehash each path against the effective tree.
    paths = set(old_native) | {k for k in effective if k.startswith("scripts/")}
    paths.add(description["asset_path"])
    full = {k: effective[k] for k in sorted(paths)}
    require(all(sha(ROOT / k) == h for k, h in full.items()), "changed development source bytes")
    return full


def historical(repository, plan, name):
    path = plan["prior_private"] + "/trials/" + name
    return pinned(repository / path, plan["input_sha256"][path])


def registrations(repository, plan, lock):
    old_native = historical(repository, plan, "original-native-source-inventory.json")
    result = {}
    for arm in ("original", "dual"):
        description, geometry = arm_description(arm, lock, plan)
        full = catalog_for(lock, description, plan, old_native)
        result[arm] = description, geometry, full
    return result


def bind_scenario_mass(scenario, expected, compiled):
    require(
        math.isfinite(compiled)
        and expected > 0
        and math.isclose(expected, compiled, abs_tol=1e-12, rel_tol=0),
        "compiled rigid body mass differs from registered mechanical assembly",
    )
    return replace(scenario, object_mass_kg=expected)


def mass_properties(model):
    body = model.body("object")
    return {
        "mass_kg": float(body.mass[0]),
        "principal_inertia_kg_m2": body.inertia.tolist(),
        "body_local_center_of_mass_m": body.ipos.tolist(),
        "inertial_quaternion_wxyz": body.iquat.tolist(),
    }


class RegisteredAssemblyBackend(TranslatedBackend):
    def __init__(self, directory, case):
        super().__init__(directory, case["view"])
        self.registered_mass = case["physical_object_mass_kg"]

    def reset(self, scenario):
        before = mass_properties(self._model)
        scenario = bind_scenario_mass(scenario, self.registered_mass, before["mass_kg"])
        super().reset(scenario)
        after = mass_properties(self._model)
        require(
            all(np.allclose(before[k], after[k], atol=1e-12, rtol=0) for k in before),
            "physical reset altered the registered rigid body mass properties",
        )
        write(
            self.directory / "assembly-reset.json",
            dict(
                requested_object_mass_kg=scenario.object_mass_kg,
                compiled=before,
                after_reset=after,
            ),
        )


def episode_with_registered_mass(directory, alloc, allocation_sha, catalog):
    episode = TranslatedEpisode(directory, alloc, allocation_sha, catalog)
    episode.backend = RegisteredAssemblyBackend(directory, alloc["case"])
    episode.robot = runtime.MuJoCoSkillRobot(episode.backend)
    episode.executor = guarded_clock.RecordedExecutor(
        episode,
        runtime.SkillExecutor(robot=episode.robot, registry=runtime.SkillRegistry.default()),
    )
    return episode


@contextmanager
def exclusive_egl(private):
    require(os.environ.get("MUJOCO_GL") == "egl", "MuJoCo EGL required")
    with (private / "egl.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def checked_controls(plan_file, private, build_sha, gate):
    from scripts.graduation.g1_dual_probe import qualifies

    path = plan_file.with_name("zero-step-probes.public.json")
    controls = pinned(private / "probes" / "zero-step-probes.json", sha(path))
    require(
        controls["plan_sha256"] == PLAN_SHA
        and controls["runtime_build_sha256"] == build_sha
        and controls["gate"] == gate
        and controls["eligible"] is True
        and qualifies(controls["results"])
        and controls["dispatched_actions"] == 0,
        "missing complete zero-step support / fail-closed controls",
    )
    for name, digest in controls["private_seal_sha256"].items():
        require(sha(private / "probes" / name) == digest, "changed zero-step probe raw seal")
    return sha(path)


def issue(plan_file, raw):
    private = raw.parent
    repository, plan, lock, build_sha, gate = context(plan_file, private)
    probe_sha = checked_controls(plan_file, private, build_sha, gate)
    old = historical(repository, plan, "m01-original/allocation.json")
    previous = historical(repository, plan, "allocation.json")
    require(
        old["case"]["visual_stages_in_order"]
        == old["intent_descriptor"]["stages"]
        == plan["stage_order"]
        and len(plan["slots"]) == 8
        and all(s["attempts"] == 1 for s in plan["slots"])
        and all(
            s["reset_fixture_center_m"] != o["reset_fixture_center_m"]
            for s in plan["slots"]
            for o in previous["cases"]
        ),
        "case template or new placement design differs",
    )
    require(
        shutil.disk_usage(private).free >= len(plan["slots"]) * 2**31,
        "insufficient private raw storage",
    )
    arms = registrations(repository, plan, lock)
    raw.mkdir()
    issued = datetime.now(UTC).isoformat()
    catalogs, geometries, cases = {}, {}, []
    for arm, (desc, geometry, full) in arms.items():
        path = raw / f"{arm}-development-source-inventory.json"
        write(path, full)
        catalogs[desc["family"]] = {
            "family": desc["family"],
            "selection": "ACTUAL_ISOLATED_DEVELOPMENT_SOURCES",
            "historical_control_native_product_sha256": old["catalog"]["original_product_sha256"],
            "count": len(full),
            "private_filename": path.name,
            "archived_json_sha256": sha(path),
            "product_compact_sorted_utf8_sha256": native.digest(full),
            "development_default_separators_sorted_utf8_sha256": runtime.digest(full),
        }
        geometries[desc["family"]] = geometry
    for spec in plan["slots"]:
        desc, geometry, full = arms[spec["arm"]]
        row = {**spec, **desc}
        case = {
            **old["case"],
            **row,
            "visual_id": RELEASE + "/" + row["id"],
            "release": RELEASE,
            "visual_seed": row["seed"],
            "private_output": row["id"] + "/instance",
        }
        case.pop("original_catalog_sha256")
        a = dict(
            schema="g1.development.dual-marker.case.v1",
            baseline=builder.BASE,
            scope="DEVELOPMENT_COMPONENT_ONLY",
            issued_at=issued,
            case=case,
            geometry=geometry,
            asset_sha256=desc["asset_sha256"],
            catalog=catalogs[desc["family"]],
            sources_sha256=full,
            component_catalog_sha256=runtime.digest(full),
            source_root="runtime-source",
            intent_descriptor=old["intent_descriptor"],
            selected_entry=old["selected_entry"],
            capture_grid=old["capture_grid"],
            plan_sha256=PLAN_SHA,
            plan_md_sha256=plan["plan_md_sha256"],
            selection_sha256=gate["static_decision_sha256"],
            runtime_build_sha256=build_sha,
            cross_readback_sha256=gate["cross_readback_sha256"],
            zero_step_probes_sha256=probe_sha,
        )
        path = raw / row["id"] / "allocation.json"
        path.parent.mkdir()
        write(path, a)
        cases.append(
            {
                **row,
                "allocation_file": path.relative_to(raw).as_posix(),
                "allocation_sha256": sha(path),
            }
        )
    batch = dict(
        schema="g1.development.dual-marker.allocation.v1",
        release=RELEASE,
        baseline=builder.BASE,
        plan_sha256=PLAN_SHA,
        plan_md_sha256=plan["plan_md_sha256"],
        runtime_build_sha256=build_sha,
        selection_sha256=gate["static_decision_sha256"],
        gate=gate,
        issued_at=issued,
        attempts_per_slot=1,
        native_catalogues=catalogs,
        geometries=geometries,
        cases=cases,
        catalog_scope="Actual development sources for both arms and historical control digest.",
        zero_step_probes_sha256=probe_sha,
        hardware_actions=0,
        task_model_calls=0,
        formal_claims=0,
        formal_simulations=0,
    )
    write(raw / "allocation.json", batch)
    write(plan_file.with_name("trial-allocation.public.json"), batch)


def check_batch(plan_file, raw, allocation_sha):
    _, plan, lock, build_sha, gate = context(plan_file, raw.parent)
    batch = pinned(raw / "allocation.json", allocation_sha)
    require(
        sha(plan_file.with_name("trial-allocation.public.json")) == allocation_sha
        and batch["plan_sha256"] == PLAN_SHA
        and batch["baseline"] == builder.BASE
        and batch["release"] == RELEASE
        and batch["runtime_build_sha256"] == build_sha
        and batch["gate"] == gate
        and batch["attempts_per_slot"] == 1
        and batch["zero_step_probes_sha256"]
        == checked_controls(plan_file, raw.parent, build_sha, gate),
        "foreign batch or unverified qualification",
    )
    arms = {arm: arm_description(arm, lock, plan)[0] for arm in ("original", "dual")}
    for spec, row in zip(plan["slots"], batch["cases"], strict=True):
        expected = {**spec, **arms[spec["arm"]], "allocation_file": spec["id"] + "/allocation.json"}
        require(
            all(row.get(k) == v for k, v in expected.items()), "case differs from preallocated plan"
        )
    return batch, lock


def load_case(raw, batch, row):
    alloc = pinned(raw / row["allocation_file"], row["allocation_sha256"])
    case = alloc["case"]
    require(
        all(
            case[k] == v
            for k, v in row.items()
            if k not in {"allocation_file", "allocation_sha256"}
        ),
        "case identity differs from pre-issued schedule",
    )
    catalog = batch["native_catalogues"][row["family"]]
    full = pinned(raw / catalog["private_filename"], catalog["archived_json_sha256"])
    reg = NativeGeometryRegistration(alloc["geometry"])
    reg.validate_asset(ROOT)
    require(
        case["visual_id"] == RELEASE + "/" + row["id"]
        and case["visual_seed"] == row["seed"]
        and alloc["plan_sha256"] == PLAN_SHA
        and alloc["runtime_build_sha256"] == batch["runtime_build_sha256"]
        and alloc["selection_sha256"] == batch["selection_sha256"]
        and alloc["cross_readback_sha256"] == batch["gate"]["cross_readback_sha256"]
        and alloc["zero_step_probes_sha256"] == batch["zero_step_probes_sha256"]
        and alloc["catalog"] == catalog
        and alloc["sources_sha256"] == full
        and native.digest(full) == catalog["product_compact_sorted_utf8_sha256"]
        and alloc["component_catalog_sha256"] == runtime.digest(full)
        and alloc["geometry"]
        == batch["geometries"][row["family"]]
        == runtime.geometry_registration(marker_family_id=row["family"])
        and reg.marker_family_id == row["family"]
        and reg.pose_marker.marked_asset_sha256
        == alloc["asset_sha256"]
        == row["asset_sha256"]
        == full[row["asset_path"]]
        and alloc["intent_descriptor"]["stages"] == case["visual_stages_in_order"],
        "foreign live allocation binding",
    )
    check_sources(alloc)
    return alloc, full


def hand_contacts(samples):
    counts = Counter()
    cube, board, both = [], [], []
    for sample in samples:
        seen_cube, seen_board = set(), False
        for pair in {tuple(sorted(pair)) for pair in sample["contact_pairs"]}:
            for hand, obj in (pair, pair[::-1]):
                if hand not in HANDS:
                    continue
                if obj == "object_geom":
                    seen_cube.add(hand)
                elif obj in SUPPORT_GEOMS:
                    seen_board = True
                else:
                    continue
                counts["/".join(pair)] += 1
        if seen_cube:
            cube.append(sample["physics_step"])
        if FINGERS <= seen_cube:
            both.append(sample["physics_step"])
        if seen_board:
            board.append(sample["physics_step"])
    return dict(
        block_hand_or_finger_steps=cube,
        block_both_fingers_steps=both,
        board_or_support_hand_or_finger_steps=board,
        hand_contact_pairs=dict(counts),
    )


def audit_one(directory, row, allocation, allocation_sha):
    evidence = g1_mount_trials.captured_evidence(directory, row, allocation)
    receipt = read(directory / "receipt.json")
    require(
        receipt["batch_sha256"] == allocation_sha
        and all(receipt[k] == v for k, v in evidence.items()),
        "raw acquisition differs from original capture receipt",
    )
    seal = read(directory / "acquisition-seal.json")
    index = pinned(directory / "pixel-index.json", seal["index_sha256"])
    truth = pinned(directory / "offline-truth.json", seal["truth_sha256"])
    run, audit = (
        pinned(directory / "run.json", seal["run_sha256"]),
        pinned(directory / "online-audit.json", seal["audit_sha256"]),
    )
    require(
        index["allocation_sha256"] == truth["allocation_sha256"] == row["allocation_sha256"]
        and truth["episode"] == index["episode"],
        "foreign dense trajectory",
    )
    states = vision.checked_steps(
        truth["samples"], index["episode"], row["asset_sha256"], truth["asset_sha256"]
    )
    geometry = allocation["geometry"]
    frames = {}
    for source in index["frames"]:
        frame = vision.frame_from_row(directory, source, index["episode"], index["scene"], geometry)
        runtime.validate_camera(frame, geometry)
        require(frame.frame_id not in frames, "duplicate acquired frame")
        frames[frame.frame_id] = {
            **source,
            "captured_at": frame.captured_at.isoformat(),
            "sim_time_s": frame.sim_time_s,
        }
    require(
        index["frames"][-1]["physics_step"] == max(states), "trajectory extends beyond terminal"
    )
    by_role = g1_mount_score.role_sources(
        run["frame_roles"],
        list(frames.values()),
        allocation["case"]["visual_stages_in_order"],
        index["episode"],
    )
    phases = g1_mount_score.check_clocks(run, audit, frames, index["episode"])
    proposal_scoring.check_audit(run["actions"], audit)
    passed = proposal_scoring.score_admissions(
        run["actions"], {k: v["checksum_sha256"] for k, v in frames.items()}
    )
    physical = [
        sample_physical_observation(PhysicsStepObservation(**s), proposal_scoring.CRITERIA)
        for s in truth["samples"]
    ]
    outcome = evaluate_evidence(physical, proposal_scoring.CRITERIA)
    windows = proposal_scoring.registered_windows(physical, {s["skill"]: s for s in run["actions"]})
    mass = read(directory / "assembly-reset.json")
    req = read(directory / "reset-observed.json")[1]["parameters"]["requested"]
    require(
        req["object_mass_kg"] == mass["requested_object_mass_kg"] == row["physical_object_mass_kg"]
        and np.allclose(
            mass["after_reset"]["mass_kg"], row["physical_object_mass_kg"], rtol=0, atol=1e-12
        ),
        "reset body assembly differs from registered mass",
    )
    return {
        **evidence,
        "acquired": True,
        "receipt_sha256": sha(directory / "receipt.json"),
        "finished_utc": receipt["finished_utc"],
        "wall_s": receipt["wall_s"],
        "mass": mass,
        "mass_receipt_sha256": sha(directory / "assembly-reset.json"),
        "role_source_counts": {k: len(v) for k, v in by_role.items()},
        "shield_clocks": phases,
        "admitted_stages": passed,
        "stage_status": {s["skill"]: s["status"] for s in run["actions"]},
        "independent_physical_outcome": asdict(outcome),
        "registered_windows": windows,
        "hand_contacts": hand_contacts(truth["samples"]),
    }


def audit_all(plan_file, raw, allocation_sha):
    batch, _ = check_batch(plan_file, raw, allocation_sha)
    cases = []
    for row in batch["cases"]:
        alloc, _ = load_case(raw, batch, row)
        directory = raw / row["id"] / "instance"
        if not (directory / "receipt.json").exists():
            require(
                (directory / "interrupted.json").exists(),
                "no original terminal or interruption receipt",
            )
            cases.append(
                {
                    **row,
                    "acquired": False,
                    "interrupted": read(directory / "interrupted.json"),
                    "interruption_sha256": sha(directory / "interrupted.json"),
                }
            )
            continue
        cases.append(audit_one(directory, row, alloc, allocation_sha))
    completed = [r for r in cases if r["acquired"]]
    for ids in (
        [r["physical_reset"]["episode_id"] for r in completed],
        [r["worker"]["job_id"] for r in completed],
        [r["worker"]["lease_id"] for r in completed],
    ):
        require(len(set(ids)) == len(completed), "registered reset or lease reused")
    require(
        all(
            b["worker"]["acquired_at"] > a["worker"]["released_at"]
            for a, b in zip(completed, completed[1:], strict=False)
        ),
        "overlapping capture leases",
    )
    output = dict(
        schema="g1.development.dual-marker.acquisition.v1",
        allocation_sha256=allocation_sha,
        runtime_build_sha256=batch["runtime_build_sha256"],
        selection_sha256=batch["selection_sha256"],
        cases=cases,
        actual_episodes=len(completed),
        distinct_resets=len(completed),
        actual_dispatched=sum(len(r["action_commands"]) for r in completed),
        worker_label_scope=(
            "Inherited G1 development worker, manifest and task labels. Each case has its own "
            "recorded release, source generation, asset and lease."
        ),
        formal_simulations=0,
        formal_claims=0,
        hardware_actions=0,
        task_model_calls=0,
    )
    write(raw / "acquisition.json", output)
    write(plan_file.with_name("trial-acquisition.public.json"), output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["issue", "capture", "audit"])
    parser.add_argument("plan", type=Path)
    parser.add_argument("raw", type=Path)
    parser.add_argument("allocation_sha256", nargs="?")
    parser.add_argument("case", nargs="?")
    args = parser.parse_args()
    plan, raw = args.plan.resolve(), args.raw.resolve()
    if args.command == "issue":
        issue(plan, raw)
    elif args.command == "capture":
        with exclusive_egl(raw.parent):
            g1_mount_trials.capture(
                plan,
                raw,
                args.allocation_sha256,
                args.case,
                context=check_batch,
                case_reader=load_case,
                episode_factory=episode_with_registered_mass,
            )
    else:
        audit_all(plan, raw, args.allocation_sha256)


if __name__ == "__main__":
    main()
