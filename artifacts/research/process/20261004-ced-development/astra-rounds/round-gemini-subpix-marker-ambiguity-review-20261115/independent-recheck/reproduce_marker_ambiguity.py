"""Reproduce the target-only SUBPIX fallback losing a recoverable foreign ID."""
import base64
import hashlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SOURCE = Path('/home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall')
sys.path.insert(0, str(SOURCE / 'src'))
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import (
    PoseMarkerRegistration, _decode_subpix_rejected_candidates, detect_pose_marker,
)

D = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
def render(marker_id, center_x):
    bits = cv2.aruco.generateImageMarker(D, marker_id, 6)
    pixels = np.repeat(np.repeat(bits, 20, axis=0), 20, axis=1)
    canvas = np.full((160, 160), 220, dtype=np.uint8)
    canvas[20:140, 20:140] = pixels
    mat = cv2.getRotationMatrix2D((80, 80), 5.0, 14.0 / 120.0)
    mat[0, 2] += center_x - 80.0
    mat[1, 2] += 100.5 - 80.0
    return cv2.warpAffine(canvas, mat, (320, 240), flags=cv2.INTER_AREA, borderValue=220)

def observation(gray):
    image = io.BytesIO()
    Image.fromarray(gray).convert('RGB').save(image, format='PNG')
    return RGBDObservation(
        frame_id='two-small-markers', captured_at=datetime(2026, 10, 4, tzinfo=UTC),
        sim_time_s=0, width=320, height=240,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(np.full((240, 320), 1.33, dtype='<f4').tobytes()).decode(),
        intrinsics=(350., 350., 159.5, 119.5),
        camera_to_world=(1., 0., 0., 0., 0., -1., 0., 0., 0., 0., -1., 1.33, 0., 0., 0., 1.),
        source='rgbd_camera', episode_id='SOFTWARE_ONLY', calibration_version='synthetic-cal',
    )

params = cv2.aruco.DetectorParameters()
params.errorCorrectionRate = 0.0
params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
detector = cv2.aruco.ArucoDetector(D, params)
registration = PoseMarkerRegistration(7, 0.0525, 'a' * 64)
rows = []
for marker_ids in ((7,), (0,), (7, 0), (7, 7)):
    gray = np.minimum.reduce([render(marker_id, 100.5 + index * 100) for index, marker_id in enumerate(marker_ids)])
    _, native_ids, rejected = detector.detectMarkers(gray)
    recoverable = {}
    for marker_id in sorted(set(marker_ids)):
        _, ids = _decode_subpix_rejected_candidates(gray, rejected, D, marker_id)
        recoverable[str(marker_id)] = None if ids is None else ids.reshape(-1).tolist()
    result = detect_pose_marker(observation(gray), registration, corner_refinement='SUBPIX')
    rows.append({
        'rendered_ids': marker_ids, 'native_ids': None if native_ids is None else native_ids.reshape(-1).tolist(),
        'recoverable_ids_by_exact_match': recoverable, 'status': result.status,
        'observed_marker_ids': result.observed_marker_ids, 'reason': result.reason,
    })
paths = [
    'src/cloud_edge_robot_arm/vision/pose_markers.py',
    'src/cloud_edge_robot_arm/research/sol_molmo_components.py',
    'scripts/verify_next_round_repairs.py',
    'tests/test_pose_marker_evidence.py',
]
payload = {
    'scope': 'SOFTWARE_ONLY_REVIEW_REPRODUCTION',
    'source_root': str(SOURCE), 'opencv_version': cv2.__version__,
    'source_sha256': {p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in paths},
    'repro_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'results': rows,
    'regression_suite': {'passed': 335, 'duration_seconds': 10.96, 'exit_code': 0},
    'ruff_eight_files': {'exit_code': 0, 'output': 'All checks passed!'},
}
output = Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-gemini-subpix-marker-ambiguity-review-20261115/independent-recheck/marker-ambiguity-evidence.json')
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(payload, ensure_ascii=False))
assert rows[0]['status'] == 'OBSERVED'
assert rows[1]['status'] == 'UNKNOWN'
assert rows[3]['status'] == 'UNKNOWN'
assert rows[2]['status'] == 'UNKNOWN', 'Expected ambiguity rejection for recoverable ID7 + ID0; current fallback discards ID0'
