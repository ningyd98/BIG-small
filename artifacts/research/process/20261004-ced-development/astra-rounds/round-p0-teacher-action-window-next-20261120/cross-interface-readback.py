"""Read the same archived RGB-D acquisitions across recorder and observation interfaces."""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from copy import deepcopy
from dataclasses import fields
from datetime import datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import patch

import benchmark_original_frames as bench
from PIL import Image

from cloud_edge_robot_arm.contracts import ExecutionCheckpoint, RobotState
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.research.native_archived_tracker import (
    _ArchivedRegisteredCollectionTrackerV2,
)
from cloud_edge_robot_arm.research.native_calibration_collection import ROOT, canonical, digest
from cloud_edge_robot_arm.research.native_collection_grounding import validate_registration_handoff
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    _Audit,
    _registered_lease_from_payload,
    _restore_frame,
)
from cloud_edge_robot_arm.research.native_full_horizon_recorder import _v2_feedback
from cloud_edge_robot_arm.research.raw_episode_v3 import RawEpisodeIdentityV3, _owner_decode
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision import capture, observations
from cloud_edge_robot_arm.vision.owner_registration import (
    RegisteredCollectionStepBindingV2,
    RegisteredGroundingFrameInputsV2,
    RegisteredGroundingPolicyV2,
    VisualOriginalPlan,
    prepare_registered_step_binding_v2,
)
from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3

BENCH = Path("experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/run-02")
INPUTS = {
    "preregistration.json": "7b81b263c41a05e08ac9cc428bd3315b0bfce79496b8aefa9f7182f8877e9078",
    "frame-measurements.jsonl": "126f8399005bcadd305e2c57a82a56d699d4526b9e52a3ef20c67be41abf4045",
    "summary.json": "86d5c7f3ca117634a81b1c00cc1a5a70de1d2977157012531b1ee63cac554a62",
    "independent-readback.json": "e287a27ff60c337d3006a6f7f6b50666d78ce6aed0988837c42e0d2cad9cb50c",
}
DECISION_SHA = "8d61eac42c6f08cc47f1e04fc0d24a0aa412d0cbe9b43dd5e3300e3ee6ef4da1"
ARCHIVE_SCOPE = "ARCHIVED_SENSOR_AND_RECORDED_UTC_ONLY"
EXPLICIT = "REGISTERED_ACTION_BOUNDARY"


def require_equal(left, right):
    bench.require(canonical(left) == canonical(right), "archived cross-interface value differs")


def archived_sensor(folder, observation, metadata, state):
    with Image.open(folder / "rgb.png") as image:
        bench.require(image.mode == "RGB", "archived RGB mode differs")
        pixels = image.tobytes()
    sensor = SensorFrame(
        **{
            key: getattr(observation, key)
            for key in (
                "frame_id",
                "sim_time_s",
                "width",
                "height",
                "camera_to_world",
                "captured_at",
                "scene_id",
                "episode_id",
                "calibration_version",
            )
        },
        rgb=pixels,
        depth=observation.depth_values(),
        intrinsics=tuple(observation.intrinsics),
        valid_mask=observation.valid_mask_bytes(),
    )
    instance_bytes = (folder / "instances.i32").read_bytes()
    ids = struct.unpack(f"<{len(instance_bytes) // 4}i", instance_bytes)
    labels = metadata["instance_labels"]
    result = {
        "sensor_frame": {field.name: getattr(sensor, field.name) for field in fields(sensor)},
        "pass_state_hashes": metadata["frame"]["pass_state_hashes"],
    }
    if metadata["instance_ids_present"]:
        result["instance_ids"] = ids
    if metadata["instance_labels_present"]:
        result["instance_labels"] = labels
    event = SimpleNamespace(
        operation_id=metadata["capture_source"]["operation_id"],
        parameters={
            "camera_state": metadata["frame"]["camera_state_payload"],
            "physics_state": state,
        },
        result=result,
    )
    aid = metadata["frame"]["acquisition_id"]
    return bench.Input(aid, folder, event, sensor, metadata, "OFFLINE_READBACK")


def matched_recorder_payload(root, metadata, archive, sensor, level):
    restored = _restore_frame(root, metadata)
    payload = restored["observation_payload"]
    if level == 6:
        require_equal(metadata, archive.metadata)
    else:
        expected = deepcopy(archive.metadata)
        expected["frame"]["observation_payload"]["checksum_sha256"] = payload["checksum_sha256"]
        expected["frame"]["file_hashes"][f"frames/{archive.aid}/rgb.png"] = restored["file_hashes"][
            f"frames/{archive.aid}/rgb.png"
        ]
        expected["encoded_string_sha256"]["rgb_png_base64"] = metadata["encoded_string_sha256"][
            "rgb_png_base64"
        ]
        expected["observation_payload_sha256"] = digest(payload)
        require_equal(metadata, expected)
    expected_payload = observations.observation_from_sensor_frame(
        sensor, source="mujoco_camera", png_compress_level=level
    ).model_dump(mode="json")
    require_equal(payload, expected_payload)
    for name in ("depth.f32", "mask.u8", "instances.i32"):
        bench.require(
            (root / "frames" / archive.aid / name).read_bytes()
            == (archive.folder / name).read_bytes(),
            "paired non-PNG originals changed",
        )
    with Image.open(root / "frames" / archive.aid / "rgb.png") as image:
        bench.require(image.mode == "RGB" and image.tobytes() == sensor.rgb, "paired RGB differs")
    return observations.RGBDObservation.model_validate(payload)


class ArchivedCaptureBackend:
    """Supply once, before session encoding, only the frozen explicit SensorFrame."""

    def __init__(self, recorder, archive, level):
        self.recorder, self.archive, self.level = recorder, archive, level
        self.calls = 0

    def capture_sensor_frame_with_instances(self):
        bench.require(
            not self.calls and self.archive.role == EXPLICIT, "source not explicit/unique"
        )
        bench.require(self.recorder._explicit_capture, "real recorder explicit path not entered")
        self.calls += 1
        encode = partial(observations.observation_from_sensor_frame, png_compress_level=self.level)
        bench.record_frame(self.recorder, self.archive, encode)
        data = self.archive.event.result
        return (
            self.archive.sensor,
            data["instance_ids"],
            {int(key): value for key, value in data["instance_labels"].items()},
            tuple(data["pass_state_hashes"]),
        )


def explicit_return(path, archive, session_level, recorder_level, pair_metadata_sha):
    recorder = bench.recorder_for(path)
    recorder._open, recorder._thread_id = True, get_ident()
    recorder._explicit_capture = recorder._derived_capture = False
    adapter = ArchivedCaptureBackend(recorder, archive, recorder_level)
    encoder = partial(observations.observation_from_sensor_frame, png_compress_level=session_level)
    with (
        capture.MuJoCoCaptureSession(SimulatorConfig(), backend=adapter) as session,
        patch.object(capture, "observation_from_sensor_frame", encoder),
    ):
        recorder.capture_session = session
        returned = VisualRawRecorderV3.capture(recorder)
    bench.require(
        adapter.calls == 1, "archived capture provider called an unexpected number of times"
    )
    captured = recorder.last_captured_frame
    bench.require(captured.observation is returned, "recorder returned foreign observation")
    data = archive.event.result
    require_equal(captured.instance_ids, data["instance_ids"])
    require_equal(
        {str(key): value for key, value in captured.instance_labels.items()},
        data["instance_labels"],
    )
    require_equal(captured.pass_state_hashes, data["pass_state_hashes"])
    require_equal(captured.physics_state_hash, data["pass_state_hashes"][0])
    source = recorder.frame_sources[archive.aid]
    bench.verified_file(path / source, pair_metadata_sha)
    restored = _restore_frame(path, bench.read(path / source))
    ref = dict(acquisition_id=archive.aid, path=source, sha256=recorder.inventory[source]["sha256"])
    return returned, restored["observation_payload"], ref


def must_reject(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except (ValueError, RuntimeError) as error:
        return {"type": type(error).__name__, "message": str(error)}
    raise AssertionError("production consumer accepted mismatched archival source")


def feedback_read(payload, observation, reference, state):
    _v2_feedback(
        payload,
        observation=observation,
        acquisition=reference,
        physics_step=120,
        robot_state=state.model_dump(mode="json"),
    )


def tracker_and_binding(audit, ground, pre, boot, explicit, level):
    ref_id = boot["acquisition"]["acquisition_id"]
    compiler_id = boot["compiler_reference_acquisition"]["acquisition_id"]
    reference, compiler = explicit[ref_id], explicit[compiler_id]
    initialized = datetime.fromisoformat(boot["finished_at"])
    validate_registration_handoff(
        audit.original,
        boot["registration_lease_source"],
        compiler,
        reference,
        step_before=120,
        step_after=120,
        now=initialized,
    )
    same_step_rejection = must_reject(
        lambda: validate_registration_handoff(
            audit.original,
            boot["registration_lease_source"],
            compiler,
            compiler,
            step_before=120,
            step_after=120,
            now=initialized,
        )
    )
    tracker = _ArchivedRegisteredCollectionTrackerV2(
        reference,
        audit.scope,
        source_root=ROOT,
        source_hashes=audit.original.source_hashes,
        initialized_at=initialized,
        nominal_policy=audit.protocol["region_policy"],
    )
    bench.require(ground["acquisition"]["acquisition_id"] == ref_id, "unexpected ground source")
    bench.require(pre["capture"]["acquisition_id"] == ref_id, "unexpected PRE acquisition")
    outputs = {}
    previews = {}
    for phase, source, state, expected_inputs in (
        (
            "grounding",
            ground["registered_preview"],
            ground["online"]["robot_state"],
            ground["inputs"],
        ),
        ("pre", pre["registered_preview"], pre["robot_state"], pre["registered_inputs"]),
    ):
        robot = RobotState.model_validate(state)
        preview = tracker.preview_at(
            reference,
            robot,
            evaluated_at=datetime.fromisoformat(source["track"]["evaluated_at"]),
            finished_at=datetime.fromisoformat(source["evaluated_at"]),
        )
        inputs = RegisteredGroundingFrameInputsV2.from_preview(preview, reference, audit.scope)
        if level == 6:
            require_equal(preview.to_payload(), source)
            require_equal(inputs.to_payload(), expected_inputs)
        else:
            stable = (
                "status",
                "region_basis",
                "grasp_tcp_world_m",
                "object_center_world_m",
                "rotation_object_to_world",
                "destination_world_m",
            )
            require_equal(
                {k: preview.to_payload()[k] for k in stable}, {k: source[k] for k in stable}
            )
        bench.require(inputs.matches_observation(reference), "matching profile failed inputs check")
        previews[phase] = preview
        outputs[phase] = inputs
    online = ground["online"]
    prepared = prepare_registered_step_binding_v2(
        audit.original,
        original_step_id=ground["step_id"],
        online=OnlineEvidenceSnapshot(
            reference,
            RobotState.model_validate(online["robot_state"]),
            online["visual_facts"],
            online["plan_version"],
            online["command_seq"],
            online["context_hash"],
        ),
        source_checkpoint=ExecutionCheckpoint.model_validate(ground["checkpoint"]),
        current_identity=audit.original.identity,
        owner_revision=1,
        state_generation=1,
        lease_source=_registered_lease_from_payload(ground["lease_source"]),
        grounding_inputs=outputs["grounding"],
        grounding_policy=RegisteredGroundingPolicyV2.for_original(
            audit.original,
            audit.original.source_hashes,
            region_policy=audit.protocol["region_policy"],
        ),
        now=datetime.fromisoformat(ground["binding_now"]),
    )
    binding = RegisteredCollectionStepBindingV2.from_prepared(
        prepared, collection_policy_id="registered-model-collection-v2"
    )
    require_equal(binding.grounded_step.model_dump(mode="json"), ground["grounded_step"])
    require_equal(
        binding.to_payload()["prepared"]["observation_checksum_sha256"],
        reference.checksum_sha256,
    )
    if level == 6:
        require_equal(binding.to_payload(), ground["binding"])
        require_equal(binding.to_payload(), pre["grounding"])
    else:
        bench.require(binding.digest() != ground["binding_sha256"], "candidate copied old binding")
    bench.require(
        binding.to_payload()["execution_authority"] is False, "archival authority changed"
    )
    return previews["pre"], {
        "grounding_inputs_sha256": outputs["grounding"].digest(),
        "pre_inputs_sha256": outputs["pre"].digest(),
        "binding_sha256": binding.digest(),
        "matches_archived_level_6_inputs_and_binding": level == 6,
        "same_step_reused_compiler_frame_rejected": same_step_rejection,
    }


def readback(work):
    bench.verified_file(bench.ROUND / "next-development.md", DECISION_SHA)
    measured = work / BENCH
    for name, sha in INPUTS.items():
        bench.verified_file(measured / name, sha)
    input_hashes = bench.read(measured / "independent-readback.json")
    run, _, preflight = bench.preflight(work)
    bench.require(ROOT == work / bench.SOURCE_SUFFIX / "source", "frozen imports required")
    blocked = bench.prohibit_external_activity()
    originals = run / "originals"
    recipe = bench.read(run.parent / "protocol.json")["recipe"]
    audit = _Audit(recipe, recipe["assignments"][0], run)
    audit.raw = audit.read("partial-originals.json")
    audit.identity = RawEpisodeIdentityV3.from_json(json.dumps(audit.raw["identity"]))
    audit.original = _owner_decode(VisualOriginalPlan, audit.read("original-plan.json"))
    audit.intervals = {item["interval_id"]: item for item in audit.raw["intervals"]}
    audit.states = {
        item["physics_step"]: item["post_state_payload"] for item in audit.raw["physics"]
    }
    audit.states[0] = audit.raw["reset"]["physics_state"]
    boot = audit.read("registered-tracker-bootstrap.json")
    ground = audit.read("grounding/step-1.json")
    (decision,) = audit.raw["decisions"]
    pre = decision["inputs"]
    bench.require(pre["phase"] == "PRE" and decision["decision"]["allowed"], "original PRE differs")
    bench.require(not (originals / "shield/step-1-post-result.json").exists(), "unexpected POST")

    roles = Counter()
    changed = 0
    explicit = {}
    pairs = {6: "pair-1-A", 1: "pair-1-B"}
    frame_chain = {level: [] for level in pairs}
    ids = audit.raw["allocated_frames"]
    bench.require(len(ids) == len(set(ids)) == 242, "expected 242 original acquisitions")
    for aid in ids:
        observation, metadata, state = audit.frame(aid)
        row = archived_sensor(originals / "frames" / aid, observation, metadata, state)
        roles[row.role] += 1
        compared = {}
        for level, name in pairs.items():
            tape = measured / name
            sha = input_hashes[name]["frame_metadata_sha256"][aid]
            metadata_path = bench.verified_file(tape / "frames" / aid / "source-frame.json", sha)
            compared[level] = matched_recorder_payload(
                tape, bench.read(metadata_path), row, row.sensor, level
            )
            frame_chain[level].append([aid, sha, compared[level].checksum_sha256])
        require_equal(compared[6].model_dump(mode="json"), observation.model_dump(mode="json"))
        a, b = compared[6].model_dump(mode="json"), compared[1].model_dump(mode="json")
        bench.payload_equivalence(a, b)
        changed += a["checksum_sha256"] != b["checksum_sha256"]
        if row.role == EXPLICIT:
            explicit[aid] = (row, compared)
    require_equal(
        dict(roles),
        {
            EXPLICIT: 2,
            "REGISTERED_PER_PHYSICS_STEP": 219,
            "IMPLICIT_SENSOR_CACHE_UPDATE": 21,
        },
    )
    bench.require(changed == 242, "unexpected candidate checksum change count")

    session_observation = {level: {} for level in pairs}
    feedbacks = {level: {} for level in pairs}
    negatives = []
    checked_feedback = []
    with TemporaryDirectory(prefix="teacher-cross-interface-") as scratch:
        for aid, (archive, paired) in explicit.items():
            feedback_path = originals / "frames" / aid / "feedback.json"
            old_feedback = bench.read(feedback_path)
            state = RobotState.model_validate(old_feedback["robot_state"])
            for recorder_level, name in pairs.items():
                pair_sha = input_hashes[name]["frame_metadata_sha256"][aid]
                for session_level in pairs:
                    obs, recorded, reference = explicit_return(
                        Path(scratch) / f"{aid}-{recorder_level}-{session_level}",
                        archive,
                        session_level,
                        recorder_level,
                        pair_sha,
                    )
                    require_equal(recorded, paired[recorder_level].model_dump(mode="json"))
                    require_equal(
                        obs.model_dump(mode="json"), paired[session_level].model_dump(mode="json")
                    )
                    feedback = {
                        **old_feedback,
                        "acquisition": reference,
                        "checksum_sha256": recorded["checksum_sha256"],
                    }
                    if recorder_level == 6:
                        bench.require(
                            canonical(feedback) + b"\n" == feedback_path.read_bytes(),
                            "original explicit feedback bytes changed",
                        )
                    if recorder_level != session_level:
                        rejection = must_reject(feedback_read, feedback, obs, reference, state)
                        negatives.append(
                            {
                                "consumer": "_v2_feedback",
                                "acquisition_id": aid,
                                "recorder_level": recorder_level,
                                "session_level": session_level,
                                **rejection,
                            }
                        )
                    else:
                        feedback_read(feedback, obs, reference, state)
                        session_observation[session_level][aid] = obs
                        feedbacks[session_level][aid] = feedback
                        checked_feedback.append(
                            {
                                "acquisition_id": aid,
                                "level": session_level,
                                "payload_sha256": digest(feedback),
                                "original_feedback_file_sha256": bench.sha_file(feedback_path),
                                "archived_bytes": session_level == 6,
                            }
                        )
    compiler = boot["compiler_reference_acquisition"]["acquisition_id"]
    dispatch = boot["acquisition"]["acquisition_id"]
    require_equal(pre["feedback_source"], feedbacks[6][dispatch])
    for level in pairs:
        value, expected = feedbacks[level][compiler], feedbacks[level][dispatch]
        negatives.append(
            {
                "consumer": "_v2_feedback",
                "case": "same_step_different_acquisition",
                "level": level,
                **must_reject(
                    feedback_read,
                    value,
                    session_observation[level][dispatch],
                    expected["acquisition"],
                    RobotState.model_validate(expected["robot_state"]),
                ),
            }
        )
    pre_inputs = {}
    previews = {}
    for level, by_id in session_observation.items():
        previews[level], pre_inputs[level] = tracker_and_binding(
            audit, ground, pre, boot, by_id, level
        )
    for recorder_level, session_level in ((6, 1), (1, 6), (6, 6), (1, 1)):
        aid = compiler if recorder_level == session_level else dispatch
        negatives.append(
            {
                "consumer": "RegisteredGroundingFrameInputsV2.from_preview",
                "case": "same_step_different_acquisition" if aid == compiler else "codec_mismatch",
                "recorder_level": recorder_level,
                "session_level": session_level,
                **must_reject(
                    RegisteredGroundingFrameInputsV2.from_preview,
                    previews[recorder_level],
                    session_observation[session_level][aid],
                    audit.scope,
                ),
            }
        )
    bench.require(not blocked, "offline check reached a simulator or network entry point")
    return dict(
        scope=ARCHIVE_SCOPE,
        result="OFFLINE_CROSS_INTERFACE_PASS",
        original_frames=len(ids),
        role_counts=roles,
        same_level=(
            {"recorder": 6, "observations": 6, "matched_frames": 242},
            {"recorder": 1, "observations": 1, "matched_frames": 242},
        ),
        changed_png_observation_checksums=changed,
        ordered_frame_identity_sha256={level: digest(rows) for level, rows in frame_chain.items()},
        real_explicit_return_paths=8,
        explicit_physics_step=120,
        explicit_feedback=checked_feedback,
        recorded_pre_binding=pre_inputs,
        consumer_rejections=negatives,
        live_recorder_feedback_invoked=False,
        post_available=False,
        physical_attempts=0,
        models=0,
        resource_violations=blocked,
        decision_sha256=DECISION_SHA,
        benchmark_inputs_sha256=INPUTS,
        paired_metadata_inventory_sha256={
            level: input_hashes[name]["frame_metadata_inventory_sha256"]
            for level, name in pairs.items()
        },
        verified_original_input_counts=preflight["verified_parent_input_counts"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    print(json.dumps(readback(parser.parse_args().checkout.resolve()), sort_keys=True, indent=2))
