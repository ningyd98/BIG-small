# RoboMIND official-source check

Requested source: ModelScope `X-Humanoid/RoboMIND`, specifically real `benchmark1_0_compressed/h5_franka_1rgb`. Anonymous metadata and a two-byte HTTP Range probe for each first part succeeded. Source files are pinned to full commit `be28d59219430dc8796f221f7fc4c23e113d6a4e`; all 68 declared SHA256 values are retained in `blocked-source-plan.json`.

The directory has exactly two task archives: `bread_in_basket` (37 parts, 391,352,931,369 bytes) and `bread_on_table` (31 parts, 329,457,550,918 bytes). Combined download is 720,810,482,287 bytes (671.31 GiB). The first part of either archive alone is 10 GiB. Parts are concatenated gzip segments, not independent tar archives; a smaller final segment cannot produce a complete task archive by itself. No official single-trajectory object is listed. Versions 1.1 and 1.2 have no `h5_franka_1rgb` directory. Therefore the authorized first-round 10 GiB budget cannot deploy complete target source units for two tasks. Status: `BLOCKED_BUDGET`; zero target trajectories downloaded.

Hugging Face official mirror is pinned to `e7ffe31d1fe983a42c3d7b79d192f554fc05b86e`, `gated=auto`; public card requires contact-sharing agreement and unauthenticated content access returned 401. No terms were accepted.

Official schema and quick-start documents are saved locally with SHA256 verification against ModelScope file metadata. Franka 1RGB uses `observations/{rgb_images,depth_images}/camera_top`, `puppet/joint_position` (T,8), `master/joint_position` (T,8), and `puppet/end_effector` (T,6, xyz+rpy). Franka image order after official OpenCV decode is BGR and needs one BGR→RGB conversion. Depth must preserve original numeric values; official format says millimeters, xyz meters, angles radians. Reader configuration should explicitly declare millimeters instead of deciding scale from image maxima. Official published intrinsics are in `RoboMIND_intrinsics.md`; per-trajectory calibration and camera-to-world extrinsics have not been verified and must not be fabricated.

Official links:
- https://modelscope.cn/datasets/X-Humanoid/RoboMIND
- https://huggingface.co/datasets/x-humanoid-robomind/RoboMIND
- https://github.com/x-humanoid-robomind/x-humanoid-robomind.github.io/blob/main/static/all_robot_h5_info.md
- https://github.com/x-humanoid-robomind/x-humanoid-robomind.github.io/blob/main/static/quick_start.ipynb
- https://github.com/x-humanoid-robomind/x-humanoid-robomind.github.io/blob/main/static/RoboMIND_intrinsics.md
- https://github.com/Open-X-Humanoid/RoboMIND-dataset-utils
