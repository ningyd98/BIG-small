"""Evidence recorder for the one isolated 5.5-second LIFT development slot."""

from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.perception_io import read, write

from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference

QUALIFICATION_LABEL = "train-t01-lift55-qualification-01"
CASE_ID = "cvfix-t01"
DEVELOPMENT_STEP_LIMIT = 3672
CAPTURE_REQUEST_LIMIT = 512
ENTRY_ATOL = 1e-10

ARM_PACKET_FIELDS = (
    "joint_positions_rad",
    "joint_velocities_rad_s",
    "finger_positions_m",
    "finger_velocities_m_s",
    "tcp_position_m",
    "tcp_quaternion_wxyz",
    "camera_joint_positions_rad",
    "camera_finger_positions_m",
)
DRIVE_FIELDS = (
    "entry_target_rad",
    "entry_effective_arm_goal_rad",
    "entry_native_arm_velocity_rad_s",
    "entry_finger_target_m",
)


class QualificationLiftReference(CartesianMotionReference):
    """Change only the time law of the original reference."""

    duration_s = 5.5


def reference_class(path):
    if path is not None and path.skill == "LIFT":
        return QualificationLiftReference
    return CartesianMotionReference


class LiftTrace:
    def __init__(self, episode):
        self.episode = episode
        self.backend = episode.backend
        self.steps = []
        self.frames = []
        self.reference = None
        self.entry = read(Path(__file__).with_name("g1_lift55_entry.json"))
        self.signature = mujoco.mjtState.mjSTATE_INTEGRATION

    def state(self):
        backend = self.backend
        model, data = backend._model, backend._data
        expected = mujoco.mj_stateSize(model, self.signature)
        packed = np.empty(expected, dtype="<f8")
        mujoco.mj_getState(model, data, packed, self.signature)
        return {
            "integration": packed.tolist(),
            "physics_step": backend.total_physics_steps,
            "sim_time_s": float(data.time),
            "ctrl": data.ctrl.tolist(),
            "qfrc_bias_arm": data.qfrc_bias[:7].tolist(),
            "arm_target": backend._target_positions.tolist(),
            "pending": [[tick, target.tolist()] for tick, target in backend._pending_joint_targets],
            "actuator_delay_steps": backend._actuator_delay_steps,
            "command_count": len(backend._command_records),
            "gripper_open": backend._gripper_open,
            "estop": backend.estop_engaged,
        }

    def before_step(self, event):
        state = self.state()
        if event.physics_step != state["physics_step"] + 1:
            raise ValueError("qualification actuator step and native state differ")
        if event.physics_step > DEVELOPMENT_STEP_LIMIT:
            raise ValueError("qualification LIFT physical budget exceeded")
        if (
            tuple(state["ctrl"][:7]) != event.control_rad
            or tuple(state["ctrl"][7:]) != event.finger_control_targets_m
        ):
            raise ValueError("qualification actuator observation differs")
        self.steps.append(state)

    def decision(self, frame, phase, robot, target, original):
        session = self.episode.robot._visual_servo_session
        if session is not None and getattr(session, "qualification_lift_reference", None):
            self.reference = session.qualification_lift_reference
        self.frames.append(
            {
                "frame_id": frame.frame_id,
                "checksum_sha256": frame.checksum_sha256,
                "phase": phase,
                "status": original["status"],
                "reason": original["reason"],
                "motion": original.get("short_motion"),
                "source_support": original.get("source_table_support"),
                "state": self.state(),
            }
        )
        if phase == "PRE" and original["status"] == "CLEAR":
            if (
                robot["physics_step"] != self.entry["step"]
                or target != self.entry["target"]
                or robot["handoff"]["entry_command_seq"] != self.entry["command_seq"]
                or robot["last_accepted_gripper_open"] is not False
            ):
                raise ValueError("5.5 s candidate differs at the real native LIFT entry")
            for field in ARM_PACKET_FIELDS:
                if not np.allclose(
                    robot[field], self.entry["robot"][field], atol=ENTRY_ATOL, rtol=0
                ):
                    raise ValueError(f"5.5 s entry measured encoder differs: {field}")
            for field in DRIVE_FIELDS:
                if not np.allclose(
                    robot["handoff"][field], self.entry["drive"][field], atol=ENTRY_ATOL, rtol=0
                ):
                    raise ValueError(f"5.5 s entry drive differs: {field}")

    def publish(self):
        write(
            self.episode.raw.parent / "lift-qualification-trace.json",
            {
                "scope": "t01 candidate LIFT, original guards, no transfer dispatch",
                "state_signature": int(self.signature),
                "entry_observable_source_sha256": self.entry["source_sha256"],
                "native_scenario_mass_kg": self.backend._scenario.object_mass_kg,
                "native_scenario_friction_coefficient": self.backend._scenario.friction_coefficient,
                "reference": self.reference,
                "frames": self.frames,
                "before_integrations": self.steps,
            },
        )
