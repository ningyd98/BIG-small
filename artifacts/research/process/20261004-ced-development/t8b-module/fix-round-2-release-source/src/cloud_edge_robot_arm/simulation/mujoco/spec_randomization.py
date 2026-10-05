"""Compile a run-specific MuJoCo model through the public MjSpec API."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MjSpecParameterEvidence:
    parameter: str
    value: float
    adapter: str
    target: str
    application_stage: str

    def to_jsonable(self) -> dict[str, object]:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "adapter": self.adapter,
            "target": self.target,
            "application_stage": self.application_stage,
        }


@dataclass(frozen=True)
class MjSpecBuildResult:
    model: Any
    spec_xml_sha256: str
    evidence: tuple[MjSpecParameterEvidence, ...]


def compile_randomized_mjspec_model(
    mujoco: Any,
    *,
    model_path: Path,
    parameters: Mapping[str, float],
) -> MjSpecBuildResult:
    """Parse, patch, and compile MJCF once for a deterministic run.

    MuJoCo 3.3.7 is the minimum supported version because it exposes stable
    named MjSpec accessors.  Sensor noise and the compatibility actuator-delay
    queue are intentionally applied by the backend after compilation and are
    still recorded in the returned evidence.
    """

    spec_type = getattr(mujoco, "MjSpec", None)
    if spec_type is None or not hasattr(spec_type, "from_file"):
        raise RuntimeError("MuJoCo >= 3.3.7 with MjSpec.from_file is required")
    try:
        spec = spec_type.from_file(str(model_path))
    except TypeError as exc:
        raise RuntimeError("MuJoCo >= 3.3.7 MjSpec classmethod API is required") from exc

    evidence: list[MjSpecParameterEvidence] = []
    if "object_mass_kg" in parameters:
        value = float(parameters["object_mass_kg"])
        spec.geom("object_geom").mass = value
        evidence.append(_evidence("object_mass_kg", value, "geom.mass", "object_geom", "MJSPEC"))

    if "friction_coefficient" in parameters:
        value = float(parameters["friction_coefficient"])
        geom = spec.geom("object_geom")
        friction = [float(item) for item in geom.friction]
        friction[0] = value
        geom.friction = friction
        evidence.append(
            _evidence(
                "friction_coefficient",
                value,
                "geom.friction[0]",
                "object_geom",
                "MJSPEC",
            )
        )

    if "joint_damping_scale" in parameters:
        value = float(parameters["joint_damping_scale"])
        targets: list[str] = []
        for joint in spec.joints:
            if not str(joint.name).startswith("joint"):
                continue
            try:
                damping = [float(item) for item in joint.damping]
            except TypeError:
                # MjSpec 3.3.x exposes scalar damping; newer releases expose
                # the three-value joint-axis representation.
                joint.damping = float(joint.damping) * value
            else:
                damping[0] *= value
                joint.damping = damping
            targets.append(str(joint.name))
        evidence.append(
            _evidence(
                "joint_damping_scale",
                value,
                "joint.damping[0]*scale",
                ",".join(targets),
                "MJSPEC",
            )
        )

    if "actuator_gain_scale" in parameters:
        value = float(parameters["actuator_gain_scale"])
        targets = []
        for actuator in spec.actuators:
            if not str(actuator.name).startswith("act"):
                continue
            gain = [float(item) for item in actuator.gainprm]
            bias = [float(item) for item in actuator.biasprm]
            gain[0] *= value
            bias[1] *= value
            actuator.gainprm = gain
            actuator.biasprm = bias
            targets.append(str(actuator.name))
        evidence.append(
            _evidence(
                "actuator_gain_scale",
                value,
                "actuator.gainprm/biasprm",
                ",".join(targets),
                "MJSPEC",
            )
        )

    if "gravity_z_m_s2" in parameters:
        value = float(parameters["gravity_z_m_s2"])
        gravity = [float(item) for item in spec.option.gravity]
        gravity[2] = value
        spec.option.gravity = gravity
        evidence.append(_evidence("gravity_z_m_s2", value, "option.gravity[2]", "world", "MJSPEC"))

    if "actuator_delay_ms" in parameters:
        value = float(parameters["actuator_delay_ms"])
        evidence.append(
            _evidence(
                "actuator_delay_ms",
                value,
                "deterministic_control_queue",
                "all_arm_actuators",
                "RUNTIME",
            )
        )

    if "camera_depth_noise_m" in parameters:
        value = float(parameters["camera_depth_noise_m"])
        evidence.append(
            _evidence(
                "camera_depth_noise_m",
                value,
                "sensor_noise_std_m",
                "camera/depth",
                "RUNTIME",
            )
        )

    xml = spec.to_xml()
    return MjSpecBuildResult(
        model=spec.compile(),
        spec_xml_sha256=hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        evidence=tuple(evidence),
    )


def _evidence(
    parameter: str,
    value: float,
    adapter: str,
    target: str,
    stage: str,
) -> MjSpecParameterEvidence:
    return MjSpecParameterEvidence(
        parameter=parameter,
        value=value,
        adapter=adapter,
        target=target,
        application_stage=stage,
    )
