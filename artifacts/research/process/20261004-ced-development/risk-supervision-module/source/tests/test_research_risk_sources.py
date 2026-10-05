"""Source-consistency checks; synthetic cases are explicitly SOFTWARE_ONLY."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.risk_sources import (
    RawCaseRegistration,
    RiskSourceAuditor,
    RiskSourceRegistration,
    required_source_paths,
)
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    configuration_hash,
)
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

ROOT = Path(__file__).resolve().parents[1]
MOTION = (
    ROOT / "artifacts/research/process/20261004-ced-development/t7b-pose-marker-motion-development"
)


def hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def sources() -> dict[str, str]:
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            *required_source_paths(),
            "assets/robots/franka_panda/scene_pose_marker_color_v2.xml",
        )
    }


def json_file(path: Path, value: object) -> None:
    path.write_text(json.dumps(value) + "\n")


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def fixture_case(tmp_path: Path) -> tuple[RawCaseRegistration, Path]:
    """Static synthetic traces, never presented as a measured physical episode."""
    case = tmp_path / "case"
    case.mkdir()
    first = json.loads((MOTION / "attempt-1/raw-physics.jsonl").read_text().splitlines()[0])
    control = json.loads((MOTION / "attempt-1/raw-actuators.jsonl").read_text().splitlines()[0])
    dt = 0.0041666667
    physics = []
    controls = []
    for step in range(122):
        physics.append({**first, "physics_step": step, "sim_time_s": step * dt})
        if step:
            controls.append({**control, "physics_step": step, "sim_time_s": (step - 1) * dt})
    for name, rows in (
        ("raw-physics.jsonl", physics),
        ("raw-actuators.jsonl", controls),
        ("raw-actions.jsonl", []),
    ):
        (case / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    for name in ("commands.json", "actions.json", "unframed-actions.json"):
        json_file(case / name, [])
    header = json.loads((MOTION / "header.json").read_bytes())
    context = {
        "episode_id": first["episode_id"],
        "physics_dt_s": dt,
        "evaluation_start_step": 120,
        "initial_controller_targets": {
            "joints_rad": [-0.8, 0, 0, 0, 0, 0, 0],
            "fingers_m": [0.039, 0.039],
        },
        "actuator_delay_steps": 0,
    }
    registration = RawCaseRegistration(
        "sw-case",
        "case",
        "MARKER_MOTION_DEVELOPMENT_RAW_V1",
        hashes(case),
        header["scene"],
        context,
        {"physics_steps": 121, "commands": 0, "actions": 0, "frames": 0},
        source_kind="SOFTWARE_ONLY",
    )
    return registration, case


def registered(tmp_path: Path, case: RawCaseRegistration) -> RiskSourceAuditor:
    registration = RiskSourceRegistration(
        tmp_path, ROOT, sources(), (case,), CompletionCriteria("object", "target_region")
    )
    return RiskSourceAuditor({"fixture": registration})


def test_unregistered_id_and_unsupported_scope_fail_closed() -> None:
    auditor = RiskSourceAuditor({})
    result = auditor.audit("missing", scope="RAW_EXECUTION")
    assert result.status == "UNKNOWN"
    assert result.counts["allocated"] == 0
    assert result.formal_source_eligible is False
    with pytest.raises(ValueError, match="scope"):
        auditor.audit("missing", scope="VALID_RECEIPT")


def test_static_software_trace_recomputed_failure_with_full_denominator(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "VALID"
    assert result.source_scope == "SOFTWARE_ONLY"
    assert result.counts == {
        "allocated": 1,
        "reconstructed": 1,
        "failed": 1,
        "physical_success": 0,
        "unknown": 0,
    }
    assert result.case_results[0]["physical_outcome"]["success"] is False
    assert result.formal_source_eligible is False


def test_risk_scope_does_not_accept_flag_receipt_or_valid_raw_execution(tmp_path: Path) -> None:
    case, directory = fixture_case(tmp_path)
    json_file(directory / "risk-accepted.json", {"source_accepted": True, "status": "VALID"})
    case = replace(case, original_file_hashes=hashes(directory))
    result = registered(tmp_path, case).audit("fixture")
    assert result.status == "UNKNOWN"
    assert result.verified_scope == "RAW_EXECUTION"
    assert {
        "risk_label_source_unavailable",
        "initial_source_audit_unavailable",
        "clock_mapping_unavailable",
        "calibration_source_unavailable",
        "risk_selection_replay_unavailable",
    } <= set(result.reasons)
    assert result.formal_source_eligible is False


@pytest.mark.parametrize(
    "field",
    [
        "control_rad",
        "applied_joint_targets_rad",
        "pre_joint_positions_rad",
        "finger_control_targets_m",
    ],
)
def test_rehashed_controller_mismatch_rejected(tmp_path: Path, field: str) -> None:
    case, directory = fixture_case(tmp_path)
    path = directory / "raw-actuators.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows[5][field][0] += 0.025
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    case = replace(case, original_file_hashes=hashes(directory))
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID"
    assert result.counts["allocated"] == result.counts["unknown"] == 1


@pytest.mark.parametrize("mode", ["prefix", "tail", "middle", "time", "collision_scope"])
def test_rehashed_incomplete_physics_rejected(tmp_path: Path, mode: str) -> None:
    case, directory = fixture_case(tmp_path)
    path = directory / "raw-physics.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    if mode == "prefix":
        rows.pop(0)
    elif mode == "tail":
        rows.pop()
    elif mode == "middle":
        rows.pop(7)
    elif mode == "time":
        rows[5]["sim_time_s"] += 0.01
    else:
        rows[5]["self_collision_distances_m"].pop()
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID"


def test_registration_copies_nested_source_inventory_and_context(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    context = plain(case.context)
    source_hashes = sources()
    caller = replace(case, context=context)
    registration = RiskSourceRegistration(
        tmp_path, ROOT, source_hashes, (caller,), CompletionCriteria("object", "target_region")
    )
    auditor = RiskSourceAuditor({"fixture": registration})
    context["initial_controller_targets"]["joints_rad"][0] = 99
    source_hashes.clear()
    assert auditor.audit("fixture", scope="RAW_EXECUTION").status == "VALID"


def test_original_inventory_changes_and_extra_files_do_not_shrink_denominator(
    tmp_path: Path,
) -> None:
    case, directory = fixture_case(tmp_path)
    auditor = registered(tmp_path, case)
    assert auditor.audit("fixture", scope="RAW_EXECUTION").status == "VALID"
    json_file(directory / "summary.json", {"status": "SUCCESS"})
    result = auditor.audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID"
    assert result.counts["allocated"] == result.counts["unknown"] == 1


def test_missing_attempt_retained_in_all_assigned_denominator(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    missing = replace(case, case_id="failed-original", relative_directory="absent")
    registration = RiskSourceRegistration(
        tmp_path, ROOT, sources(), (case, missing), CompletionCriteria("object", "target_region")
    )
    result = RiskSourceAuditor({"fixture": registration}).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "UNKNOWN"
    assert result.counts["allocated"] == 2
    assert result.counts["failed"] == result.counts["unknown"] == 1
    assert len(result.original_file_hashes) == 2 * len(case.original_file_hashes)
    assert any(name.startswith("failed-original/") for name in result.original_file_hashes)


@pytest.mark.parametrize("relative", ["../case", "/tmp/case"])
def test_registration_rejects_path_escape(tmp_path: Path, relative: str) -> None:
    case, _ = fixture_case(tmp_path)
    with pytest.raises(ValueError, match="relative"):
        replace(case, relative_directory=relative)


def test_symlink_case_rejected(tmp_path: Path) -> None:
    case, directory = fixture_case(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(directory, target_is_directory=True)
    result = registered(tmp_path, replace(case, relative_directory="link")).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID"


def test_current_validating_helper_source_mismatch_is_invalid(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    inventory = sources()
    inventory[next(iter(inventory))] = "0" * 64
    registration = RiskSourceRegistration(
        tmp_path, ROOT, inventory, (case,), CompletionCriteria("object", "target_region")
    )
    result = RiskSourceAuditor({"fixture": registration}).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID"
    assert result.counts["allocated"] == result.counts["unknown"] == 1


def test_actual_excluded_saved_motion_raw_only_reconstruction() -> None:
    directory = MOTION / "attempt-1"
    header = json.loads((MOTION / "header.json").read_bytes())
    summary = json.loads((directory / "summary.json").read_bytes())
    context = {
        "episode_id": summary["episode_id"],
        "physics_dt_s": header["config"]["physics_dt_s"],
        "evaluation_start_step": 120,
        "initial_controller_targets": {
            "joints_rad": [-0.8, 0, 0, 0, 0, 0, 0],
            "fingers_m": [0.039, 0.039],
        },
        "actuator_delay_steps": 0,
    }
    case = RawCaseRegistration(
        "actual-excluded-motion",
        "attempt-1",
        "MARKER_MOTION_DEVELOPMENT_RAW_V1",
        hashes(directory),
        header["scene"],
        context,
        {"physics_steps": 4806, "commands": 743, "actions": 9, "frames": 10},
        marker_registration=PoseMarkerRegistration(
            7, 0.045, "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4"
        ),
        source_kind="RECORDED_SIMULATION",
    )
    inventory = sources()
    asset = "assets/robots/franka_panda/scene_pose_marker_color_v2.xml"
    inventory[asset] = hashlib.sha256((ROOT / asset).read_bytes()).hexdigest()
    registration = RiskSourceRegistration(
        MOTION, ROOT, inventory, (case,), CompletionCriteria("object", "target_region")
    )
    auditor = RiskSourceAuditor({"actual": registration})
    raw = auditor.audit("actual", scope="RAW_EXECUTION")
    assert raw.status == "VALID", raw.reasons
    assert raw.source_scope == "RECORDED_SIMULATION_RAW_ONLY"
    assert raw.counts["physical_success"] == 1
    assert raw.case_results[0]["marker_unknown_frames"] == 9
    assert plain(raw.case_results[0]["physical_outcome"]) == summary["outcome"]
    assert raw.formal_source_eligible is False
    risk = auditor.audit("actual")
    assert risk.status == "UNKNOWN"
    assert risk.formal_source_eligible is False


def test_ced_raw_layout_recomputes_failed_no_action_source(tmp_path: Path) -> None:
    marker, directory = fixture_case(tmp_path)
    physics = [
        json.loads(row) for row in (directory / "raw-physics.jsonl").read_text().splitlines()
    ]
    controls = [
        json.loads(row) for row in (directory / "raw-actuators.jsonl").read_text().splitlines()
    ]
    json_file(directory / "physical-observations.json", physics)
    json_file(directory / "actuator-steps.json", controls)
    assignment = {"scene": plain(marker.assignment)}
    context = {
        **plain(marker.context),
        "schema_version": "rgbd.raw-episode.v2",
        "reset_step": 0,
        "reset_sim_time_s": 0,
        "terminal_step": 121,
        "terminal_sim_time_s": physics[-1]["sim_time_s"],
        "reset_observation_hash": hashlib.sha256(
            json.dumps(physics[0], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "terminal_observation_hash": hashlib.sha256(
            json.dumps(physics[-1], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    context.update(
        assignment_hash=content_digest(assignment),
        group_id=assignment["scene"]["group_id"],
        scene_hash=SceneSpec.model_validate(assignment["scene"]).scene_hash,
    )
    json_file(directory / "context.json", context)
    case = replace(
        marker,
        layout="CED_PILOT_RAW_V2",
        assignment=assignment,
        context=context,
        original_file_hashes=hashes(directory),
    )
    assert registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION").status == "VALID"
    paired = {"base_assignment": assignment, "period_s": 2.0, "stratum_id": "STATIC_RTT50"}
    context["pilot_assignment_hash"] = content_digest(paired)
    json_file(directory / "context.json", context)
    case = replace(case, assignment=paired, context=context, original_file_hashes=hashes(directory))
    assert registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION").status == "VALID"
    actual_request = replace(case, source_kind="RECORDED_SIMULATION")
    missing_role = registered(tmp_path, actual_request).audit("fixture", scope="RAW_EXECUTION")
    assert missing_role.status == "UNKNOWN"
    assert any("current_role_binding_unavailable" in reason for reason in missing_role.reasons)
    context["evaluation_start_step"] = 121
    json_file(directory / "context.json", context)
    case = replace(case, context=context, original_file_hashes=hashes(directory))
    assert registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION").status == "INVALID"


@pytest.mark.parametrize(
    "name,value",
    [
        ("commands.json", None),
        ("commands.json", {}),
        ("summary.json", None),
        ("summary.json", []),
        ("physical-samples.json", {"success": True}),
    ],
)
def test_malformed_rehashed_tables_fail_typed_validation(
    tmp_path: Path, name: str, value: object
) -> None:
    case, directory = fixture_case(tmp_path)
    json_file(directory / name, value)
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID"
    assert result.counts["unknown"] == result.counts["allocated"] == 1


@pytest.mark.parametrize("bad_clamp", [False, True])
def test_joint_error_clamp_and_bias_reproduced(tmp_path: Path, bad_clamp: bool) -> None:
    case, directory = fixture_case(tmp_path)
    command = {
        "command_seq": 1,
        "physics_step": 120,
        "sim_time_s": 120 * 0.0041666667,
        "episode_id": case.context["episode_id"],
        "type": "joint_target",
        "accepted": True,
        "reason": "",
        "after_emergency_stop": False,
        "target_positions_rad": [-0.5, 0, 0, 0, 0, 0, 0],
        "applied_target_positions_rad": [-0.5, 0, 0, 0, 0, 0, 0],
    }
    json_file(directory / "commands.json", [command])
    path = directory / "raw-actuators.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows[-1]["applied_joint_targets_rad"][0] = -0.5
    rows[-1]["control_rad"][0] = -0.5 if bad_clamp else -0.7
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    case = replace(
        case,
        original_file_hashes=hashes(directory),
        expected_counts={**dict(case.expected_counts), "commands": 1},
    )
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == ("INVALID" if bad_clamp else "UNKNOWN")
    if not bad_clamp:
        # Correct controller math still lacks the original typed action ranges.
        assert any("typed_action_ranges" in reason for reason in result.reasons)


def test_role_binding_nested_snapshots_copy_without_mutable_aliases(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    edge_names = [
        "src/cloud_edge_robot_arm/edge/recovery/verification_router.py",
        *[
            f"src/cloud_edge_robot_arm/edge/evidence/{name}.py"
            for name in ("models", "validator", "conditions")
        ],
    ]
    cloud_names = ["src/cloud_edge_robot_arm/vision/role_models.py"]
    device_name = "src/cloud_edge_robot_arm/vision/action_evidence.py"
    source_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in [*edge_names, *cloud_names, device_name]
    }
    policy = {"scope": "SOFTWARE_ONLY", "values": [1, 2]}
    cloud = RoleProviderSnapshot(
        "CLOUD",
        "fixture-cloud",
        "LOCAL_HOST",
        "fixture-model",
        None,
        None,
        None,
        configuration_hash(policy),
        {name: source_hashes[name] for name in cloud_names},
    )
    edge = RoleProviderSnapshot(
        "EDGE",
        "fixture-edge",
        "LOCAL_HOST",
        None,
        None,
        None,
        None,
        configuration_hash(policy),
        {name: source_hashes[name] for name in edge_names},
    )
    device = {device_name: source_hashes[device_name]}
    binding = RoleRuntimeBinding(
        RoleModelBundle(cloud, edge.provider_id, edge.digest(), configuration_hash(device)),
        edge,
        device,
        policy,
        root=ROOT,
    )
    registration = RiskSourceRegistration(
        tmp_path, ROOT, sources(), (case,), CompletionCriteria("object", "target_region"), binding
    )
    policy["values"][0] = 99
    assert registration.current_role_binding is not binding
    assert plain(registration.current_role_binding.edge_policy)["values"] == [1, 2]
    assert (
        RiskSourceAuditor({"fixture": registration}).audit("fixture", scope="RAW_EXECUTION").status
        == "VALID"
    )


def test_unknown_raw_field_and_nonfinite_row_rejected(tmp_path: Path) -> None:
    case, directory = fixture_case(tmp_path)
    path = directory / "raw-physics.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows[0]["new_schema_truth"] = 1
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID"
    rows[0].pop("new_schema_truth")
    rows[0]["sim_time_s"] = float("nan")
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert (
        registered(tmp_path, replace(case, original_file_hashes=hashes(directory)))
        .audit("fixture", scope="RAW_EXECUTION")
        .status
        == "INVALID"
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("actions.json", [{"success": True}]),
        ("unframed-actions.json", [{"success": True}]),
        ("raw-actions.jsonl", {"result": {"success": True}}),
    ],
)
def test_action_declarations_cannot_forge_missing_execution(
    tmp_path: Path, name: str, value: object
) -> None:
    case, directory = fixture_case(tmp_path)
    json_file(directory / name, value)
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID"
    assert result.counts["physical_success"] == 0


def test_audit_results_nested_outcomes_are_immutable(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    with pytest.raises(TypeError):
        result.case_results[0]["physical_outcome"]["success"] = True
    with pytest.raises(TypeError):
        result.counts["allocated"] = 0


def test_registration_cannot_omit_helpers_or_duplicate_an_original(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    with pytest.raises(ValueError, match="helper"):
        RiskSourceRegistration(
            tmp_path, ROOT, {}, (case,), CompletionCriteria("object", "target_region")
        )
    with pytest.raises(ValueError, match="distinct"):
        RiskSourceRegistration(
            tmp_path,
            ROOT,
            sources(),
            (case, replace(case, case_id="copy")),
            CompletionCriteria("object", "target_region"),
        )
    with pytest.raises(ValueError, match="integer"):
        replace(case, expected_counts={**dict(case.expected_counts), "frames": True})


def motion_software_case(tmp_path: Path) -> tuple[RawCaseRegistration, Path]:
    """Derived complete source copy is SOFTWARE_ONLY, never new measured evidence."""
    import shutil

    directory = tmp_path / "attempt"
    shutil.copytree(MOTION / "attempt-1", directory)
    header = json.loads((MOTION / "header.json").read_bytes())
    summary = json.loads((directory / "summary.json").read_bytes())
    case = RawCaseRegistration(
        "derived-software-motion",
        "attempt",
        "MARKER_MOTION_DEVELOPMENT_RAW_V1",
        hashes(directory),
        header["scene"],
        {
            "episode_id": summary["episode_id"],
            "physics_dt_s": header["config"]["physics_dt_s"],
            "evaluation_start_step": 120,
            "initial_controller_targets": {
                "joints_rad": [-0.8, 0, 0, 0, 0, 0, 0],
                "fingers_m": [0.039, 0.039],
            },
            "actuator_delay_steps": 0,
        },
        {"physics_steps": 4806, "commands": 743, "actions": 9, "frames": 10},
        source_kind="SOFTWARE_ONLY",
        marker_registration=PoseMarkerRegistration(
            7, 0.045, "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4"
        ),
    )
    return case, directory


def rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize("mutation", ["overwritten_hold", "asset_gain", "fixed_geometry"])
def test_full_software_action_source_rejects_independent_consistency_counterexamples(
    tmp_path: Path, mutation: str
) -> None:
    case, directory = motion_software_case(tmp_path)
    if mutation == "overwritten_hold":
        path = directory / "commands.json"
        commands = json.loads(path.read_bytes())
        index = next(
            i
            for i, command in enumerate(commands[:-1])
            if command["type"] == "hold_current_joints"
            and commands[i + 1]["physics_step"] == command["physics_step"]
        )
        commands[index]["target_positions_rad"][0] += 0.01
        commands[index]["applied_target_positions_rad"][0] += 0.01
        json_file(path, commands)
        reason = "hold"
    elif mutation == "asset_gain":
        path = directory / "raw-actuators.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[5]["actuator_gains"][1] = 40.0
        rows[5]["control_rad"][1] = (
            rows[5]["pre_joint_positions_rad"][1] + rows[5]["pre_gravity_bias_nm"][1] / 40
        )
        rewrite_jsonl(path, rows)
        reason = "asset"
    else:
        from dataclasses import asdict

        from cloud_edge_robot_arm.research.protocol_evidence import _observation
        from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
            sample_physical_observation,
        )

        path = directory / "raw-physics.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[5]["object_half_extent_m"][0] = 0.0001
        rewrite_jsonl(path, rows)
        samples = json.loads((directory / "physical-samples.json").read_bytes())
        samples[5] = asdict(
            sample_physical_observation(
                _observation(rows[5]), CompletionCriteria("object", "target_region")
            )
        )
        json_file(directory / "physical-samples.json", samples)
        reason = "geometry"
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID", result.reasons
    assert any(reason in value for value in result.reasons)
    assert result.counts["allocated"] == result.counts["unknown"] == 1
    assert result.counts["physical_success"] == 0
    assert result.formal_source_eligible is False


def test_full_software_commands_cannot_delete_every_typed_action(tmp_path: Path) -> None:
    case, directory = motion_software_case(tmp_path)
    (directory / "raw-actions.jsonl").write_text("")
    json_file(directory / "actions.json", [])
    case = replace(
        case,
        original_file_hashes=hashes(directory),
        expected_counts={**dict(case.expected_counts), "actions": 0},
    )
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "UNKNOWN", result.reasons
    assert any("action" in reason for reason in result.reasons)
    assert result.counts["unknown"] == result.counts["allocated"] == 1
    assert result.counts["reconstructed"] == result.counts["physical_success"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "bias_bool",
        "q_bool",
        "gain_bool",
        "range_bool",
        "output_bool",
        "target_bool",
        "finger_bool",
    ],
)
def test_strict_actuator_schema_and_numeric_types(tmp_path: Path, mutation: str) -> None:
    case, directory = fixture_case(tmp_path)
    path = directory / "raw-actuators.jsonl"
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    if mutation == "unknown":
        rows[5]["unrecognized_authority"] = True
    else:
        key = {
            "bias_bool": "pre_gravity_bias_nm",
            "q_bool": "pre_joint_positions_rad",
            "gain_bool": "actuator_gains",
            "range_bool": "actuator_ctrl_ranges",
            "output_bool": "control_rad",
            "target_bool": "applied_joint_targets_rad",
            "finger_bool": "finger_control_targets_m",
        }[mutation]
        if mutation == "range_bool":
            rows[5][key][0][0] = False
        else:
            rows[5][key][0 if mutation == "bias_bool" else 1] = False
    rewrite_jsonl(path, rows)
    result = registered(tmp_path, replace(case, original_file_hashes=hashes(directory))).audit(
        "fixture", scope="RAW_EXECUTION"
    )
    assert result.status == "INVALID", result.reasons


def test_missing_registered_controller_asset_is_unknown(tmp_path: Path) -> None:
    case, _ = fixture_case(tmp_path)
    inventory = sources()
    del inventory["assets/robots/franka_panda/scene_pose_marker_color_v2.xml"]
    registration = RiskSourceRegistration(
        tmp_path, ROOT, inventory, (case,), CompletionCriteria("object", "target_region")
    )
    result = RiskSourceAuditor({"fixture": registration}).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "UNKNOWN", result.reasons
    assert any("asset" in reason for reason in result.reasons)


@pytest.mark.parametrize("mutation", ["unknown", "requested_bool", "applied_bool", "string"])
def test_command_typed_schema_cannot_be_waived_by_rehashed_inventory(
    tmp_path: Path, mutation: str
) -> None:
    case, directory = fixture_case(tmp_path)
    command = {
        "command_seq": 1,
        "physics_step": 120,
        "sim_time_s": 120 * 0.0041666667,
        "episode_id": case.context["episode_id"],
        "type": "joint_target",
        "accepted": True,
        "reason": "",
        "after_emergency_stop": False,
        "target_positions_rad": [-0.8, 0, 0, 0, 0, 0, 0],
        "applied_target_positions_rad": [-0.8, 0, 0, 0, 0, 0, 0],
    }
    if mutation == "unknown":
        command["authority"] = True
    else:
        key = (
            "applied_target_positions_rad" if mutation == "applied_bool" else "target_positions_rad"
        )
        command[key][1] = "0" if mutation == "string" else False
    json_file(directory / "commands.json", [command])
    changed = replace(
        case,
        original_file_hashes=hashes(directory),
        expected_counts={**dict(case.expected_counts), "commands": 1},
    )
    result = registered(tmp_path, changed).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID", result.reasons


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("location", ["actuator", "dt"])
def test_oversized_integer_returns_typed_invalid_with_complete_inventory(
    tmp_path: Path, sign: int, location: str
) -> None:
    case, directory = fixture_case(tmp_path)
    value = sign * 10**500
    if location == "actuator":
        path = directory / "raw-actuators.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[5]["pre_gravity_bias_nm"][0] = value
        rewrite_jsonl(path, rows)
        case = replace(case, original_file_hashes=hashes(directory))
    else:
        case = replace(case, context={**plain(case.context), "physics_dt_s": value})
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID"
    assert result.counts["allocated"] == result.counts["unknown"] == 1
    assert result.counts["reconstructed"] == result.counts["physical_success"] == 0
    assert dict(result.original_file_hashes) == {
        f"{case.case_id}/{name}": digest for name, digest in case.original_file_hashes.items()
    }
    assert not result.verified_original_file_hashes
    assert result.formal_source_eligible is False
