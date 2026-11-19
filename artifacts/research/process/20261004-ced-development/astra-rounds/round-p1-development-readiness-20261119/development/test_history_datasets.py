import json

import pytest
from development_plan import assert_no_conflicts, dataset_identities

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest


def scene():
    return SceneSpec.from_parameters(
        {
            "target": {"position": [0.4, 0.0, 0.035]},
            "camera": {"position": [0.1, 0.2, 1.35]},
            "destination": {"position": [0.2, 0.25, 0.003]},
        },
        "a" * 64,
        981351,
    )


def sample():
    s = scene()
    return {
        "schema_version": "rgbd.dataset.v1",
        "source": "mujoco_camera",
        "status": "NEGATIVE",
        "sample_id": "first-sample",
        "group_id": s.group_id,
        "content_hash": "4" * 64,
        "scene": s.model_dump(mode="json"),
    }


def test_rgbd_dataset_compares_negative_sample_and_only_target():
    seeds, locations, _ = dataset_identities(
        json.dumps(sample()).encode(), "rgbd-smoke-20261003", "samples.jsonl", 1
    )
    assert (seeds, locations) == ({981351}, {(0.4, 0.0, 0.035)})
    proposed = [{"pose_seed": 981352, "scene": {"object_position_m": [0.4, 0.0, 0.035]}}]
    with pytest.raises(ValueError, match="rgbd.*position"):
        assert_no_conflicts(proposed, {"rgbd": (seeds, locations)})


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (("schema_version", "unrecognized"), "ordinary RGB-D"),
        (("seed", 10), "assignment seed disagrees"),
        (("group_id", "incorrect"), "group identity differs"),
    ],
)
def test_invalid_sample_version_or_conflicting_binding(mutation, error):
    original = sample()
    key, value = mutation
    original[key] = value
    with pytest.raises(ValueError, match=error):
        dataset_identities(json.dumps(original).encode(), "rgbd-smoke-20261003", "samples.jsonl", 1)


def test_ordinary_bad_numeric_seed_and_position_are_rejected():
    row = sample()
    row["scene"]["seed"] = True
    with pytest.raises(ValueError, match="invalid dataset scene seed"):
        dataset_identities(json.dumps(row).encode(), "rgbd-smoke-20261003", "samples.jsonl", 1)
    row = sample()
    row["scene"]["scene_parameters"]["target"]["position"][0] = float("nan")
    with pytest.raises(ValueError, match="nonfinite JSON"):
        dataset_identities(json.dumps(row).encode(), "rgbd-smoke-20261003", "samples.jsonl", 1)


def legacy_teacher():
    s = scene()
    member = {
        "scene": s.model_dump(mode="json"),
        "seed": s.seed,
        "group_id": s.group_id,
        "scene_source": "FIXED_S01_CONTROL",
        "scene_hash": s.scene_hash,
    }
    config = {"dataset_id": "fixture", "seed": s.seed}
    return {
        "schema_version": "rgbd.trajectory.manifest.v1",
        "config": config,
        "asset_sha256": s.asset_family_hash,
        "config_hash": content_digest({"config": config, "asset": s.asset_family_hash}),
        "requested_episodes": 2,
        "assignments": [member | {"index": 0}, member | {"index": 1}],
    }


def test_two_distinct_teacher_assignments_can_share_one_seed_and_pose():
    data = legacy_teacher()
    converted = dataset_identities(
        json.dumps(data).encode(), "rgbd-teacher-smoke", "manifest.json", 2
    )
    assert converted == ({981351}, {(0.4, 0.0, 0.035)}, 1)
    data["assignments"][1]["scene_source"] = "UNREGISTERED"
    with pytest.raises(ValueError, match="teacher scene source is unknown"):
        dataset_identities(json.dumps(data).encode(), "rgbd-teacher-smoke", "manifest.json", 2)
