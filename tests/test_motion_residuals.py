"""SOFTWARE_ONLY point-motion input reconstruction; never motion certification."""

from __future__ import annotations

import base64
import hashlib
import io
import struct
from dataclasses import asdict, replace
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from cloud_edge_robot_arm.research import raw_episode_v3 as raw
from cloud_edge_robot_arm.research.risk_sources import (
    RawCaseRegistration,
    RiskSourceRegistration,
    required_source_paths,
)
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration
from tests.test_raw_episode_v3 import NOW, SHA, fixture, hash_payload

ROOT = Path(__file__).resolve().parents[1]
ASSET = "assets/robots/franka_panda/scene_pose_marker_color_v2.xml"


def api():
    return import_module("cloud_edge_robot_arm.research.motion_residuals")


def graph(*, predecessor=True, mapped=True, observed_depth_change=False, rotation=False):
    """Extend the existing complete software graph with four recorded action steps.

    The object returns to its initial point, so endpoint-only reconstruction
    misses the middle 2 mm excursion. No physics engine or renderer is used.
    """
    envelope, records = fixture()
    asset = (ROOT / ASSET).read_bytes()
    asset_hash = hashlib.sha256(asset).hexdigest()
    identity = replace(
        envelope.identity,
        asset_hash=asset_hash,
        source_hashes={**dict(envelope.identity.source_hashes), ASSET: asset_hash},
    )
    descriptor = replace(envelope.clock_descriptor, utc_uncertainty_ns=1000 if mapped else None)

    def pair(ns):
        return raw.ClockPairV3(
            identity.clock_domain_id,
            descriptor.digest(),
            ns + 1,
            ns,
            NOW + timedelta(microseconds=ns // 1000),
            ns + 100,
        )

    intervals = [
        replace(
            item,
            identity=identity,
            start=pair(item.start.mono_before_ns),
            end=pair(item.end.mono_before_ns) if item.end else None,
        )
        for item in records.intervals
    ]
    physical = [replace(item, identity=identity) for item in records.physics]
    for n in range(122, 125):
        previous = physical[-1]
        snapshot = {**dict(previous.post_state_payload), "physics_step": n, "sim_time_s": n / 240}
        snapshot["object_geom_position_m"] = [0.2, 0.102 if n == 122 else 0.1, 0.04]
        snapshot["object_position_m"] = snapshot["object_geom_position_m"]
        snapshot["object_geom_rotation_row_major"] = (
            [0, 0, 1, 0, 1, 0, -1, 0, 0] if rotation and n == 122 else [1, 0, 0, 0, 1, 0, 0, 0, 1]
        )
        base = 211_000_000 + (n - 121) * 1_000_000
        for kind, suffix, t0, t1, n1 in (
            ("CONTROL_APPLY", "control", base + 1000, base + 2000, n - 1),
            ("PHYSICS_STEP", "step", base + 3000, base + 90_000, n),
        ):
            intervals.append(
                raw.RawIntervalV3(
                    f"{suffix}-{n}",
                    1,
                    identity,
                    kind,
                    pair(t0),
                    pair(t1),
                    n - 1,
                    n1,
                    (n - 1) / 240,
                    n1 / 240,
                    "COMPLETE",
                    None,
                )
            )
        physical.append(
            replace(
                previous,
                physics_step=n,
                previous_state_hash=hash_payload(dict(previous.post_state_payload)),
                post_state_payload=snapshot,
                control_payload={
                    **dict(previous.control_payload),
                    "physics_step": n,
                    "sim_time_s": (n - 1) / 240,
                },
                physics_interval_id=f"step-{n}",
                control_interval_id=f"control-{n}",
            )
        )
    intervals = [
        replace(item, end_step=124, end_sim_time_s=124 / 240)
        if item.interval_id == "attempt"
        else replace(
            item, start_step=124, end_step=124, start_sim_time_s=124 / 240, end_sim_time_s=124 / 240
        )
        if item.interval_id == "acq-after"
        else item
        for item in intervals
    ]
    frames = []
    stream = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(stream, format="PNG")
    for frame in records.frames:
        step = 120 if frame.acquisition_id == "before" else 124
        observation = RGBDObservation.model_validate(
            {
                **dict(frame.observation_payload),
                "width": 1,
                "height": 1,
                "intrinsics": [1, 1, 0, 0],
                "sim_time_s": step / 240,
                "rgb_png_base64": base64.b64encode(stream.getvalue()).decode(),
                "depth_float32_base64": base64.b64encode(struct.pack("<f", 0.515625)).decode(),
                "valid_mask_base64": base64.b64encode(b"\x01").decode(),
                "checksum_sha256": "",
            }
        )
        camera = {**dict(frame.camera_state_payload), "sim_time_s": step / 240}
        camera_hash = raw._camera_hash(camera)
        frames.append(
            replace(
                frame,
                identity=identity,
                observation_payload=observation.model_dump(mode="json"),
                camera_state_payload=camera,
                joined_physics_observation_hash=hash_payload(
                    dict(physical[step - 1].post_state_payload)
                ),
                pass_state_hashes=(camera_hash,) * 3,
                file_hashes={
                    f"frames/{frame.acquisition_id}/{key}": hashlib.sha256(value).hexdigest()
                    for key, value in (
                        ("rgb.png", stream.getvalue()),
                        ("depth.f32", base64.b64decode(observation.depth_float32_base64)),
                        ("mask.u8", b"\x01"),
                    )
                },
            )
        )
    if predecessor:
        template = frames[0]
        ns = 11_891_000
        intervals.append(
            raw.RawIntervalV3(
                "acq-predecessor",
                1,
                identity,
                "ACQUISITION",
                pair(ns),
                pair(ns + 8000),
                119,
                119,
                119 / 240,
                119 / 240,
                "COMPLETE",
                None,
            )
        )
        observation = RGBDObservation.model_validate(
            {
                **dict(template.observation_payload),
                "observation_id": "predecessor",
                "frame_id": "predecessor",
                "sim_time_s": 119 / 240,
                "captured_at": (NOW + timedelta(microseconds=ns // 1000)).isoformat(),
                "depth_float32_base64": base64.b64encode(
                    struct.pack(
                        "<f",
                        0.5 if observed_depth_change else 0.515625,
                    )
                ).decode(),
                "checksum_sha256": "",
            }
        )
        camera = {**dict(template.camera_state_payload), "sim_time_s": 119 / 240}
        camera_hash = raw._camera_hash(camera)
        previous = replace(
            template,
            acquisition_id="predecessor",
            interval_id="acq-predecessor",
            observation_payload=observation.model_dump(mode="json"),
            camera_state_payload=camera,
            joined_physics_observation_hash=hash_payload(dict(physical[118].post_state_payload)),
            pass_state_hashes=(camera_hash,) * 3,
            file_hashes={
                f"frames/predecessor/{key}": hashlib.sha256(value).hexdigest()
                for key, value in (
                    ("rgb.png", stream.getvalue()),
                    ("depth.f32", base64.b64decode(observation.depth_float32_base64)),
                    ("mask.u8", b"\x01"),
                )
            },
        )
        frames.insert(0, previous)
    action = replace(
        records.actions[0],
        identity=identity,
        returned_result={
            **dict(records.actions[0].returned_result),
            "details": {"physics_steps": 4},
        },
    )
    joins = tuple(
        replace(
            join,
            identity=identity,
            checksum_sha256=next(
                f for f in frames if f.acquisition_id == join.acquisition_id
            ).observation_payload["checksum_sha256"],
        )
        for join in records.joins
    )
    groups = [
        intervals,
        physical,
        [replace(records.commands[0], identity=identity)],
        [action],
        frames,
        list(joins),
    ]
    seq = 0
    numbered = []
    for group in groups:
        rows = []
        for item in group:
            seq += 1
            rows.append(replace(item, record_seq=seq))
        numbered.append(tuple(rows))
    records = raw.RawEpisodeRecordsV3(*numbered)
    envelope = replace(
        envelope,
        identity=identity,
        clock_descriptor=descriptor,
        terminal_state_payload=physical[-1].post_state_payload,
        allocated_acquisition_ids=tuple(frame.acquisition_id for frame in frames),
        original_file_hashes={k: v for frame in frames for k, v in frame.file_hashes.items()},
    )
    marker = PoseMarkerRegistration(7, 0.045, asset_hash)
    case = RawCaseRegistration(
        "case-1",
        "software-case",
        "CED_PILOT_RAW_V2",
        {},
        {},
        {},
        {"physics_steps": 124, "commands": 1, "actions": 1, "frames": len(frames)},
        marker_registration=marker,
    )
    registration = RiskSourceRegistration(
        Path("/tmp/software-motion"),
        ROOT,
        {**{name: SHA for name in required_source_paths()}, ASSET: asset_hash},
        (case,),
        CompletionCriteria("object", "target_region"),
    )
    return registration, envelope, records, asset


def prepare(values):
    registration, envelope, records, asset = values
    return api().prepare_point_motion_residuals(
        registration,
        "case-1",
        envelope,
        records,
        marked_asset_xml=asset,
    )


def test_middle_motion_uses_all_actual_steps_and_original_command_range():
    values = graph()
    view = raw.validate_raw_episode_v3(values[1], values[2])
    assert view.status == "COMPLETE", view.reasons
    result = prepare(values)
    row = result.rows[0]
    assert row.status == "AVAILABLE"
    assert row.sampled_max_secant_upper_m_s == pytest.approx(0.002 / 0.0009129)
    assert row.motion_residual_m_s == pytest.approx(0.002 / 0.0009129)
    assert row.sampled_segments == 4
    assert (row.start_step, row.end_step) == (120, 124)
    assert (row.command_seq_start, row.command_seq_end) == (1, 2)
    assert row.observation_id == "before" and row.previous_observation_id == "predecessor"
    assert row.original_expected_duration_s == 10
    assert result.source_kind == "SOFTWARE_ONLY"
    assert result.scope == "CALIBRATION_INPUT" and result.continuous_motion == "NOT_CERTIFIED"
    assert result.actual_source_status == "UNKNOWN"


def test_observable_speed_comes_from_prior_online_frames_only():
    result = prepare(graph(observed_depth_change=True))
    row = result.rows[0]
    # Exact binary32 depth difference, 88.109 ms measured acquisition interval.
    observed = 0.015625 / 0.088109
    assert row.observed_motion_m_s == pytest.approx(observed)
    assert row.motion_residual_m_s == pytest.approx(0.002 / 0.0009129 - observed)


def test_rotation_moves_registered_marker_point_without_origin_motion():
    result = prepare(graph(rotation=True))
    row = result.rows[0]
    # Registered marker top is 35.05 mm above box origin; 90 degrees about y.
    distance = (0.03505**2 + 0.03505**2 + 0.002**2) ** 0.5
    assert row.sampled_max_secant_upper_m_s == pytest.approx(distance / 0.0009129)


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"predecessor": False}, "previous_online_acquisition_unavailable"),
        ({"mapped": False}, "utc_monotonic_mapping_unavailable"),
    ],
)
def test_missing_evidence_retains_unavailable_action_denominator(options, reason):
    result = prepare(graph(**options))
    assert len(result.rows) == result.allocated_actions == 1
    assert result.available_rows == 0
    assert result.rows[0].motion_residual_m_s is None
    assert reason in result.rows[0].reasons


def test_missing_physics_cannot_shorten_actual_horizon_or_supply_zero():
    registration, envelope, records, asset = graph()
    records = replace(records, physics=tuple(p for p in records.physics if p.physics_step != 122))
    result = prepare((registration, envelope, records, asset))
    assert result.raw_status != "COMPLETE"
    assert result.available_rows == 0 and len(result.rows) == 1
    assert result.rows[0].motion_residual_m_s is None
    assert "raw_graph_not_complete" in result.rows[0].reasons


def test_frozen_criteria_are_detached_and_sampling_threshold_is_not_relaxed():
    registration, envelope, records, asset = graph()
    lower = [-0.85, -0.85, 0]
    criteria = replace(registration.criteria, workspace_min_m=lower, max_sample_gap_s=0.001)
    registration = replace(registration, criteria=criteria)
    result = prepare((registration, envelope, records, asset))
    lower[0] = 100
    assert asdict(result.criteria) == {**asdict(criteria), "workspace_min_m": (-0.85, -0.85, 0)}
    assert "physics_sample_gap_exceeds_original_criterion" in result.rows[0].reasons
    assert result.rows[0].motion_residual_m_s is None


def test_unregistered_asset_bytes_cannot_select_an_arbitrary_reference_point():
    registration, envelope, records, asset = graph()
    result = prepare((registration, envelope, records, asset + b" "))
    assert result.available_rows == 0
    assert "marked_asset_bytes_mismatch" in result.rows[0].reasons
    assert result.rows[0].motion_residual_m_s is None


def test_unavailable_raw_row_keeps_original_horizon_and_command_denominator():
    registration, envelope, records, asset = graph()
    records = replace(records, physics=tuple(p for p in records.physics if p.physics_step != 122))
    result = prepare((registration, envelope, records, asset))
    row = result.rows[0]
    assert (row.start_step, row.end_step) == (120, 124)
    assert (row.command_seq_start, row.command_seq_end) == (1, 2)
    assert row.original_expected_duration_s == 10
    assert row.motion_residual_m_s is None


@pytest.mark.parametrize("field", ["max_sample_gap_s", "hold_s", "placed_stable_s"])
def test_boolean_criterion_cannot_silently_widen_original_threshold(field):
    registration, envelope, records, asset = graph()
    registration = replace(registration, criteria=replace(registration.criteria, **{field: True}))
    with pytest.raises(ValueError, match="strict finite criterion"):
        prepare((registration, envelope, records, asset))


def test_criterion_cannot_be_for_a_different_physical_object():
    registration, envelope, records, asset = graph()
    registration = replace(registration, criteria=replace(registration.criteria, object_id="other"))
    result = prepare((registration, envelope, records, asset))
    assert result.available_rows == 0
    assert "criterion_reference_target_mismatch" in result.rows[0].reasons


@pytest.mark.parametrize("carrier", ["mutable", "subclass"])
def test_nonconcrete_marker_carrier_cannot_supply_available_motion_input(carrier):
    registration, envelope, records, asset = graph()
    original = registration.cases[0].marker_registration
    if carrier == "mutable":
        marker = SimpleNamespace(**asdict(original))
    else:

        class MarkerSubclass(PoseMarkerRegistration):
            pass

        marker = MarkerSubclass(**asdict(original))
    registration = replace(
        registration, cases=(replace(registration.cases[0], marker_registration=marker),)
    )
    assert raw.validate_raw_episode_v3(envelope, records).status == "COMPLETE"
    result = prepare((registration, envelope, records, asset))
    row = result.rows[0]
    assert row.status == "UNAVAILABLE" and row.motion_residual_m_s is None
    assert "concrete_pose_marker_registration_required" in row.reasons
    assert (row.start_step, row.end_step) == (120, 124)
    assert (row.command_seq_start, row.command_seq_end) == (1, 2)
    if carrier == "mutable":
        marker.marker_size_m = 0.0525
        repeated = prepare((registration, envelope, records, asset))
        assert repeated.rows[0].reasons == row.reasons
        assert repeated.raw_source_digest == result.raw_source_digest


def test_concrete_marker_fields_are_revalidated_before_reference_use():
    registration, envelope, records, asset = graph()
    marker = registration.cases[0].marker_registration
    # Simulates a forged nested frozen object; it still has the genuine class.
    object.__setattr__(marker, "dictionary", "FORGED_DICTIONARY")
    assert raw.validate_raw_episode_v3(envelope, records).status == "COMPLETE"
    result = prepare((registration, envelope, records, asset))
    assert result.available_rows == 0
    assert result.rows[0].motion_residual_m_s is None
    assert (result.rows[0].start_step, result.rows[0].end_step) == (120, 124)
