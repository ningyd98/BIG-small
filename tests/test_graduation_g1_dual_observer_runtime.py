"""Exercise the isolated V2 owner, prism inventory and controller input with software pixels."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def exercise_software_frames():
    import cv2
    import numpy as np
    from PIL import Image
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation.g1_dual_runtime_adapter import SOURCE_SHA256

    from cloud_edge_robot_arm.contracts import Pose, RobotState
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding
    from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY, marker_family
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.owner_registration import RegisteredGroundingFrameInputsV2
    from cloud_edge_robot_arm.vision.registered_object_tracking import PREVIEW_SOURCE_PATHS
    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

    root = Path.cwd()
    assert root == grounding.ROOT == Path(asset.__file__).resolve().parents[2]
    geometry = grounding.geometry_registration(marker_family_id=asset.FAMILY)
    reg = NativeGeometryRegistration(geometry)
    sources = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in {
            *SOURCE_SHA256,
            *PREVIEW_SOURCE_PATHS,
            *asset.SOURCE_FILES,
            asset.ASSET_PATH,
            asset.BASE_ASSET_PATH,
            marker_family(LEGACY_FAMILY).asset_path,
        }
    }

    def frame(index, ids):
        image = np.full((240, 320, 3), 255, np.uint8)
        image[113:127, 153:167] = [210, 30, 30]
        image[60:86, 110:136] = [30, 210, 30]
        depth = np.full((240, 320), 1.4, dtype="<f4")
        depth[113:127, 153:167] = 1.33
        depth[60:86, 110:136] = 1.396
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for code in ids:
            x, y = (160, 101) if code == 7 else (179, 120)
            image[y - 9 : y + 9, x - 9 : x + 9] = cv2.aruco.generateImageMarker(
                dictionary, code, 18
            )[:, :, None]
            depth[y - 11 : y + 11, x - 11 : x + 11] = 1.32995
        output = io.BytesIO()
        Image.fromarray(image).save(output, format="PNG")
        return RGBDObservation(
            **geometry["camera"],
            frame_id=f"software-frame-{index}",
            captured_at=datetime.now(UTC),
            episode_id="SOFTWARE_ONLY",
            scene_id=asset.SCENE_ID,
            sim_time_s=0.5 + index / 30,
            rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        )

    boot = frame(0, [7, 8])
    color, evidence = grounding.bootstrap_collection_tracker(boot, geometry)
    tracker = grounding.bootstrap_registered_collection_tracker_v2(
        boot,
        reg,
        source_root=root,
        source_hashes=sources,
        nominal_policy=grounding.registered_nominal_region_policy_v1(sources),
    )
    assert len(tracker._primitives.to_payload()["boxes"]) == 79
    state = RobotState(connected=True)
    for i, ids in enumerate(([7, 8], [7], [8]), start=1):
        obs = frame(i, ids)
        preview = grounding.registered_collection_grounding_preview_v2(tracker, obs, state)
        assert preview.status == "DERIVED", preview.reason
        marker = preview.track.geometry.marker_estimate
        assert list(marker.observed_marker_ids) == ids
        current = RegisteredGroundingFrameInputsV2.from_preview(preview, obs, reg).to_payload()
        assert current["marker_registration_hash"] == asset.pose_registration(ids[0]).digest()
        assert np.linalg.norm(np.asarray(current["grasp_tcp_world_m"]) - [0.35, 0, 0.045]) < 0.004
    servo = OpenCVServoFeedback(
        frame(4, [7, 8]),
        color,
        evidence,
        skill="MOVE_ABOVE",
        initial_target=Pose(x=0.35, y=0, z=0.16),
        marker_family_id=asset.FAMILY,
        verify_mujoco_calibration=True,
    )
    updated = servo.update(frame(5, [8]))
    row = servo.records[-1]
    assert abs(updated.x - 0.35) < 0.004
    assert row["development_dual_marker"]["selected_id"] == 8
    assert row["checksum_sha256"] == row["development_dual_marker"]["checksum"]
    print(
        "Software-only fresh tracker/nominal-region/owner V2: both, ID7, ID8; servo selected ID8."
    )


def test_exported_software_chain_selects_the_real_id_and_seals_owner_evidence(tmp_path):
    from scripts.graduation.g1_dual_build import build

    root = Path(__file__).resolve().parents[1]
    exported = tmp_path / "runtime"
    build(root, exported)
    # No renderer, physics backend, operation, or clock substitute is created.
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve())],
        check=True,
        cwd=exported,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(map(str, (exported, exported / "src")))},
    )


if __name__ == "__main__":
    exercise_software_frames()
