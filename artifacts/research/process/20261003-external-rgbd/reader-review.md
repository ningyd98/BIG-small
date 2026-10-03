# External RGB-D reader review

Review date: 2026-10-03. Scope: software only; no real-data deployment completion claim. The real download was still ongoing during this review. No implementation files were edited.

Reviewed `models.py`, `robomind.py`, `graspclutter.py`, their three reader test modules, the deployment design spec, and the saved official RoboMIND schema/Quick Start plus GraspClutter6D API/BOP source evidence.

## Findings requiring changes

### R1 — HDF5 external storage and virtual datasets bypass the source boundary (high)

Location: `src/cloud_edge_robot_arm/datasets/external/robomind.py:48` (`_dataset`, especially the HardLink check at lines 50–57).

The link guard rejects soft/external HDF5 links but accepts any hard-linked `h5py.Dataset`. HDF5 virtual datasets and datasets backed by external raw files also have HardLink entries. They can therefore read data outside `source_root`, and their backing-file contents are not covered by the indexed `trajectory.hdf5` SHA256.

Confirmed using temporary synthetic fixtures:

- Replaced `master/joint_position` with an external-storage dataset backed by an absolute file outside the raw root. Discovery and reading both succeeded. Changing the external file changed the returned state from `99.0` to `77.0` while the indexed HDF5 digest stayed unchanged.
- Replaced `observations/depth_images/camera_top` with a virtual dataset backed by an outside-root HDF5 file. Discovery and reading both succeeded. Changing that file changed depth from `1234` to `4321` without triggering the indexed-source checksum guard.

Required correction: reject datasets with nonempty `Dataset.external` and `Dataset.is_virtual` before reading them, consistently for RGB, depth, state, and an optional timestamp dataset. Add focused regression coverage for both cases. This uses the same already-authorized source-boundary rule as the existing link guard.

### R2 — Different depth resolution still receives RGB intrinsics and metric geometry (medium)

Location: `src/cloud_edge_robot_arm/datasets/external/graspclutter.py:377` and `:399` (`same_shape`/alignment calculation and unconditional `K_depth=intrinsics`).

When RGB and depth dimensions differ, the reader sets `rgb_depth_aligned=False` but still assigns the same per-image `scene_camera.cam_K` to `K_depth`. Without independently verified depth-resolution calibration, that assignment permits a point cloud using an unsupported focal length and principal point. The saved official API constructs depth points on the same pixel grid as RGB; it does not establish calibration for a differently sized depth image.

Confirmed with the existing synthetic GraspClutter fixture, replacing only depth with a valid `2×2 uint16` PNG while RGB stayed `3×4`: `rgb_depth_aligned=False`, `capabilities['camera_geometry']=True`, and `backproject_depth()` succeeded with four points.

Required correction: preserve readable RGB-D, but leave `K_depth` unavailable and downgrade camera geometry for this mismatch unless separate calibration explicitly establishes the corresponding depth camera/resolution. Extend the existing different-size test to check that depth backprojection is blocked, not only colored backprojection.

## Checks with no additional findings in this scope

- Compressed image decoding uses Pillow RGB output; raw BGR arrays swap channels once. Saved RoboMIND OpenCV evidence is consistent with this distinction.
- Encoded depth retains 16-bit values; RoboMIND scale needs explicit unit evidence, and GraspClutter applies BOP `depth_scale * 0.001` once.
- Missing calibration/time/action data remains nullable. No fabricated robot-base transform, current-time timestamp, or action label was found in these readers.
- GraspClutter world/model transforms retain explicit directions and convert BOP millimeters to meters. Duplicate object instances retain distinct instance IDs.
- Ground truth remains outside `model_input()`. NPZ annotation inspection reads numeric headers with pickle disabled and does not deserialize object arrays.
- Indexed GraspClutter RGB, depth, camera metadata, and pose metadata have digest checks; the issues above concern the uncovered external-HDF5 payload and unsupported depth-camera correspondence.

## Verification record

The scoped existing CPU tests were invoked once:

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_models.py tests/test_external_rgbd_robomind.py tests/test_external_rgbd_graspclutter.py
```

The combined tool response truncated that command's output, so this review does not state a test count or infer PASS from it. The three targeted reproductions above ran independently with `PYTHONPATH=src .venv-data/bin/python`; the successful reproduction call exited `0` and printed the stated values. All reproduction data lived in automatically removed temporary directories and was marked as synthetic fixture data.

Result: **CHANGES REQUIRED** for R1 and R2. Real source-backed integration acceptance remains a separate downstream step.
