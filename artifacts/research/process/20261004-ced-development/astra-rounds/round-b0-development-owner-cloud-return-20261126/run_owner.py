"""Exercise a real B0 SQLite owner at a bounded, no-action development boundary."""

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import patch

from scripts.probe_rgbd_roles import read_role_config

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.research.freeze_evidence import _registered_observation
from cloud_edge_robot_arm.research.pilot_worker import PilotWorkerAttempt
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, VisualEpisodeOutcome
from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    cloud_request_settings,
    configuration_hash,
)
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding
from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
PLAN_PATH = HERE / "plan.json"
PLAN = json.loads(PLAN_PATH.read_bytes())
FIXTURE = HERE / "local-response.json"
FIXTURE_SHA256 = "fecc89155c2cf8346ed30ae62d9a67c1d8850383a4199b322eb1468dcfa99213"
SCENE = ROOT / PLAN["frozen_scene"]
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, body):
    with path.open("x", encoding="utf-8") as f:
        json.dump(body, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def forbid_network(event, args):
    if event.startswith("socket.") and event not in {"socket.__new__"}:
        raise PermissionError("local fixture may not access sockets or resolve names")


def check_inputs():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    need(head == PLAN["baseline"], "unexpected development commit")
    for path, expected in (PLAN["source_sha256"] | PLAN["evidence_sha256"]).items():
        need(digest(ROOT / path) == expected, f"pinned input changed: {path}")
    need(digest(FIXTURE) == FIXTURE_SHA256, "fixture drift")
    receipt = read(SCENE / "capture/receipt.json")
    for name, expected in receipt["files_sha256"].items():
        need(digest(SCENE / "capture" / name) == expected, f"raw capture changed: {name}")


def role():
    cfg = read_role_config(ROOT / "configs/research/ced_roles.yaml")
    snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model="b0-local-fixture",
        endpoint="http://127.0.0.1:9",
        weight_digest=None,
        quantization=None,
        image_size=tuple(cfg["cloud"]["image_size"]),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=15,
        coordinate_system=cfg["cloud"]["coordinate_system"],
        grasp_profile=cfg["cloud"]["grasp_profile"],
    )
    planner = resolve_visual_planner(snapshot, allow_paid=False)
    edge_cfg = cfg["edge"]
    edge_policy = edge_cfg["policy"]
    cloud_paths = ["src/cloud_edge_robot_arm/vision/planner.py", str(FIXTURE.relative_to(ROOT))]
    cloud = RoleProviderSnapshot(
        "CLOUD",
        "development-rgb-seed-fixture",
        "LOCAL_HOST",
        snapshot.model,
        None,
        None,
        None,
        configuration_hash(cloud_request_settings(planner)),
        {path: digest(ROOT / path) for path in cloud_paths},
    )
    edge = RoleProviderSnapshot(
        "EDGE",
        edge_cfg["provider_id"],
        edge_cfg["provider_location"],
        None,
        None,
        None,
        None,
        configuration_hash(edge_policy),
        {path: digest(ROOT / path) for path in edge_cfg["source_paths"]},
    )
    device = {path: digest(ROOT / path) for path in cfg["device"]["source_paths"]}
    bundle = RoleModelBundle(cloud, edge.provider_id, edge.digest(), configuration_hash(device))
    planner.role_snapshot = cloud
    binding = RoleRuntimeBinding(bundle, edge, device, edge_policy, root=ROOT)
    binding.validate(planner)
    return planner, binding, VerificationBudget(**edge_policy["verification_budget"])


def attempt(stage, output, registration, planner, binding):
    from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec

    scene = SceneSpec.model_validate(registration["scene"])
    assignment = {
        "assignment_id": f"b0-owner-diagnostic-{stage}",
        "group_id": scene.group_id,
        "physics_seed": scene.seed,
        "scene_hash": scene.scene_hash,
        "role_bundle_hash": binding.bundle.digest(),
        "period_s": None,
        "stratum_id": "STATIC_RTT0",
        "network_schedule": None,
        "base_assignment": {"scene": registration["scene"], "perturbation": {}},
    }
    owner = PilotWorkerAttempt(
        planner=planner,
        binding=binding,
        assignment=assignment,
        directory=output,
        runtime_directory=output / "worker-runtime",
        timeout_s=120,
    )
    actual_xml_hash = hashlib.sha256(owner.model_xml.encode()).hexdigest()
    need(actual_xml_hash == registration["compiled_xml_sha256"], "compiled scene hash changed")
    return owner


def runtime_for(owner, episode_id, limits):
    return VisualWorkerRuntime(
        owner.source,
        episode_id=episode_id,
        instruction=owner.instruction,
        role_binding=owner.binding,
        model_snapshot_hash=owner.planner.model_snapshot.digest(),
        verification_limits=limits,
    )


def mark_failed(owner, reason):
    owner.record_outcome(
        VisualEpisodeOutcome(
            success=False,
            status="FAILED",
            safety_violation=False,
            failure_reason=reason,
            measured_lift_m=0,
            hold_s=0,
            placed_stable_s=0,
            elapsed_s=0,
            terminal_reason=reason,
        )
    )


def stale(owner, previous, limits):
    runtime = runtime_for(owner, previous.episode_id, limits)
    software_state = RobotState(connected=True)
    claim = runtime.reserve_capture(software_state, initial=True)
    before = runtime.bootstrap
    try:
        runtime.complete_capture(claim, previous, software_state)
    except ValueError as error:
        reason = str(error)
    else:
        raise RuntimeError("historical frame accepted as a current capture")
    need(reason == PLAN["stage_a"]["expected_rejection"], "unexpected historical rejection")
    after = runtime.bootstrap
    need(
        after.digest() == before.digest() and after.observation is None and not runtime.is_adopted,
        "failed capture changed persisted bootstrap",
    )
    mark_failed(owner, "DEVELOPMENT_HISTORICAL_FRAME_REFUSED")
    return {
        "reason": reason,
        "bootstrap_id": after.definition.bootstrap_id,
        "bootstrap_revision": after.revision,
        "pending_claim_id": claim,
        "claimed_at": before.to_payload()["pending"]["claimed_at"],
        "actual_historical_frame": previous.evidence(),
        "native_episode_used_only_for_clock_negative": True,
        "physical_backend_created": False,
    }


class ProbeBoundary(Exception):
    """A developer budget stops before the next production effect."""


def fresh(owner, previous, limits, output):
    backend = MuJoCoPhysicsBackend()
    exposure_counts = []
    steps = []
    prohibited = []
    provider_calls = []
    original_capture = MuJoCoRGBDCamera._capture
    native_step = backend.step

    def no_action(name):
        def rejected(*args, **kwargs):
            prohibited.append(name)
            raise ProbeBoundary(f"unplanned action requested: {name}")

        return rejected

    def capture_checked(camera, data, **kwargs):
        need(len(exposure_counts) < 3, "exposure budget exceeded before camera call")
        exposure_counts.append(backend.total_physics_steps)
        return original_capture(camera, data, **kwargs)

    def step_checked(steps_requested=1, **kwargs):
        count = kwargs.get("steps", steps_requested)
        need(steps == [] and count == 120, "integration budget exceeded before native step")
        steps.append(count)
        return native_step(count)

    def fixture_response(messages, schema):
        need(not provider_calls, "fixture response budget exceeded")
        provider_calls.append(FIXTURE_SHA256)
        return {"choices": [{"message": {"content": FIXTURE.read_text()}}]}

    try:
        backend.initialize(owner.config, model_xml=owner.model_xml)
        backend._sensor_noise_std_m = 0.0
        with ExitStack() as stack:
            for name in (
                "apply_joint_targets",
                "apply_gripper_command",
                "emergency_stop",
                "hold_current_joints",
                "inject_fault",
            ):
                stack.enter_context(patch.object(backend, name, no_action(name)))
            stack.enter_context(patch.object(backend, "step", side_effect=step_checked))
            stack.enter_context(patch.object(MuJoCoRGBDCamera, "_capture", capture_checked))
            stack.enter_context(
                patch.object(
                    SkillExecutor, "execute_attempt", side_effect=no_action("execute_attempt")
                )
            )
            stack.enter_context(
                patch.object(owner.planner, "_request_visual", side_effect=fixture_response)
            )
            robot = MuJoCoSkillRobot(backend)
            capture = stack.enter_context(MuJoCoCaptureSession(owner.config, backend=backend))
            recorder = stack.enter_context(
                VisualRawRecorderV3(
                    backend,
                    capture,
                    SkillExecutor(robot=robot, registry=SkillRegistry.default()),
                    directory=output / "raw_episode_v3",
                    source_root=owner.binding.root,
                    source_hashes=owner.source.source_hashes,
                )
            )
            backend.reset(owner.scenario)
            with recorder.purpose("SETTLE"):
                backend.step(steps=120)
            runtime = runtime_for(owner, backend._episode_id, limits)
            policy = ExecutionPolicy(
                instruction=owner.instruction,
                model_snapshot_hash=owner.planner.model_snapshot.digest(),
                timeout_s=owner.remaining_s(),
                output_dir=output,
                advance_physics_during_wait=True,
                verification_budget=limits,
                device_pipeline="OPENCV",
                role_binding=owner.binding,
                worker_runtime=runtime,
                raw_recorder=recorder,
                cancelled=owner.cancelled,
            )
            episode = _VisualEpisode(owner.planner, robot, capture, policy)
            observation = episode.recapture()
            compare = (
                "camera_to_world",
                "intrinsics",
                "calibration_version",
                "sim_time_s",
                "rgb_png_base64",
                "depth_float32_base64",
                "valid_mask_base64",
            )
            need(
                all(getattr(observation, field) == getattr(previous, field) for field in compare),
                "fresh development capture differs from archived target image or camera",
            )
            need(
                observation.episode_id != previous.episode_id
                and observation.captured_at > previous.captured_at,
                "unfresh camera identity",
            )
            request = InitialPlanningRequest(
                request_id="b0-owner-rgb-fixture",
                user_instruction=owner.instruction,
                observation=observation,
            )
            fixture = read(FIXTURE)
            for key, expected in (("target_pixel", (167, 112)), ("destination_pixel", (128, 67))):
                need(
                    model_to_observation_pixel(
                        fixture[key], observation, coordinate_system="normalized_1000"
                    )
                    == expected,
                    "frozen role pixel map changed",
                )
            claim_id = runtime.reserve_plan(robot.get_state())
            draft = owner.planner.plan(request)
            need(
                not draft.parse_error
                and draft.parsed_json
                and not draft.parsed_json.get("_sentinel"),
                f"local fixture did not ground: {draft.parse_error}",
            )
            draft.observation_evidence = {
                **draft.observation_evidence,
                "role_bundle_hash": owner.binding.bundle.digest(),
                "role_binding": owner.binding.evidence(),
            }
            runtime.complete_plan(claim_id, draft, robot.get_state())
            need(runtime.bootstrap.planning_source_usable, "actual owner fixture not usable")

            def recapture_budget(*, advance_steps=0, **kwargs):
                need(advance_steps == 1, "unexpected recapture request")
                raise ProbeBoundary("DEVELOPMENT_REOBSERVATION_REQUEST_NOT_EXECUTED")

            try:
                with (
                    patch.object(episode, "recapture", side_effect=recapture_budget),
                    patch.object(
                        episode, "prepare_worker_step", side_effect=no_action("prepare_worker_step")
                    ),
                ):
                    episode.run_worker_online(draft)
            except (_EpisodeStopped, ProbeBoundary) as error:
                terminal = str(error)
                terminal_cause = None if error.__cause__ is None else str(error.__cause__)
            else:
                raise RuntimeError("bounded diagnostic returned without a safe stop")
            gates = [row for row in episode.records if row["layer"] == "ACTION_EVIDENCE_GATE"]
            routes = [
                row for row in episode.records if row["layer"] == "WORKER_CANONICAL_VERIFICATION"
            ]
            write(
                output / "runtime-boundary.json",
                {
                    "terminal": terminal,
                    "terminal_cause": terminal_cause,
                    "bootstrap_id": runtime.bootstrap.definition.bootstrap_id,
                    "bootstrap_pending_claim": runtime.bootstrap.pending_claim_id,
                    "original_adopted": runtime.is_adopted,
                    "observation": observation.evidence(),
                    "original_hash": runtime.original.digest() if runtime.is_adopted else None,
                    "publication_hash": runtime.publication.digest()
                    if runtime.is_adopted
                    else None,
                    "gates": gates,
                    "routes": routes,
                    "native_exposures_at_steps": exposure_counts,
                    "actual_integrations": backend.total_physics_steps,
                    "planner_fixture_calls": len(provider_calls),
                    "no_provider_transport": True,
                    "commands": backend.command_records,
                    "prohibited_attempts": prohibited,
                    "grounding_publications_in_scope": sum(
                        row["layer"] == "WORKER_FRESH_GROUNDING" for row in episode.records
                    ),
                },
            )
            mark_failed(owner, terminal)
            need(
                not prohibited
                and exposure_counts == [0, 120, 120]
                and steps == [120]
                and backend.total_physics_steps == 120
                and not backend.command_records,
                "unexpected command or acquisition budget",
            )
    finally:
        backend.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("A", "B"))
    args = parser.parse_args()
    sys.addaudithook(forbid_network)
    check_inputs()
    output_root = ROOT / PLAN["private_output"]
    if args.stage == "B":
        cold = output_root / "a-cold-read.json"
        need(
            digest(cold) == "93b31cf63de98ce6c7224aa9ca47588fbbdf2c6df8e30c07df1b3f71159c2520"
            and cold.read_bytes() == (output_root / "a-cold-read-2.json").read_bytes()
            and read(cold)["pass"] is True,
            "stage A not eligible",
        )
    output = output_root / args.stage
    output.mkdir(exist_ok=False)
    registration = read(SCENE / "registration.json")
    previous = _registered_observation(SCENE / "capture/step-0120")
    planner, binding, limits = role()
    write(
        output / "registration.json",
        {
            "plan_sha256": digest(PLAN_PATH),
            "driver_sha256": digest(Path(__file__)),
            "fixture_sha256": FIXTURE_SHA256,
            "role": binding.evidence(),
            "stage": args.stage,
        },
    )
    with LOCK.open("rb") if args.stage == "B" else nullcontext() as lock:
        if lock is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with attempt(args.stage, output, registration, planner, binding) as owner:
            if args.stage == "A":
                write(output / "stale.json", stale(owner, previous, limits))
            else:
                fresh(owner, previous, limits, output)


if __name__ == "__main__":
    main()
