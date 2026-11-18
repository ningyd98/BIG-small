"""The native harness stop audit binds observations before measuring them."""

import hashlib
import json
import struct
from datetime import UTC, datetime

import pytest
from scripts import diagnose_native_harness_stops as audit

from cloud_edge_robot_arm.research.sol_molmo_offline_regression import FrozenCase
from cloud_edge_robot_arm.vision.servo import save_servo_frame
from tests.test_opencv_target_evidence import scene
from tests.test_visual_servo import revised


def paired_frame(name="frame", **changes):
    original = scene(
        name, started=datetime(2026, 1, 1, tzinfo=UTC), source="mujoco_camera", **changes,
    )
    digest = hashlib.sha256(
        struct.pack("<20d", *original.intrinsics, *original.camera_to_world),
    ).hexdigest()
    return revised(original, calibration_version=digest[:16])


def frozen_frame(root, observation, *, name="frame"):
    save_servo_frame(observation, root / name)
    files = {}
    for path in (root / name).iterdir():
        data = path.read_bytes()
        files[path.relative_to(root).as_posix()] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
    return FrozenCase(root, files, {})


def test_frozen_observation_uses_original_identity_and_checksum(tmp_path):
    original = paired_frame()
    case = frozen_frame(tmp_path, original)
    observed = audit.read_bound_frame(case, "frame", episode_id=original.episode_id)
    assert observed == original
    assert observed.captured_at.year == 2026


def test_changed_paired_file_cannot_be_read(tmp_path):
    case = frozen_frame(tmp_path, paired_frame())
    depth = tmp_path / "frame" / "depth.f32"
    data = depth.read_bytes()
    depth.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    with pytest.raises(ValueError, match="FROZEN_FILE_HASH_MISMATCH"):
        audit.read_bound_frame(case, "frame", episode_id="device-evidence")


def test_calibration_must_bind_the_actual_transform_even_if_checksum_is_valid(tmp_path):
    observation = revised(paired_frame(), calibration_version="a-false-calibration")
    case = frozen_frame(tmp_path, observation)
    with pytest.raises(ValueError, match="calibration"):
        audit.read_bound_frame(case, "frame", episode_id=observation.episode_id)


def test_cross_episode_archive_frame_rejected_before_geometry(tmp_path):
    case = frozen_frame(tmp_path, paired_frame(episode_id="other-episode"))
    with pytest.raises(ValueError, match="episode"):
        audit.read_bound_frame(case, "frame", episode_id="device-evidence")


@pytest.mark.parametrize("difference", ["repeated", "time", "scene"])
def test_alternate_frames_require_unique_identity_and_one_simulation_instant(difference):
    original = paired_frame("initial", scene_id="scene")
    alternate = paired_frame("alternate", scene_id="scene")
    if difference == "repeated":
        alternate = original
    elif difference == "time":
        alternate = revised(alternate, sim_time_s=0.1)
    else:
        alternate = revised(alternate, scene_id="other-scene")
    with pytest.raises(ValueError):
        audit.check_same_sample([original, alternate])


def test_original_binding_rejects_wrong_frame_record():
    original = paired_frame("initial")
    evidence = paired_frame("different").evidence()
    with pytest.raises(ValueError, match="observation_id"):
        audit.check_frame_binding(original, evidence)


@pytest.mark.parametrize("alias", [False, True])
def test_no_outputs_inside_the_source_tree(tmp_path, alias):
    archive = tmp_path / "archive"
    archive.mkdir()
    destination = archive
    if alias:
        destination = tmp_path / "alias"
        destination.symlink_to(archive, target_is_directory=True)
    with pytest.raises(ValueError, match="protected"):
        audit.write_report(destination / "new.json", {}, protected=(archive,))
    assert list(archive.iterdir()) == []


def test_existing_output_never_overwritten(tmp_path):
    destination = tmp_path / "report.json"
    destination.write_text('"existing"')
    with pytest.raises(FileExistsError):
        audit.write_report(destination, {"new": True}, protected=())
    assert json.loads(destination.read_text()) == "existing"


@pytest.mark.parametrize("damage", [None, "depth"])
def test_static_initial_measurement_uses_production_selected_support(damage):
    original = paired_frame(damage=damage)
    _, outcome = audit.measure_initial_geometry(original, {
        "original_pixel_target": [12, 26],
        "original_pixel_destination": [57, 32],
        "top_grasp_support_height_m": 0.0,
        "depth_error_bound_m": 0.001,
    })
    assert outcome["entities"]["target"]["depth"]["rejected_pixels"] == int(damage == "depth")
    assert outcome["entities"]["destination"]["depth"]["rejected_pixels"] == 0
    assert outcome["entities"]["destination"]["status"] == "ACCEPTED"
    if damage:
        assert outcome["reason"] == (
            "initial RGB-D identity/extent unavailable: target_depth_incomplete"
        )
        assert outcome["entities"]["target"]["depth"]["invalid_mask_pixels"] == 1
        assert outcome["entities"]["target"]["depth"]["nonpositive_pixels"] == 1
        assert outcome["entities"]["target"]["depth"]["nonfinite_pixels"] == 0
    else:
        assert outcome["status"] == "ACCEPTED"


MOLMO_PROMPTS = (
    b"<|image|><|im_start|>user\nPoint to the visible top center of red block. "
    b"If the requested item is not visible, return exactly ABSENT and no points."
    b"<|im_end|>\n<|im_start|>assistant\n",
    b"<|image|><|im_start|>user\nPoint to the interior of green region. "
    b"If the requested item is not visible, return exactly ABSENT and no points."
    b"<|im_end|>\n<|im_start|>assistant\n",
)
MOLMO_PHRASES = ("visible top center of red block", "interior of green region")
MOLMO_RESPONSES = (
    b'<points coords="1 1 515 817">red block</points>',
    b'<points coords="1 1 405 298">green region</points>',
)
MOLMO_COORDS = ([515, 817], [405, 298])


def model_point_case(root, observation, index, fault=None):
    prompt = MOLMO_PROMPTS[index - 1]
    phrase = MOLMO_PHRASES[index - 1]
    raw = MOLMO_RESPONSES[index - 1]
    if fault == "extra_image":
        prompt = b"<|image|>" + prompt
    elif fault == "extra_role":
        prompt += b"<|im_end|>\n<|im_start|>user\n"
    elif fault == "wrong_role":
        prompt = prompt.replace(b"user", b"system", 1)
    elif fault == "bare_text":
        prompt = prompt.split(b"\n")[1].removesuffix(b"<|im_end|>")
    elif fault == "missing_newline":
        prompt = prompt[:-1]
    elif fault == "wrong_query_prompt":
        prompt = MOLMO_PROMPTS[2 - index]
    query_sha = hashlib.sha256(phrase.encode()).hexdigest()
    raw_sha = hashlib.sha256(raw).hexdigest()
    common = {
        "observation_checksum": observation.checksum_sha256,
        "rgb_sha256": observation.evidence()["rgb_sha256"],
        "query_sha256": query_sha,
    }
    started = common | {"phrase": phrase}
    result = common | {"raw_sha256": raw_sha, "reached_cap": fault == "generation_capped"}
    binding = {
        "query_sha256": query_sha,
        "raw_sha256": raw_sha,
        "status": "POINT",
        "normalized_1000": MOLMO_COORDS[index - 1],
    }
    if fault == "wrong_phrase":
        started["phrase"] = MOLMO_PHRASES[2 - index]
    elif fault == "wrong_response":
        raw = MOLMO_RESPONSES[2 - index]
        result["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    elif fault == "wrong_rgb":
        started["rgb_sha256"] = "0" * 64
    elif fault == "wrong_observation":
        result["observation_checksum"] = "0" * 64
    elif fault == "wrong_coordinates":
        binding["normalized_1000"] = MOLMO_COORDS[2 - index]
    folder = root / f"raw/molmo/request-{index:04d}"
    folder.mkdir(parents=True)
    files = {}
    for name, data in {
        "prompt.txt": prompt, "raw-response.txt": raw,
        "started.json": json.dumps(started).encode(), "result.json": json.dumps(result).encode(),
    }.items():
        path = folder / name
        path.write_bytes(data)
        files[path.relative_to(root).as_posix()] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
    if fault == "unindexed_edit":
        (folder / "prompt.txt").write_bytes(prompt[:-1])
    return FrozenCase(root, files, {}), binding


@pytest.mark.parametrize(("index", "expected_pixel"), [(1, (41, 52)), (2, (32, 19))])
def test_model_point_accepts_exact_registered_chat_prompt(
    tmp_path, index, expected_pixel,
):
    observation = paired_frame()
    case, binding = model_point_case(tmp_path, observation, index)
    pixel, details = audit._model_point(case, index, observation, binding)
    assert pixel == expected_pixel
    assert details["status"] == "POINT"
    assert list(details["normalized_1000"]) == MOLMO_COORDS[index - 1]
    assert details["prompt_sha256"] == hashlib.sha256(MOLMO_PROMPTS[index - 1]).hexdigest()


@pytest.mark.parametrize("fault", [
    "bare_text", "extra_image", "extra_role", "wrong_role", "missing_newline",
    "wrong_query_prompt", "wrong_phrase", "wrong_response", "wrong_rgb",
    "wrong_observation", "wrong_coordinates", "generation_capped",
])
def test_model_point_rejects_semantic_mismatch_even_when_files_are_indexed(tmp_path, fault):
    observation = paired_frame()
    case, binding = model_point_case(tmp_path, observation, 1, fault)
    with pytest.raises(ValueError, match="not bound"):
        audit._model_point(case, 1, observation, binding)


def test_model_point_rejects_post_inventory_prompt_edit(tmp_path):
    observation = paired_frame()
    case, binding = model_point_case(tmp_path, observation, 1, "unindexed_edit")
    with pytest.raises(ValueError, match="FROZEN_FILE_HASH_MISMATCH"):
        audit._model_point(case, 1, observation, binding)
