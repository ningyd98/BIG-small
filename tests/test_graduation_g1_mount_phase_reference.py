from copy import deepcopy

import mujoco
import pytest
from scripts.graduation import g1_mount_phase_reference as ref
from scripts.graduation import g1_mount_phases as phases
from scripts.graduation.perception_io import ROOT
from scripts.graduation.proposal_camera import CHECK_LIMITS, restore

NAMES = {"APPROACH": "approach", "GRASP": "grasp", "LIFT": "lift"}
LIMITS = {"tcp_residual_m": 1e-5, "object_center_residual_m": 1e-8, "object_rotation_max_abs": 1e-8}
TICKS = {"APPROACH": [0, 1, 2], "GRASP": [2, 3, 4], "LIFT": [4, 5, 6]}
SPANS = [
    {"stage": name, "status": "RETURNED", "start_step": 2 * i, "end_step": 2 * i + 2}
    for i, name in enumerate(NAMES.values())
]


def test_nine_phase_roles_have_seven_unique_source_steps():
    actual = ref.samples_from_stages(SPANS, NAMES, TICKS)
    assert actual == TICKS
    assert len({s for ticks in actual.values() for s in ticks}) == 7


@pytest.mark.parametrize("change", [{"stage": "release"}, {"end_step": 3}, {"status": "ERROR"}])
def test_wrong_source_phase_cannot_supply_g1_reference(change):
    spans = deepcopy(SPANS)
    spans[1].update(change)
    with pytest.raises(ValueError, match="stage"):
        ref.samples_from_stages(spans, NAMES, TICKS)


@pytest.mark.parametrize("name", LIMITS)
def test_fk_registration_and_measurement_are_bound_to_three_actual_fields(name):
    without = {k: v for k, v in LIMITS.items() if k != name}
    assert ref.valid_fk_registration(LIMITS)
    assert phases.usable_reconstruction(True, LIMITS)
    assert not phases.usable_reconstruction(False, LIMITS)
    for invalid in (
        without,
        CHECK_LIMITS,
        {**LIMITS, name: LIMITS[name] + 1e-12},
        {**LIMITS, name: -1.0},
        {**LIMITS, name: float("nan")},
        {**LIMITS, name: float("inf")},
        {**LIMITS, name: None},
        {**LIMITS, name: False},
    ):
        assert not ref.valid_fk_registration(invalid)
        assert not phases.usable_reconstruction(True, invalid)
    assert not ref.valid_fk_registration({**LIMITS, name: LIMITS[name] / 2})


def test_real_mujoco_forward_restore_returns_only_the_registered_residuals():
    model = mujoco.MjModel.from_xml_path(str(ROOT / "assets/robots/franka_panda/scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    geom = data.geom("object_geom")
    state = {
        "sim_time_s": 0,
        "joint_positions_rad": [0.0] * 7,
        "joint_velocities_rad_s": [0.0] * 7,
        "finger_positions_m": [0.0, 0.0],
        "finger_velocities_m_s": [0.0, 0.0],
        "object_position_m": geom.xpos.tolist(),
        "object_geom_position_m": geom.xpos.tolist(),
        "object_geom_rotation_row_major": geom.xmat.tolist(),
        "tcp_position_m": data.site("tcp").xpos.tolist(),
    }
    actual = restore(model, data, state)
    assert actual.keys() == LIMITS.keys()
    assert phases.usable_reconstruction(True, actual)


def test_phase_reference_rejects_unregistered_plan(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="SHA|sha|digest|pin"):
        ref.reference_records({}, path, "r579")
