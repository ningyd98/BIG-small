"""Independent development readback for stage preparation and negative original-time controls."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import timedelta, timezone
from functools import partial
from pathlib import Path

import numpy as np
from qualify_archive import checked_time, frame_key, utc
from qualify_native import OLD, checked, dump, frozen_inputs, sha


def expect_failure(call):
    try:
        call()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("negative readback control unexpectedly passed")


def history(repo):
    from scripts.graduation import binding_score, g1_dual_pixel_readback
    from scripts.graduation.g1_formal_runtime import bind_scene

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    results = []
    folder = repo / OLD
    manifest = json.loads((folder / "read-input.json").read_bytes())
    for mm, seals in zip((0, 7), manifest, strict=True):
        case = folder / f"offset-{mm}"
        run = checked(case / "run.json", seals["run.json"])
        audit = checked(case / "audit.json", seals["audit.json"])
        allocation = checked(case / "allocation.json", seals["allocation.json"])
        index = checked(case / "frame-index.json", seals["frame-index.json"])
        roles = {r["label"]: r["frame_id"] for r in run["frame_roles"]}
        frames = {}
        with bind_scene(allocation["case"]["scene_id"]):
            for fid, key in index.items():
                raw = RGBDObservation.model_validate(checked(case / key["file"], key["sha256"]))
                assert raw.frame_id == fid
                measured = g1_dual_pixel_readback.dual_read(raw, allocation["geometry"])
                frames[fid] = {**measured, **frame_key(raw)}
        issues = binding_score.verify_issues(audit, frames)
        by_skill = {stage["skill"]: stage for stage in run["actions"]}
        samples = []
        for event in [r for r in audit if r.get("phase") == "servo"]:
            skill = event["skill"]
            ref = frames[roles[f"{skill}/servo_reference"]]
            for sample in event["visual_samples"]:
                frame = frames[sample["observation_id"]]
                binding_score.verify_sample(issues, skill, sample, frame)
                reason, residual = None, None
                if skill in ("MOVE_TO_REGION", "PLACE"):
                    reason = "initial color-reference evaluation time absent in run-01"
                else:
                    predicted = np.array([by_skill[skill]["selected"][k] for k in "xyz"])
                    if skill in ("MOVE_ABOVE", "APPROACH"):
                        predicted += np.subtract(frame["tcp_m"], ref["tcp_m"])
                        predicted += binding_score.offset_delta(issues[skill][0], ref, frame)
                    actual = [sample["target_pose"][k] for k in "xyz"]
                    np.testing.assert_allclose(actual, predicted, rtol=0, atol=1e-10)
                    residual = float(1000 * np.linalg.norm(actual - predicted))
                samples.append(
                    dict(
                        skill=skill,
                        central_and_selected_checked=True,
                        endpoint_mm=residual,
                        missing_endpoint_cause=reason,
                        stage_pre_shield_allowed=by_skill[skill]["physical_pre_shield"],
                    )
                )
        forged = copy.deepcopy(audit)
        issue = next(r for r in forged if "development_grasp_binding" in r)
        issue["development_grasp_binding"]["selection"]["spec"]["offset_object_m"][0] += 0.007
        tamper = expect_failure(partial(binding_score.verify_issues, forged, frames))
        results.append(
            dict(
                offset_mm=mm,
                raw_packets=len(frames),
                native_preparation_count=len(issues),
                component_samples=samples,
                prep_stages=[
                    dict(
                        skill=s["skill"],
                        central_recipe=s["central_recipe"],
                        selected=s["selected"],
                        shield_allowed=s["physical_pre_shield"],
                        native_binding_sha256=s["native_binding_sha256"],
                    )
                    for s in run["actions"]
                ],
                tampered_binding_rejection=tamper,
                actual_controller_feedback=0,
                physical_steps=run["total_physics_steps"],
            )
        )
    return results


def clock_controls(folder, seals):
    from qualify_archive import archived_color
    from scripts.graduation.g1_formal_runtime import bind_scene

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.owner_registration import RegisteredCollectionStepBindingV2
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    results = []
    for key, manifest in seals["cases"].items():
        base = folder / ("offset-" + key)
        run = checked(base / "run.json", manifest["run.json"])
        source = run["color_init_event"]
        record = next(
            r
            for r in checked(base / "frames.json", manifest["frames.json"])
            if r["role"] == "color_reference"
        )
        raw = RGBDObservation.model_validate(checked(base / record["file"], record["file_sha256"]))
        lease = source["lease_id"]
        binding = next(
            r
            for r in checked(base / "audit.json", manifest["audit.json"])
            if "development_grasp_binding" in r
        )
        limit = utc(binding["binding"]["prepared"]["valid_until"])
        tm = utc(source["evaluated_at"])
        local = tm.astimezone(timezone(timedelta(hours=8)))
        tests = {
            "missing_original_read_time": {"evaluated_at": None},
            "wrong_frame": {"frame_id": "foreign-frame"},
            "wrong_role": {"role": "current.feedback"},
            "wrong_lease": {"lease_id": "foreign-lease"},
            "wrong_timezone": {"evaluated_at": local.isoformat()},
            "past_freshness_or_deadline": {
                "evaluated_at": (limit + timedelta(seconds=1)).isoformat()
            },
            "captured_as_evaluated": {"evaluated_at": raw.captured_at.isoformat()},
        }
        rejected = {
            n: expect_failure(
                partial(
                    checked_time,
                    frame_key(raw),
                    {**source, **fields},
                    "color.initial",
                    lease,
                    limit,
                )
            )
            for n, fields in tests.items()
        }
        rejected["changed_packet_seal"] = expect_failure(
            partial(checked, base / record["file"], "0" * 64)
        )
        asserted_shield = binding["grounded_step"]["parameters"]["target_pose"]
        native_receipt = RegisteredCollectionStepBindingV2.from_payload(binding["binding"])
        if native_receipt.digest() != binding["binding_sha256"]:
            raise ValueError("native owner receipt hash differs")
        pre = next(
            e
            for e in checked(base / "audit.json", manifest["audit.json"])
            if e.get("phase") == "PRE" and "shield" in e
        )
        if asserted_shield != pre["target_pose"]:
            raise ValueError("independent PRE comparison failed")
        alloc = checked(base / "allocation.json", manifest["allocation.json"])
        with bind_scene(alloc["case"]["scene_id"]):
            tracker = archived_color(raw, alloc["geometry"], source, lease, limit.isoformat())
            region, reason = measure_servo_region(raw, tracker)
        if (
            reason
            or not region
            or not np.array_equal(region["center"], run["region_reference"]["center"])
        ):
            raise ValueError("archived region center differs from online measurement")
        sample = run["component_sample"]
        frame_index = checked(base / "frames.json", manifest["frames.json"])
        pair = {
            item["role"]: RGBDObservation.model_validate(
                checked(base / item["file"], item["file_sha256"])
            )
            for item in frame_index
            if item["role"] in ("MOVE_ABOVE/component-sample", "MOVE_ABOVE/servo_reference")
        }
        measured = pair["MOVE_ABOVE/component-sample"]
        reference = pair["MOVE_ABOVE/servo_reference"]
        n0, n1, n2, n3 = sample["perf_counter_ns"]
        if not (
            sample["sample"]["checksum_sha256"] == measured.checksum_sha256
            and sample["reference"] == reference.frame_id
            and sample["sample"]["observation_id"] == measured.frame_id
            and utc(binding["binding_now"])
            <= reference.captured_at
            <= utc(sample["reference_init_utc"][0])
            <= utc(sample["reference_init_utc"][1])
            <= utc(sample["sample_utc"][0])
            <= measured.captured_at
            <= utc(sample["sample_utc"][1])
            < limit
            and n0 <= n1 <= n2 <= n3
            and (n3 - n0) / 1e6 == sample["capture_sample_ik_ms"]
        ):
            raise ValueError("independent sample frame, timestamps or monotonic window differs")
        results.append(
            {
                "offset_mm": int(key),
                "rejections": rejected,
                "shield_target_matched": True,
                "native_owner_receipt_hash_valid": True,
                "recorded_region_center_identical": True,
                "sample_timestamps_and_monotonic_duration_verified": True,
            }
        )
    return results


def case_isolation(folder, packages, supplementary):
    frame_sets = []
    leases = []
    tickets = []
    counts = []
    for mm, manifest in zip((0, 7), packages, strict=True):
        case = folder / f"offset-{mm}"
        run = checked(case / "run.json", manifest["run.json"])
        audit = checked(case / "audit.json", manifest["audit.json"])
        issues = [a for a in audit if "development_grasp_binding" in a]
        local_frames = {r["frame_id"] for r in run["frame_roles"]}
        (scope,) = {a["development_grasp_binding"]["selection_sha256"] for a in issues}
        (lease,) = {a["identity"]["lease_id"] for a in issues}
        local_issues = {a["binding_sha256"]: a for a in issues}
        if not all(
            a["development_grasp_binding"]["selection"]["spec"]["tangent_mm"] == mm
            and a["observation_id"] in local_frames
            for a in issues
        ):
            raise ValueError("prepared issue belongs to another offset")
        if supplementary:
            samples = [run["component_sample"]["sample"]]
            local_episode = issues[0]["identity"]["episode_id"]
            if not all(
                e["episode"] == local_episode for e in run["operations"] if e["kind"] == "CAPTURE"
            ):
                raise ValueError("operation observer mixed episodes")
        else:
            samples = [s for a in audit if a.get("phase") == "servo" for s in a["visual_samples"]]
        for s in samples:
            signed = s["development_grasp_binding"]
            if (
                signed["selection_sha256"] != scope
                or signed["issued_sha256"] not in local_issues
                or s["observation_id"] not in local_frames
            ):
                raise ValueError("callback sample refers to another attempt")
        frame_sets.append(local_frames)
        leases.append(lease)
        tickets.append(scope)
        counts.append(
            dict(
                offset_mm=mm,
                source_frame_count=len(local_frames),
                native_issue_count=len(issues),
                bound_sample_count=len(samples),
                active_lease_id=lease,
                original_selection_sha256=scope,
            )
        )
    if frame_sets[0] & frame_sets[1] or len(set(leases)) != 2 or len(set(tickets)) != 2:
        raise ValueError("cross-case source, lease or selection alias")
    return dict(counts=counts, disjoint_source_frames=True, disjoint_lease_and_selection=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("repo", type=Path)
    cli.add_argument("folder", type=Path)
    cli.add_argument("seal")
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    verified = frozen_inputs(args.repo)
    seals = checked(args.folder / "sealed-inputs.json", args.seal)
    dump(
        args.output,
        dict(
            frozen_input_checks=verified,
            old_stage_preparation=history(args.repo),
            original_time_and_sha_negative_controls=clock_controls(args.folder, seals),
            case_isolation=dict(
                old=case_isolation(
                    args.repo / OLD,
                    json.loads((args.repo / OLD / "read-input.json").read_bytes()),
                    False,
                ),
                current=case_isolation(args.folder, list(seals["cases"].values()), True),
            ),
            reader_sha256=sha(Path(__file__)),
        ),
    )
