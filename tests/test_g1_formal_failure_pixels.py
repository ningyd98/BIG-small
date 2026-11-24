"""Native sampling and an independent post-seal join against the archived online audit."""

import gzip
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from scripts.graduation.g1_formal_failure_pixels import (
    PACKETS,
    PLAN_SHA,
    RAW,
    ROOT,
    ROUND,
    ROWS,
    SEAL,
    depth_features,
    projective_sample,
    quad_features,
)

ONLINE = "pixels-online-poses.public.json"
POSE_FIELDS = (
    "ordered_corners_px",
    "marker_center_world_m",
    "rotation_marker_to_world",
    "measured_edge_lengths_m",
)
FEEDBACK_FIELDS = (
    "observed_ids",
    "usable_ids",
    "selected_id",
    "target_disagreement_m",
    "grasp_world_m",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value):
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def verified_json(path, expected):
    data = path.read_bytes()
    assert digest(data) == expected, path
    return json.loads(data)


def test_native_pixel_contrast_and_edges():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    gray = np.full((48, 48), 255, np.uint8)
    gray[12:36, 12:36] = cv2.aruco.generateImageMarker(dictionary, 7, 24)
    corners = np.array([[11.5, 11.5], [35.5, 11.5], [35.5, 35.5], [11.5, 35.5]])
    features = projective_sample(gray, corners, dictionary, 7)
    assert features["quiet"]["n"] == 32**2 - 24**2
    assert features["black_cells"]["max"] == 0
    assert features["white_cells"]["min"] == 255
    assert features["quiet_minus_border_median"] == 255
    assert [row["delta"] for row in features["edges"]] == [255] * 4
    assert features["board_from_detected_print_homography_px"] == [
        [7.5, 7.5],
        [39.5, 7.5],
        [39.5, 39.5],
        [7.5, 39.5],
    ]
    geom = quad_features(corners, 48, 48)
    assert geom["side_lengths_px"] == [24] * 4
    assert geom["edge_directions_deg"] == [0, 90, 180, -90]
    assert list(geom["image_margins_px"].values()) == [11.5] * 4


def test_metric_patch_requires_all_nine_native_pixels():
    depth = np.full((20, 20), 1.25, np.float32)
    depth[4, 5] = 0
    result = depth_features(depth, [[5, 5], [14, 5], [14, 14], [5, 14]])
    first, *remaining = result["five_patches"]
    assert first["n_positive"] == 8 and first["n_pixels"] == 9 and first["median_m"] is None
    assert all(patch["n_positive"] == 9 and patch["median_m"] == 1.25 for patch in remaining)
    assert result["four_corner_median_range_m"] is None


def online_pose_comparison():
    """Recompute every stored preview visit and accepted dual feedback in audit list order."""
    plan = verified_json(ROUND / "plan.json", PLAN_SHA)
    seal_bytes = (ROUND / SEAL).read_bytes()
    seal = json.loads(seal_bytes)
    table = (ROUND / ROWS).read_bytes()
    assert seal["worker_payload_sha256"] == [digest(table)] * 2
    frames = json.loads(gzip.decompress(table))["frames"]
    bundles = verified_json(PACKETS / "index.json", seal["anonymous_index_sha256"])
    slots, visits, distinct_pose, all_feedback, differences = {}, [], set(), set(), []
    global_max = dict.fromkeys(POSE_FIELDS, 0.0)
    for arch in sorted((RAW / "trials").glob("*/instance/online-audit.json")):
        slot = arch.parents[1].name
        archive_sha = plan["inputs_sha256"][str(arch.relative_to(ROOT))]
        audit = verified_json(arch, archive_sha)
        sample_ids, pose_ids = [], []
        for ordinal, record in enumerate(audit):
            for field in ("registered_preview", "preview"):
                if field not in record:
                    continue
                track = record[field]["track"]
                archived = track["geometry"]["marker_estimate"]
                frame_id = archived["observation_id"]
                fresh = frames[frame_id]
                assert track["observation_id"] == track["geometry"]["observation_id"] == frame_id
                assert fresh["episode"] == track["episode_id"] == track["geometry"]["episode_id"]
                checksum = fresh["checksum_sha256"]
                assert (
                    checksum
                    == archived["observation_checksum_sha256"]
                    == track["observation_checksum_sha256"]
                )
                assert checksum == track["geometry"]["observation_checksum_sha256"]
                marker = str(fresh["selected_id"])
                geom = bundles[fresh["packet_set"]]["geometry"]
                registration = (
                    geom["development_dual"]["markers"][marker]["marker_registration_hash"]
                    if fresh["mode"] == "dual"
                    else canonical_digest(geom["pose_marker"])
                )
                assert (
                    archived["registration_hash"]
                    == track["marker_registration_hash"]
                    == registration
                )
                side = fresh["by_id"][marker]
                errors = {}
                for name in POSE_FIELDS:
                    a, b = (np.asarray(obj[name]) for obj in (side, archived))
                    assert a.shape == b.shape and a.size > 0
                    errors[name] = float(np.max(np.abs(a - b)))
                    global_max[name] = max(global_max[name], errors[name])
                    if errors[name] != 0:
                        differences.append(
                            {
                                "slot": slot,
                                "audit_ordinal": ordinal,
                                "frame_id": frame_id,
                                "field": name,
                                "fresh": side[name],
                                "archived": archived[name],
                            }
                        )
                distinct_pose.add(frame_id)
                pose_ids.append(frame_id)
                visits.append(
                    {
                        "slot": slot,
                        "frame_id": frame_id,
                        "checksum_sha256": checksum,
                        "audit_ordinal": ordinal,
                        "field": field,
                        "marker_id": fresh["selected_id"],
                        "physics_step": fresh["physics_step"],
                        "maximum_absolute_component_difference": errors,
                    }
                )
            for sample in record.get("visual_samples", []):
                archive = sample.get("development_dual_marker")
                if archive is None:
                    continue
                frame_id = archive["frame_id"]
                fresh = frames[frame_id]
                assert record["phase"] == "servo" and fresh["mode"] == "dual" and fresh["usable"]
                assert frame_id == sample["observation_id"] and frame_id not in all_feedback
                assert archive["checksum"] == sample["checksum_sha256"] == fresh["checksum_sha256"]
                all_feedback.add(frame_id)
                sample_ids.append(frame_id)
                for name in FEEDBACK_FIELDS:
                    value = (
                        fresh["by_id"][str(fresh["selected_id"])][name]
                        if name == "grasp_world_m"
                        else fresh[name]
                    )
                    if value != archive[name]:
                        differences.append(
                            {
                                "slot": slot,
                                "audit_ordinal": ordinal,
                                "frame_id": frame_id,
                                "field": name,
                                "fresh": value,
                                "archived": archive[name],
                            }
                        )
        slots[slot] = {
            "audit_sha256": archive_sha,
            "preview_visits": len(pose_ids),
            "distinct_pose_frames": len(set(pose_ids)),
            "accepted_dual_feedback": len(sample_ids),
            "ordered_accepted_feedback_frame_ids_sha256": canonical_digest(sample_ids),
        }
    return {
        "schema": "g1.failure-observation.pixels.post-seal-online-pose.v1",
        "plan_sha256": PLAN_SHA,
        "pre_join_seal_sha256": digest(seal_bytes),
        "fresh_table_sha256": digest(table),
        "validator_file": str(Path(__file__).resolve().relative_to(ROOT)),
        "validator_source_sha256": digest(Path(__file__).read_bytes()),
        "preview_visits": len(visits),
        "distinct_preview_frames": len(distinct_pose),
        "accepted_dual_feedback_frames": len(all_feedback),
        "slots": slots,
        "maximum_absolute_preview_component_difference": global_max,
        "preview_records": visits,
        "feedback_field_counts": dict.fromkeys(FEEDBACK_FIELDS, len(all_feedback)),
        "differences": differences,
        "scope": "Full pose checks use the selected marker in each archived preview. "
        "Accepted dual servo samples store five comparable fields. "
        "Preview revisits retain their audit ordinals.",
    }


@pytest.mark.skipif(
    not PACKETS.is_dir(), reason="local frozen G1 RGB-D research originals required"
)
def test_postseal_online_pose_readback():
    doc = online_pose_comparison()
    assert doc == json.loads((ROUND / ONLINE).read_bytes())
    assert doc["preview_visits"] == 22 and doc["distinct_preview_frames"] == 10
    assert doc["accepted_dual_feedback_frames"] == 366
    assert not doc["differences"] and not any(
        doc["maximum_absolute_preview_component_difference"].values()
    )
