"""CPU-only readback controls for the G1 marker installation development cohort."""

import copy
import importlib
import importlib.util
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from scripts.graduation.perception_io import sha, write

from cloud_edge_robot_arm.vision.marker_families import PREPARE_ONLY_FAMILY
from tests.test_registered_object_geometry import frame, revised


def api(suffix=""):
    module = "scripts.graduation.g1_mount_score" + suffix
    assert importlib.util.find_spec(module), "G1 independent scorer has not been implemented"
    return importlib.import_module(module)


def test_candidate_pixel_binding_uses_rotated_center_top_and_grasp():
    blind = api("_blind")
    score = api()
    for rotation, offset in ((0, [-0.1, 0, -0.03505]), (1, [0, -0.1, -0.03505])):
        obs, scope = frame(family=PREPARE_ONLY_FAMILY, rotation=rotation)
        geom = scope.to_payload()
        decision = blind.measure_packet(obs, geom)
        estimate = decision["estimate"]
        marker = np.asarray(estimate["marker_center_world_m"])
        expected = marker + offset
        assert estimate["object_center_world_m"] == pytest.approx(expected)
        assert estimate["object_top_center_world_m"] == pytest.approx(expected + [0, 0, 0.035])
        assert decision["servo_grasp_world_m"] == pytest.approx(expected + [0, 0, 0.01])
        assert decision["subpix_depth_patches"] == 5
        actual = dict(
            object_geom_position_m=expected.tolist(),
            object_geom_rotation_row_major=estimate["rotation_to_world"],
            object_half_extent_m=[0.035] * 3,
        )
        residual = score.residuals(decision, actual, geom)
        assert residual["top_mm"] == pytest.approx(0, abs=1e-7)
        assert residual["tcp_mm"] == pytest.approx(0, abs=1e-7)
        with pytest.raises(ValueError, match="grasp"):
            score.residuals({**decision, "servo_grasp_world_m": marker.tolist()}, actual, geom)
        wrong = copy.deepcopy(geom)
        wrong["marker_to_object"][3] = 0.0
        wrong["marker_to_object"][7] = 0.1
        with pytest.raises(ValueError, match="geometry"):
            blind.checked_geometry(wrong)


def test_packet_rejects_wrong_camera_and_separates_id_from_depth_or_missing_pose():
    blind = api("_blind")
    obs, scope = frame(family=PREPARE_ONLY_FAMILY)
    geo = scope.to_payload()
    with pytest.raises(ValueError, match="camera"):
        blind.measure_packet(revised(obs, intrinsics=[201, 201, 159.5, 119.5]), geo)
    for fault, has_id in (("missing", False), ("foreign", False), ("zero_depth", True)):
        packet, _ = frame(family=PREPARE_ONLY_FAMILY, fault=fault)
        reading = blind.measure_packet(packet, geo)
        assert (reading["estimate"]["ids"] == [7]) == has_id
        assert reading["servo_grasp_world_m"] is None
        assert reading["estimate"]["object_top_center_world_m"] is None


def test_blind_reader_rejects_foreign_episode_sha_duplicate_and_labeled_input(tmp_path):
    blind = api("_blind")
    obs, scope = frame(family=PREPARE_ONLY_FAMILY)
    group = tmp_path / "opaque"
    group.mkdir()
    write(group / "0000.json", obs.model_dump(mode="json"))
    row = dict(
        file="0000.json",
        file_sha256=sha(group / "0000.json"),
        frame_id=obs.frame_id,
        checksum_sha256=obs.checksum_sha256,
        physics_step=0,
    )
    bundle = dict(
        episode=obs.episode_id, scene=obs.scene_id, geometry=scope.to_payload(), frames=[row]
    )
    result = blind.read_set(group, bundle)
    assert len(result) == 1 and result[0]["frame_id"] == obs.frame_id
    with pytest.raises(ValueError, match="source|episode"):
        blind.read_set(group, {**bundle, "episode": "elsewhere"})
    with pytest.raises(ValueError, match="SHA256"):
        blind.read_set(group, {**bundle, "frames": [{**row, "file_sha256": "0" * 64}]})
    with pytest.raises(ValueError, match="duplicate"):
        blind.read_set(group, {**bundle, "frames": [row, row]})
    with pytest.raises(ValueError, match="fields"):
        blind.read_set(group, {**bundle, "frames": [{**row, "label": "GRASP/POST"}]})


def test_stage_frame_identity_retains_roles_without_recounting_or_importing_terminal_images():
    score = api()
    origin = datetime(2026, 11, 24, tzinfo=UTC)

    def source(fid, step, label):
        stamp = (origin + timedelta(seconds=step / 240)).isoformat()
        return dict(
            frame_id=fid,
            checksum_sha256="sha-" + fid,
            physics_step=step,
            captured_at=stamp,
            label=label,
            sim_time_s=step / 240,
        )

    frames = [
        source("a", 10, "APPROACH/POST"),
        source("b", 34, "GRASP/POST"),
        source("c", 34, "terminal"),
    ]

    def role(f, label, acquired):
        return {
            **f,
            "label": label,
            "acquired_for_this_role": acquired,
            "episode_id": "unit",
            "checked_at": f["captured_at"],
        }

    roles = [
        role(frames[0], "APPROACH/POST", True),
        role(frames[0], "GRASP/PRE", False),
        role(frames[0], "GRASP/PRE_conditions", False),
        role(frames[1], "GRASP/POST", True),
        role(frames[1], "GRASP/POST_Shield", False),
        role(frames[2], "terminal", True),
    ]
    by_stage = score.role_sources(roles, frames, ["APPROACH", "GRASP", "LIFT"], "unit")
    assert by_stage["APPROACH"] == ["a"]
    assert by_stage["GRASP"] == ["a", "b"]
    assert by_stage["LIFT"] == []
    with pytest.raises(ValueError, match="role"):
        score.role_sources(
            [*roles[:-1], {**roles[-1], "episode_id": "other"}],
            frames,
            ["APPROACH", "GRASP", "LIFT"],
            "unit",
        )
    with pytest.raises(ValueError, match="role"):
        score.role_sources(
            [*roles[:-1], {**roles[-1], "captured_at": frames[0]["captured_at"]}],
            frames,
            ["APPROACH", "GRASP", "LIFT"],
            "unit",
        )


def test_zero_coverage_empty_denominator_and_unobserved_phase_endpoints_are_distinct():
    score = api()
    assert score.phase_sampling({"status": "NOT_RUN"}, [])["sampling"] == "NOT_REACHED"
    entered = {"status": "STOPPED", "entered_step": 10, "end_step": 10, "dispatched": False}
    assert score.phase_sampling(entered, [10])["sampling"] == "ENTERED_NO_DISPATCH"
    moved = {
        **entered,
        "end_step": 34,
        "dispatch_step": 10,
        "executor_entered": True,
        "dispatched": True,
        "backend_return_step": 34,
    }
    edges = score.phase_sampling(moved, [10, 10, 34])
    assert edges["sampling"] == "ENDPOINTS_ONLY" and edges["distinct_steps"] == 2
    assert edges["max_gap_sim_s"] == pytest.approx(0.1)
    missing = score.phase_sampling(moved, [10, 18, 26])
    assert missing["controller_end_observed"] is False
    assert missing["max_unsampled_interval_steps"] == 8
    assert score.phase_sampling(moved, [])["sampling"] == "NO_FRAME"
    cov = score.pixel_summary([])
    assert cov["frames"] == 0 and cov["pose_fraction"] is None and cov["top_p90_mm"] is None


def test_unknown_slots_keep_paired_ITT_bounds_and_wilson_at_placement_grain():
    score = api()
    cases = []
    for group, results in (
        ("m01", (False, True)),
        ("m02", (True, False)),
        ("m03", (False, False)),
        ("m04", (True, None)),
    ):
        for arm, outcome in zip(("original", "selected"), results, strict=True):
            cases.append(
                dict(group=group, arm=arm, joint_success=outcome, acquired=outcome is not None)
            )
    rates, pairs = score.outcomes(cases, "joint_success")
    assert rates["original"]["successes"] == 2 and rates["original"]["allocated"] == 4
    assert rates["original"]["wilson95"] == pytest.approx([0.150036, 0.849964], abs=1e-6)
    assert rates["selected"]["known_failures"] == 2 and rates["selected"]["unknown"] == 1
    assert rates["selected"]["allocation_rate_bounds"] == [0.25, 0.5]
    assert rates["selected"]["wilson95"] is None
    assert pairs["allocation_difference_bounds"] == [-0.25, 0.0]
    assert (
        pairs["paired_success_difference"] is None and pairs["conservative_difference_ci95"] is None
    )
    cases[-1].update(acquired=True, joint_success=True)
    rates, pairs = score.outcomes(cases, "joint_success")
    assert pairs["paired_success_difference"] == 0
    assert pairs["conservative_difference_ci95"][0] < 0 < pairs["conservative_difference_ci95"][1]
    with pytest.raises(ValueError, match="paired"):
        score.outcomes(cases[:-1], "joint_success")


def test_actual_feedback_clock_must_join_its_episode_action_step_and_shield():
    score = api()
    source = {"frame_id": "id", "checksum_sha256": "bytes", "physics_step": 24}
    action = {
        "skill": "APPROACH",
        "entered_step": 16,
        "end_step": 24,
        "dispatch_step": 16,
        "executor_entered": True,
    }
    ctx = {
        "skill": "APPROACH",
        "frame_id": "id",
        "checksum_sha256": "bytes",
        "episode": "ep",
        "origin": 16,
        "absolute": 24,
        "relative": 8,
        "phase": "FEEDBACK",
        "binding_sha256": "binding",
        "step_id": "step-2",
    }
    verdict = {
        "phase": "FEEDBACK",
        "step_id": "step-2",
        "frame_id": "id",
        "shield": {
            "allowed": False,
            "decision": "DENY",
            "limiting_rule": "BUDGET",
            "limited_parameters": None,
            "original_parameters": None,
        },
    }
    trace = {
        "actions": [action],
        "action_clock_contexts": [ctx],
        "grounding_contracts": [{"skill": "APPROACH", "binding_sha256": "binding"}],
    }
    result = score.check_clocks(trace, [verdict], {"id": source}, "ep")
    assert result["APPROACH"]["FEEDBACK"]["interventions"] == 1
    for changed in ({"episode": "elsewhere"}, {"relative": 0}, {"binding_sha256": "wrong"}):
        with pytest.raises(ValueError, match="clock"):
            score.check_clocks(
                {**trace, "action_clock_contexts": [{**ctx, **changed}]},
                [verdict],
                {"id": source},
                "ep",
            )
    with pytest.raises(ValueError, match="clock"):
        score.check_clocks(trace, [], {"id": source}, "ep")


def test_anonymous_pack_and_sealed_role_join_without_any_truth_or_run_files(tmp_path):
    score = api()
    from scripts.graduation.perception_io import read

    raw = tmp_path / "instance"
    raw.mkdir()
    files = raw / "frames"
    files.mkdir()
    obs, scope = frame(family=PREPARE_ONLY_FAMILY)
    write(files / "0000.json", obs.model_dump(mode="json"))
    src = dict(
        frame_id=obs.frame_id,
        checksum_sha256=obs.checksum_sha256,
        label="GRASP/PRE",
        file="frames/0000.json",
        file_sha256=sha(files / "0000.json"),
        physics_step=0,
    )
    write(
        raw / "pixel-index.json",
        dict(frames=[src], episode=obs.episode_id, scene=obs.scene_id, allocation_sha256="issued"),
    )
    write(raw / "acquisition-seal.json", {"index_sha256": sha(raw / "pixel-index.json")})
    root = tmp_path / "anonymous"
    root.mkdir()
    token, bundle = score.pack_case(root, raw, "issued", scope.to_payload())
    assert "/instance" not in str(bundle) and "GRASP" not in str(bundle)
    write(root / "index.json", {token: bundle})
    out = tmp_path / "blind-results"
    score.blind_process(root / "index.json", out, tmp_path / "process.json")
    score.join_packet_sources(raw, token, out)
    linked = read(raw / "decisions.json")["decisions"]
    assert len(linked) == 1 and linked[0]["label"] == "GRASP/PRE"
    assert linked[0]["estimate"]["ids"] == [7]
    assert read(raw / "decision-seal.json")["blind_seal_sha256"] == sha(out / "seal.json")


def test_online_preview_grasp_compares_to_independent_pixel_object_not_marker_center():
    score = api()
    obs, scope = frame(family=PREPARE_ONLY_FAMILY)
    geom = scope.to_payload()
    px = api("_blind").measure_packet(obs, geom)
    px.update(frame_id=obs.frame_id, checksum_sha256=obs.checksum_sha256)
    track = dict(
        observation_id=obs.frame_id,
        observation_checksum_sha256=obs.checksum_sha256,
        episode_id=obs.episode_id,
        marker_family_id=PREPARE_ONLY_FAMILY,
        asset_sha256=geom["pose_marker"]["marked_asset_sha256"],
        camera_to_world=geom["camera"]["camera_to_world"],
        calibration_version=obs.calibration_version,
    )
    preview = dict(
        status="DERIVED",
        track=track,
        object_center_world_m=px["estimate"]["object_center_world_m"],
        rotation_object_to_world=px["estimate"]["rotation_to_world"],
        grasp_tcp_world_m=px["servo_grasp_world_m"],
    )
    checked = score.check_preview(preview, px, geom, obs.episode_id)
    assert checked == pytest.approx(0, abs=1e-9)
    with pytest.raises(ValueError, match="grasp"):
        score.check_preview(
            {**preview, "grasp_tcp_world_m": px["estimate"]["marker_center_world_m"]},
            px,
            geom,
            obs.episode_id,
        )


def test_real_pose_counterfactual_wrong_side_and_marker_center_rejected_against_independent_truth():
    score = api()
    for rotation in (0, 1):
        obs, scope = frame(family=PREPARE_ONLY_FAMILY, rotation=rotation)
        g = scope.to_payload()
        px = api("_blind").measure_packet(obs, g)
        px.update(frame_id=obs.frame_id, checksum_sha256=obs.checksum_sha256)
        e = px["estimate"]
        truth = dict(
            object_geom_position_m=e["object_center_world_m"],
            object_geom_rotation_row_major=e["rotation_to_world"],
            object_half_extent_m=[0.035] * 3,
        )
        tr = dict(
            observation_id=obs.frame_id,
            observation_checksum_sha256=obs.checksum_sha256,
            episode_id=obs.episode_id,
            marker_family_id=PREPARE_ONLY_FAMILY,
            asset_sha256=g["pose_marker"]["marked_asset_sha256"],
            camera_to_world=g["camera"]["camera_to_world"],
            calibration_version=obs.calibration_version,
        )
        pv = dict(
            status="DERIVED",
            track=tr,
            object_center_world_m=e["object_center_world_m"],
            rotation_object_to_world=e["rotation_to_world"],
            grasp_tcp_world_m=px["servo_grasp_world_m"],
        )
        report = score.preview_counterfactuals(pv, px, g, truth, obs.episode_id)
        assert report["online_grasp_error_mm"] == pytest.approx(0, abs=1e-8)
        assert report["negative_controls"]["marker_center_as_grasp"]["rejected"]
        assert report["negative_controls"]["wrong_attachment_as_grasp"]["rejected"]
        assert report["negative_controls"]["wrong_attachment_as_grasp"][
            "error_to_true_grasp_mm"
        ] == pytest.approx(141.421356, abs=1e-3)


def test_first_rejected_control_frame_is_not_same_step_terminal_capture_or_pre_handoff():
    score = api()

    def packet(name, label, step, good):
        return {
            "frame_id": name,
            "checksum_sha256": "bytes-" + name,
            "label": label,
            "physics_step": step,
            "captured_at": "2026-11-24T04:00:00+00:00",
            "sim_time_s": step / 240,
            "estimate": {
                "ids": [7] if good else [],
                "status": "OBSERVED" if good else "UNKNOWN",
                "reason": "ok" if good else "known_marker_not_observed",
                "marker_center_optical_depth_m": 1.33 if good else None,
            },
            "subpix_depth_patches": 5 if good else 0,
            "servo_grasp_world_m": [0, 0, 0.05] if good else None,
        }

    packets = {
        p["frame_id"]: p
        for p in (
            packet("p", "registration-handoff", 120, True),
            packet("f0", "MOVE_ABOVE/feedback", 128, True),
            packet("f1", "MOVE_ABOVE/feedback", 136, False),
            packet("end", "terminal", 136, True),
        )
    }
    run = {
        "actions": [
            {
                "skill": "MOVE_ABOVE",
                "pre": {"frame_id": "p", "checksum_sha256": "bytes-p"},
                "servo_terminal_reason": "ValueError:servo registered marker geometry unavailable",
            }
        ],
        "stop": {
            "skill": "MOVE_ABOVE",
            "phase": "CONTROLLER",
            "physics_step": 136,
            "reason": "controller: VISUAL_SERVO_REJECTED",
        },
    }
    audit = [
        {
            "phase": "servo",
            "skill": "MOVE_ABOVE",
            "visual_samples": [{"observation_id": "f0", "checksum_sha256": "bytes-f0"}],
        }
    ]
    result = score.first_feedback_refusal(run, audit, packets)
    assert [
        result[k]["frame_id"]
        for k in (
            "pre_admission_source",
            "previous_accepted_feedback",
            "rejected_feedback",
            "separate_terminal_capture",
        )
    ] == ["p", "f0", "f1", "end"]
    assert result["rejected_feedback"]["subpix_reason"] == "known_marker_not_observed"
    assert result["separate_terminal_capture"]["grasp_usable"]
