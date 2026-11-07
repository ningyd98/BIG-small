"""Cross-original semantic validation of recorder-produced SOFTWARE_ONLY graphs."""

import shutil
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import load_json
from tests.native_collection_source_graph import (
    effect_audit,
    recorded_effect_graph,
    reseal_software_inventory,
    write_software_json,
)


def graph_api():
    name = "cloud_edge_robot_arm.research.native_source_effect_graph"
    module = import_module(name) if util.find_spec(name) else None
    assert callable(getattr(module, "validate_native_source_effect_graph", None)), (
        "R453 source effect graph kernel missing"
    )
    return module


def fixture(tmp_path):
    graph_api()
    root = tmp_path / "original"
    protocol = recorded_effect_graph(root)
    audit = effect_audit(root, protocol)
    assert audit.raw["legacy_utc_mapping"] == "UNAVAILABLE" and not audit.source_ok
    return root, protocol, audit


def rejected(root, protocol, name, mutation):
    original = (root / "originals/partial-originals.json").read_bytes()
    target = root.parent / name
    shutil.copytree(root / "originals", target / "originals")
    path = target / "originals/partial-originals.json"
    raw = load_json(path)
    checks = load_json(target / "originals/active-checks.json")
    mutation(raw, checks, target / "originals")
    write_software_json(path, raw)
    write_software_json(target / "originals/active-checks.json", checks)
    reseal_software_inventory(target / "originals")
    with pytest.raises((ValueError, KeyError), match=None):
        effect_audit(target, protocol)
    assert (root / "originals/partial-originals.json").read_bytes() == original


def changed_control(raw, number, target):
    row = raw["physics"][number - 1]
    source = next(
        c for c in raw["control_sources"] if c["interval_id"] == row["control_interval_id"]
    )
    for value in (row["control_payload"], source["control_state"]):
        value["applied_joint_targets_rad"] = list(target)
        value["control_rad"] = [
            min(
                bounds[1],
                max(bounds[0], current + min(0.1, max(-0.1, desired - current)) + bias / gain),
            )
            for desired, current, bias, gain, bounds in zip(
                target,
                value["pre_joint_positions_rad"],
                value["pre_gravity_bias_nm"],
                value["actuator_gains"],
                value["actuator_ctrl_ranges"],
                strict=True,
            )
        ]


def test_recorded_complete_effect_graph_preserves_legacy_unknown(tmp_path):
    _, _, audit = fixture(tmp_path)
    assert len(audit.raw["physics"]) == 7 and len(audit.raw["control_sources"]) == 8
    assert audit.raw["reset"]["actuator_delay_steps"] == 2
    assert audit.raw["control_sources"][-1]["control_state"]["physics_step"] == 8
    assert audit.raw["total_physics_steps"] == 7
    assert not audit.source_ok and not audit.horizon_ok and not audit.geometry_ok
    assert audit.render_accounting() == audit.raw["render_passes_observed"]


def test_terminal_stop_control_binds_final_physical_state(tmp_path):
    root, protocol, audit = fixture(tmp_path)
    raw = audit.raw
    n = raw["total_physics_steps"]
    used = {row["control_interval_id"] for row in raw["physics"]}
    extra = [row for row in raw["control_sources"] if row["interval_id"] not in used]
    assert n == 7 and len(extra) == 1
    terminal = extra[0]
    assert raw["commands"][-1]["command_payload"]["type"] == "emergency_stop"
    assert raw["commands"][-1]["command_payload"]["physics_step"] == n
    assert terminal["physics_step"] == n and terminal["control_state"]["physics_step"] == n + 1
    assert terminal["control_state"]["sim_time_s"] == audit.states[n]["sim_time_s"]
    assert (
        terminal["control_state"]["pre_joint_positions_rad"]
        == audit.states[n]["joint_positions_rad"]
    )
    assert not audit.source_ok and not audit.horizon_ok
    original = (root / "originals/partial-originals.json").read_bytes()
    target = tmp_path / "terminal-rewind"
    shutil.copytree(root / "originals", target / "originals")
    path = target / "originals/partial-originals.json"
    changed = load_json(path)
    control = next(
        row for row in changed["control_sources"] if row["operation_id"] == terminal["operation_id"]
    )
    control["physics_step"] = n - 1
    control["control_state"]["physics_step"] = n
    control["control_state"]["sim_time_s"] = audit.states[n - 1]["sim_time_s"]
    for row in changed["operational_events"]:
        if row["operation_id"] == terminal["operation_id"]:
            row["begin_step"] = row["end_step"] = n - 1
    for row in changed["backend_operation_ledger"]:
        if row["operation_id"] == terminal["operation_id"]:
            row["physics_step"] = n - 1
    for row in changed["intervals"]:
        if row["interval_id"] == terminal["interval_id"]:
            row["start_step"] = row["end_step"] = n - 1
            row["start_sim_time_s"] = row["end_sim_time_s"] = audit.states[n - 1]["sim_time_s"]
    write_software_json(path, changed)
    reseal_software_inventory(target / "originals")
    assert (root / "originals/partial-originals.json").read_bytes() == original
    with pytest.raises(ValueError, match="terminal CONTROL current step"):
        effect_audit(target, protocol)
    assert (root / "originals/partial-originals.json").read_bytes() == original


def test_command_target_delay_clip_gripper_and_hold_replay(tmp_path):
    root, protocol, _ = fixture(tmp_path)
    variants = {
        "initial": lambda r, c, d: r["reset"]["initial_controller_targets"][
            "joints_rad"
        ].__setitem__(0, 0.0),
        "clip": lambda r, c, d: r["commands"][0]["command_payload"][
            "applied_target_positions_rad"
        ].__setitem__(0, 4.0),
        "effective": lambda r, c, d: r["commands"][0].__setitem__("effective_from_step", 1),
        "queue": lambda r, c, d: r["commands"][0]["command_payload"].__setitem__(
            "reason", "queued_until_physics_step=3"
        ),
        "delay": lambda r, c, d: r["reset"].__setitem__("actuator_delay_steps", 1),
        "gripper": lambda r, c, d: r["commands"][1]["command_payload"].__setitem__(
            "target_open", True
        ),
        "hold": lambda r, c, d: r["commands"][3]["command_payload"][
            "target_positions_rad"
        ].__setitem__(0, 0.4),
        "uncleared-queue": lambda r, c, d: changed_control(r, 6, [0.4] * 7),
        "self-consistent-control": lambda r, c, d: changed_control(r, 5, [0.5] * 7),
        "terminal-effective": lambda r, c, d: r["commands"][-1].__setitem__(
            "effective_from_step", None
        ),
    }
    for name, mutation in variants.items():
        rejected(root, protocol, name, mutation)


def test_paired_missing_operations_do_not_hide_required_effects(tmp_path):
    root, protocol, _ = fixture(tmp_path)
    for kind in ("CONTROL", "PHYSICS", "COMMAND", "CAPTURE"):

        def remove(raw, checks, directory, kind=kind):
            number = next(r["operation_id"] for r in raw["operational_events"] if r["kind"] == kind)
            raw["operational_events"] = [
                r for r in raw["operational_events"] if r["operation_id"] != number
            ]
            for index, row in enumerate(raw["operational_events"], 1):
                row["sequence"] = index
            raw["backend_operation_ledger"] = [
                r for r in raw["backend_operation_ledger"] if r["operation_id"] != number
            ]

        rejected(root, protocol, "paired-" + kind, remove)

    def remove_primary_control(raw, checks, directory):
        number = raw["control_sources"].pop(0)["operation_id"]
        raw["operational_events"] = [
            r for r in raw["operational_events"] if r["operation_id"] != number
        ]
        raw["backend_operation_ledger"] = [
            r for r in raw["backend_operation_ledger"] if r["operation_id"] != number
        ]

    rejected(root, protocol, "missing-primary-control", remove_primary_control)


def test_guard_schedule_active_checks_and_real_stop_are_required(tmp_path):
    root, protocol, _ = fixture(tmp_path)
    variants = {
        "only-closed": lambda r, c, d: r.__setitem__("guard_events", r["guard_events"][-1:]),
        "empty-checks": lambda r, c, d: c.clear(),
        "missing-check": lambda r, c, d: c.pop(0),
        "false-phase": lambda r, c, d: r["guard_events"][0].__setitem__("phase", "AFTER"),
        "false-step": lambda r, c, d: c[0].__setitem__("step", 1),
        "missing-hold": lambda r, c, d: r["commands"].pop(-2),
        "missing-stop": lambda r, c, d: r["commands"].pop(),
        "missing-stop-control": lambda r, c, d: r["control_sources"].pop(),
        "stop-order": lambda r, c, d: r["commands"].__setitem__(
            slice(-2, None), list(reversed(r["commands"][-2:]))
        ),
        "after-stop-effect": lambda r, c, d: r["control_sources"].append(
            dict(r["control_sources"][-1])
        ),
    }
    for name, mutation in variants.items():
        rejected(root, protocol, name, mutation)
    for kind in ("PHYSICS", "RETURN", "CAPTURE"):

        def missing_guard(raw, checks, directory, kind=kind):
            index = next(i for i, row in enumerate(raw["guard_events"]) if row["kind"] == kind)
            raw["guard_events"].pop(index)
            checks.pop(index)
            for i, row in enumerate(raw["guard_events"][:-1], 1):
                row["sequence"] = i

        rejected(root, protocol, "missing-guard-" + kind, missing_guard)

    def duplicate_physics(raw, checks, directory):
        index = next(i for i, row in enumerate(raw["guard_events"]) if row["kind"] == "PHYSICS")
        raw["guard_events"].insert(index, dict(raw["guard_events"][index]))
        checks.insert(index, dict(checks[index]))
        for i, row in enumerate(raw["guard_events"][:-1], 1):
            row["sequence"] = i

    rejected(root, protocol, "duplicate-physics-guard", duplicate_physics)


def test_effect_graph_identity_order_and_control_joins_are_exact(tmp_path):
    root, protocol, _ = fixture(tmp_path)
    variants = {
        "cross-episode": lambda r, c, d: r["control_sources"][0].__setitem__(
            "episode_id", "foreign"
        ),
        "cross-step": lambda r, c, d: r["physics"][1].__setitem__(
            "control_interval_id", r["physics"][0]["control_interval_id"]
        ),
        "late-control": lambda r, c, d: r["control_sources"][0].__setitem__("operation_id", 999),
        "unclosed": lambda r, c, d: r["backend_operation_ledger"].pop(),
        "nesting": lambda r, c, d: r["backend_operation_ledger"].__setitem__(
            slice(0, 2), list(reversed(r["backend_operation_ledger"][:2]))
        ),
        "orphan-frame": lambda r, c, d: r["allocated_frames"].append("foreign"),
        "orphan-role": lambda r, c, d: r["capture_source_roles"].__setitem__(
            "999", dict(next(iter(r["capture_source_roles"].values())))
        ),
        "command-parent": lambda r, c, d: r["commands"][0].__setitem__(
            "parent_interval_id", r["commands"][-1]["parent_interval_id"]
        ),
        "command-sequence": lambda r, c, d: r["commands"][0]["command_payload"].__setitem__(
            "command_seq", 4
        ),
        "terminal-count": lambda r, c, d: r.__setitem__("total_physics_steps", 8),
    }
    for name, mutation in variants.items():
        rejected(root, protocol, name, mutation)

    def wrong_metadata(raw, checks, directory):
        name = next(iter(raw["frame_sources"].values()))
        metadata = load_json(directory / name)
        metadata["capture_source"]["physics_step"] = 7
        write_software_json(directory / name, metadata)

    rejected(root, protocol, "orphan-metadata", wrong_metadata)
