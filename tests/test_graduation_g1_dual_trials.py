import copy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    import importlib

    path = "scripts.graduation.g1_dual_" + name
    assert importlib.util.find_spec(path), f"missing G1 dual {name} implementation"
    return importlib.import_module(path)


def test_export_uses_exact_baseline_and_retains_historical_controller_binding(tmp_path):
    build = module("build")
    from scripts.graduation import g1_mount_runtime_build as previous

    target = tmp_path / "source"
    original, effective = build.export_base(ROOT, target)
    assert original[previous.VISION] == previous.ORIGINAL_VISION
    assert (target / previous.VISION).read_bytes() == previous.configure_vision(
        (ROOT / previous.VISION).read_bytes()
    )
    protected = "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"
    assert effective[protected] == original[protected]
    with pytest.raises(FileExistsError):
        build.export_base(ROOT, target)


def test_gate_requires_two_independently_identical_normal_rgbd_pair_witnesses():
    t = module("trials")
    witnesses = {}
    poses = []
    for number, bucket in enumerate(("X_only", "Y_only")):
        case = f"m0{number + 1}-original"
        files = {side: str(2 * number + i + 1) * 64 for i, side in enumerate(("X", "Y"))}
        witnesses[bucket] = [
            {
                "case": case,
                "time_role": "refused",
                "source_episode": "ep" + case,
                "step": 152,
                "pair_sha256": ("a" if number == 0 else "b") * 64,
                "normal_frames": {k: {"sha256": v} for k, v in files.items()},
            }
        ]
        poses.append(
            {
                "case": case,
                "role": "refused",
                "physics_step": 152,
                "bucket": bucket,
                "measurements": {
                    k: {"normal": {"rgbd_file_sha256": v, "usable": k == bucket[0]}}
                    for k, v in files.items()
                },
            }
        )
    metadata = dict(plan_sha256=t.PLAN_SHA, capture_seal_sha256="c" * 64, complementary=True)
    static, independent = {**metadata, "witnesses": witnesses}, {**metadata, "poses": poses}
    assert set(t.bind_witnesses(static, independent)) == {"X_only", "Y_only"}
    for why in ("missing", "one_direction", "diagnostic", "changed_sha", "wrong_step"):
        changed, cross = copy.deepcopy(static), copy.deepcopy(independent)
        if why == "missing":
            changed["witnesses"]["Y_only"] = []
        elif why == "one_direction":
            cross["poses"][1]["bucket"] = "X_only"
        elif why == "diagnostic":
            cross["poses"][1]["measurements"]["Y"]["normal"]["usable"] = False
        elif why == "changed_sha":
            cross["poses"][0]["measurements"]["Y"]["normal"]["rgbd_file_sha256"] = "f" * 64
        else:
            cross["poses"][0]["physics_step"] += 8
        with pytest.raises(ValueError):
            t.bind_witnesses(changed, cross)


def test_probe_gate_requires_both_marker_support_and_actual_target_servo_delivery():
    p = module("probe")

    def row(name, *, passed=False, bad=False):
        return {
            "kind": name,
            "pose": "preregistered-0",
            "physics_steps": 0,
            "commands": 0,
            "path_success": passed,
            "control_demonstrated": bad,
        }

    rows = [row(k, passed=True) for k in p.POSITIVE] + [row(k, bad=True) for k in p.NEGATIVE]
    assert p.qualifies(rows)
    for field, value, index in (
        ("commands", 1, 0),
        ("path_success", False, 1),
        ("control_demonstrated", False, -1),
    ):
        changed = copy.deepcopy(rows)
        changed[index][field] = value
        assert not p.qualifies(changed)


def test_contact_evidence_separates_block_from_board_and_tracks_both_fingers():
    t = module("trials")
    actual = [
        {"physics_step": 0, "contact_pairs": [["object_geom", "table"]]},
        {
            "physics_step": 1,
            "contact_pairs": [
                ["left_finger_geom", "object_geom"],
                ["g1_dual_id8_support", "right_finger_geom"],
                ["right_finger_geom", "g1_dual_id7_plate"],
                ["hand", "g1_dual_id8_support"],
            ],
        },
        {
            "physics_step": 2,
            "contact_pairs": [
                ["object_geom", "right_finger_geom"],
                ["object_geom", "left_finger_geom"],
            ],
        },
    ]
    found = t.hand_contacts(actual)
    assert found["block_both_fingers_steps"] == [2]
    assert found["block_hand_or_finger_steps"] == [1, 2]
    assert found["board_or_support_hand_or_finger_steps"] == [1]
    assert found["hand_contact_pairs"]["g1_dual_id8_support/right_finger_geom"] == 1


def test_reset_uses_registered_physical_mass_and_rejects_different_compiled_body():
    t = module("trials")
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

    scenario = PhysicalScenarioConfig(scenario_id="S01_NORMAL_STATIC", seed=987)
    baseline = t.bind_scenario_mass(scenario, 0.08, 0.08)
    dual = t.bind_scenario_mass(scenario, 0.10036, 0.10036000000000002)
    assert baseline == scenario and dual.seed == scenario.seed and dual.object_mass_kg == 0.10036
    with pytest.raises(ValueError):
        t.bind_scenario_mass(scenario, 0.10036, 0.08)


def test_alternative_pose_only_addresses_unavailable_visual_probe():
    probe = module("probe")
    assert probe.visibility_limited(
        {
            "kind": "both",
            "usable_ids": [7],
            "measured_reason": "development_registered_current_rgbd",
        }
    )
    assert not probe.visibility_limited(
        {
            "kind": "both",
            "usable_ids": [7, 8],
            "servo_error": "servo frame not fresh",
            "measured_reason": "development_registered_current_rgbd",
        }
    )
    assert not probe.visibility_limited(
        {"kind": "stale", "stopped_stage": "original_plan", "reason": "lease expired"}
    )


def test_actual_colour_extent_refusal_queues_the_next_registered_pose_only_at_bootstrap():
    probe = module("probe")
    observed = {
        "kind": "both",
        "stopped_stage": "pixel_bootstrap",
        "reason": (
            "initial RGB-D identity/extent unavailable: target_outer_boundary_depth_unresolved"
        ),
    }
    assert probe.visibility_limited(observed)
    assert not probe.visibility_limited({**observed, "stopped_stage": "original_plan"})
    assert not probe.visibility_limited({**observed, "reason": "foreign source"})


def test_low_bracket_contacts_include_uprights_and_crossbars_only_as_supports():
    t = module("trials")
    raw = [
        {
            "physics_step": 12,
            "contact_pairs": [
                ["left_finger_geom", "g1_dual_id8_upright"],
                ["g1_dual_id7_crossbar", "right_finger_geom"],
            ],
        },
        {
            "physics_step": 13,
            "contact_pairs": [
                ["object_geom", "right_finger_geom"],
                ["hand", "g1_dual_id8_plate"],
            ],
        },
    ]
    found = t.hand_contacts(raw)
    assert found["block_both_fingers_steps"] == []
    assert found["block_hand_or_finger_steps"] == [13]
    assert found["board_or_support_hand_or_finger_steps"] == [12, 13]


def test_low_bracket_build_seals_both_source_generations_and_distinct_asset(tmp_path):
    builder = module("build")
    destination = tmp_path / "isolated"
    lock = builder.build(ROOT, destination, assembly="v2")
    provider = "scripts/graduation/g1_dual_asset.py"
    ancestor = "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_v1.xml"
    new = (
        "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml"
    )
    assert lock["development_assembly"] == "v2"
    assert lock["runtime_files_sha256"][ancestor] != lock["runtime_files_sha256"][new]
    assert (
        lock["asset_provider_source"]["original_sha256"] != lock["runtime_files_sha256"][provider]
    )
    assert (
        lock["asset_provider_source"]["effective_sha256"] == lock["runtime_files_sha256"][provider]
    )
    assert builder.load_lock(destination) == lock
