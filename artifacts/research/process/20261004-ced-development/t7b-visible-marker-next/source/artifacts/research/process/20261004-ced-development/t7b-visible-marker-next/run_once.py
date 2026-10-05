"""One excluded offline teacher episode; no production executor or model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_episode,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_observation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

HERE = Path(__file__).resolve().parent
ASSET = Path("assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml")
ASSET_HASH = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def specification() -> tuple[SceneSpec, SimulatorConfig]:
    assert hashlib.sha256(ASSET.read_bytes()).hexdigest() == ASSET_HASH
    scene = SceneSpec.from_parameters(
        {
            "target": {
                "position": [0.45, 0.0, 0.043],
                "half_size": [0.035] * 3,
                "rgba": [0.9, 0.12, 0.08, 1.0],
                "color_name": "red",
                "mass_kg": 0.08,
                "friction": 0.8,
            },
            "distractors": [],
            "destination": {
                "position": [0.2, 0.25, 0.002],
                "half_size": [0.08, 0.08, 0.002],
                "rgba": [0.1, 0.6, 0.2, 1.0],
            },
            "camera": {
                "position": [0.35, 0.0, 1.4],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "fovy": 50.0,
            },
            "light_intensity": 0.8,
            "depth_noise_m": 0.0,
            "invalid_depth_fraction": 0.0,
        },
        ASSET_HASH,
        seed=0,
    )
    scene = SceneSpec.model_validate(
        {**scene.model_dump(), "group_id": "dev-marker-outboard-" + scene.scene_hash[:24]}
    )
    config = SimulatorConfig(
        model_path=str(ASSET),
        seed=0,
        domain_randomization=False,
        camera_width=640,
        camera_height=480,
        render_rgb=True,
        render_depth=True,
        max_episode_s=60.0,
    )
    return scene, config


def prepare() -> None:
    scene, config = specification()
    previous = HERE.parent / "t7b-pose-marker-color/source-hashes.json"
    sources = set(json.loads(previous.read_text())) | {
        "src/cloud_edge_robot_arm/vision/pose_marker_visibility.py",
        "tests/test_pose_marker_visibility.py",
        str(ASSET),
        "src/cloud_edge_robot_arm/datasets/rgbd/teacher.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/scene_sampler.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
    }
    sources.add(str(Path(__file__).relative_to(Path.cwd())))
    hashes = {}
    for name in sorted(sources):
        path = Path(name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(HERE / "source-hashes.json", hashes)
    write(
        HERE / "header.json",
        {
            "scope": "EXCLUDED_OFFLINE_DEVELOPMENT_ACTUAL_SIMULATED_CONTROLLER_ACTIONS",
            "scenario": "S01_NORMAL_STATIC",
            "case": "NORMAL",
            "attempt_limit": 1,
            "scene": scene.model_dump(mode="json"),
            "scene_hash": scene.scene_hash,
            "config": config.model_dump(mode="json"),
            "formal_source_eligible": False,
            "excluded_development_group": scene.group_id,
            "source_manifest_sha256": hashlib.sha256(
                (HERE / "source-hashes.json").read_bytes()
            ).hexdigest(),
            "model_calls": 0,
            "settle_steps": 120,
            "capture_policy": "EXISTING_T5_ACTION_BOUNDARIES_ONLY",
            "teacher_ground_truth": "OFFLINE_TARGETS_AND_INDEPENDENT_SCORER_ONLY",
            "detector_inputs": "RGBDObservation plus ID7/45mm/asset registration ONLY",
            "continuous_certificate": "UNAVAILABLE",
            "native_admission": "NOT_PROMOTED",
            "G1_G4_acceptance": "NOT_RUN",
            "new_profile": "marker-outboard-v3-S01-motion-native640-development-only",
            "cadence_ruling": "SCRIPT_ONLY suppress cached pixel updates after apply_scene; explicit T5 boundary captures unchanged; setup renders counted separately",
            "cadence_guards": "robot.observe and backend.get_sensor_frame abort; frozen motion_controller contains no cached sensor reads",
            "depth_noise_m": 0.0,
        },
    )
    write(
        HERE / "development-exclusion.json",
        {
            "scope": "EXCLUDED_DEVELOPMENT_ONLY",
            "group_id": scene.group_id,
            "scene_hash": scene.scene_hash,
            "asset_sha256": ASSET_HASH,
            "actual_marker_offset_object_m": [0.1, 0.0, 0.03505],
            "marker_size_m": 0.045,
            "physical_mount_accepted": False,
            "formal_source_eligible": False,
            "controller_or_camera_changed": False,
            "previous_negative_episode_retained": "../t7b-pose-marker-motion-development",
        },
    )
    print("PREPARED exact source/scene header; zero renderer/model/controller calls")


def execute_once() -> None:
    header = json.loads((HERE / "header.json").read_text())
    for name, expected in json.loads((HERE / "source-hashes.json").read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
    directory = HERE / "attempt-1"
    directory.mkdir(exist_ok=False)  # no replay/resume/fallback
    scene, config = specification()
    assert scene.model_dump(mode="json") == header["scene"]
    recorder = EpisodeRecorder()
    registration = PoseMarkerRegistration(7, 0.045, ASSET_HASH)
    started = time.monotonic()
    failure = None
    outcome = None
    render_counts = {
        "setup_rgbd_capture_calls": 0,
        "explicit_boundary_rgbd_instance_calls": 0,
        "cached_updates_suppressed": 0,
    }
    original_camera_capture = MuJoCoRGBDCamera.capture
    original_camera_instances = MuJoCoRGBDCamera.capture_with_instances

    def counted_setup(camera, *args, **kwargs):
        render_counts["setup_rgbd_capture_calls"] += 1
        return original_camera_capture(camera, *args, **kwargs)

    def counted_boundary(camera, *args, **kwargs):
        render_counts["explicit_boundary_rgbd_instance_calls"] += 1
        return original_camera_instances(camera, *args, **kwargs)

    MuJoCoRGBDCamera.capture = counted_setup
    MuJoCoRGBDCamera.capture_with_instances = counted_boundary
    with (
        (directory / "raw-physics.jsonl").open("w") as physical,
        (directory / "raw-actuators.jsonl").open("w") as actuator,
        (directory / "raw-actions.jsonl").open("w") as action,
    ):

        def record(stream, row):
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()

        with MuJoCoCaptureSession(config) as session:
            session.apply_scene(scene)
            backend = session._backend
            # Process-only instrumentation under root's explicit cadence ruling.
            # Original backend/controller/teacher files are unchanged.
            original_update = backend._update_sensor_frame
            original_get_sensor = backend.get_sensor_frame

            def suppress_cached_render():
                render_counts["cached_updates_suppressed"] += 1

            def forbidden_cached_sensor(*args, **kwargs):
                raise RuntimeError("cached sensor/robot.observe use violates bounded T5 cadence")

            controller_source = Path(
                "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"
            ).read_text()
            assert all(
                text not in controller_source
                for text in ("_sensor_frame", "get_sensor_frame", ".sensor_frame")
            )
            backend._update_sensor_frame = suppress_cached_render
            backend.get_sensor_frame = forbidden_cached_sensor
            robot = MuJoCoSkillRobot(backend)
            robot.observe = forbidden_cached_sensor
            try:
                with backend.observe_actuator_steps(lambda row: record(actuator, asdict(row))):
                    outcome = run_teacher_episode(
                        scene,
                        robot,
                        recorder,
                        case="NORMAL",
                        settle_steps=120,
                        physical_observer=lambda row: record(physical, asdict(row)),
                        action_observer=lambda row: record(action, dict(row)),
                    )
                # Existing independent evaluator; no skill-status override.
                rescored = evaluate_episode(
                    backend,
                    CompletionCriteria("object", "target_region"),
                    evidence=recorder.physical_samples,
                    evaluation_start_step=recorder.evaluation_start_step,
                )
                assert rescored == outcome
            except BaseException:
                failure = traceback.format_exc()
                (directory / "failure.txt").write_text(failure)
            finally:
                backend._update_sensor_frame = original_update
                backend.get_sensor_frame = original_get_sensor
                MuJoCoRGBDCamera.capture = original_camera_capture
                MuJoCoRGBDCamera.capture_with_instances = original_camera_instances
                write(directory / "commands.json", backend.command_records)
                write(
                    directory / "physical-samples.json",
                    [asdict(r) for r in recorder.physical_samples],
                )
                write(
                    directory / "actions.json",
                    [f.action.model_dump(mode="json") for f in recorder.frames],
                )
                write(
                    directory / "unframed-actions.json",
                    [r.model_dump(mode="json") for r in recorder.unframed_actions],
                )
                observations = []
                if recorder.frames:
                    observations.append(("INITIAL_SETTLED", recorder.frames[0].observation))
                    observations.extend(
                        (f"AFTER_{i:02d}_{f.action.action_type}", f.next_observation)
                        for i, f in enumerate(recorder.frames, 1)
                    )
                measured = []
                for label, observation in observations:
                    dest = directory / "frames" / label
                    save_observation(observation, dest)
                    (dest / "valid_mask.u8").write_bytes(observation.valid_mask_bytes())
                    (dest / "observation-full.json").write_text(
                        observation.model_dump_json(indent=2) + "\n"
                    )
                    estimate = detect_pose_marker(observation, registration)
                    payload = asdict(estimate)
                    payload["captured_at"] = estimate.captured_at.isoformat()
                    write(dest / "marker-estimate.json", payload)
                    measured.append(
                        {
                            "boundary": label,
                            "sim_time_s": observation.sim_time_s,
                            "status": estimate.status,
                            "reason": estimate.reason,
                            "min_side_px": estimate.measured_min_side_px,
                            "checksum": observation.checksum_sha256,
                            "occlusion_claim": "UNCONFIRMED_IF_UNKNOWN",
                        }
                    )
                write(directory / "observability.json", measured)
                summary = {
                    "scope": header["scope"],
                    "formal_source_eligible": False,
                    "group_id": scene.group_id,
                    "scene_hash": scene.scene_hash,
                    "episode_id": backend._episode_id,
                    "model_calls": 0,
                    "controller_command_records": len(backend.command_records),
                    "executed_framed_actions": len(recorder.frames),
                    "executed_unframed_actions": len(recorder.unframed_actions),
                    "physics_steps": backend.total_physics_steps,
                    "evaluation_start_step": recorder.evaluation_start_step,
                    "outcome": asdict(outcome) if outcome else None,
                    "execution_verified_by_offline_scorer": recorder.execution_verified,
                    "run_status": "INFRASTRUCTURE_ERROR" if failure else "COMPLETED_SINGLE_ATTEMPT",
                    "elapsed_wall_s": time.monotonic() - started,
                    "rendered_boundary_observations": len(observations),
                    "render_call_counts": render_counts,
                    "cadence_instrumentation": "SCRIPT_ONLY_CACHED_UPDATE_SUPPRESSION_NOT_ORIGINAL_CADENCE_EQUIVALENCE",
                    "calibrated_error_bound": "UNAVAILABLE",
                    "continuous_motion_bound": "UNAVAILABLE",
                    "native_admission": "NOT_PROMOTED",
                    "G1_G4_acceptance": "NOT_RUN",
                }
                write(directory / "summary.json", summary)
                print(json.dumps(summary, indent=2))
    write(
        directory / "raw-hashes.json",
        {
            str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*"))
            if p.is_file()
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    prepare() if args.prepare else execute_once()
