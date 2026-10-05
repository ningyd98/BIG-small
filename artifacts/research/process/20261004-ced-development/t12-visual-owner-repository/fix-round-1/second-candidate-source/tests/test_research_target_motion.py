"""Offline target perturbations move through MuJoCo forces and retain timing."""

import numpy as np
import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalFault, PhysicalFaultType
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


def test_target_motion_changes_pose_only_through_physics_steps():
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=False, render_depth=False,
                                             domain_randomization=False)) as capture:
        backend = capture._backend
        backend.step(120)
        before = backend.current_physics_observation().object_position_m
        backend.inject_fault(PhysicalFault(PhysicalFaultType.TARGET_MOTION,
            {"speed_m_s": .02, "duration_s": 1., "direction_y": 1.}))
        assert backend.current_physics_observation().object_position_m == before
        backend.step(240)
        after = backend.current_physics_observation().object_position_m
        assert .01 < after[1] - before[1] < .03
        assert np.isfinite(after).all()
        assert backend.fault_records[0]["physics_step"] == 120
        backend.step(120)
        assert backend.fault_records[-1]["event"] == "TARGET_MOTION_FINISHED"


@pytest.mark.parametrize("speed", [-1., float("nan"), float("inf")])
def test_motion_fault_rejects_invalid_configuration(speed):
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=False, render_depth=False,
                                             domain_randomization=False)) as capture:
        with pytest.raises(ValueError):
            capture._backend.inject_fault(PhysicalFault(PhysicalFaultType.TARGET_MOTION,
                                                       {"speed_m_s": speed}))
