# More mainland RGB-D sources: robot / indoor research

> 本报告为分工检索快照，最终实测结果见 [本轮汇总结论](../research-summary.md)。Micro 最小文件现已确认是 open-source-12.mcap（69,082,845 字节）；当前魔搭 LingBot 精选缺深度和索引，不能作为可用 RGB-D 推荐。VINS 体积为 481.6 MiB。

Research date: 2026-10-03. Read-only primary-source browsing; this subagent did not download remote files. Local ModelScope API snapshots and physical-interface results were produced by the root agent.

## Ranking for bounded inspection

| Priority | Mainland source | Physical / synthetic | Numeric depth and K | Robot actions | Download status |
|---|---|---|---|---|---|
| 1 | [Voxel51/lingbot-depth-subset](https://modelscope.cn/datasets/Voxel51/lingbot-depth-subset) | Mixed; choose RobbyReal or RobbyVla for measured captures | Source PNG uint16, millimeters, rawdepth/gtdepth plus intrinsic.txt | No action fields in released perception format | Root verified ModelScope API 200; small loose files under data/; file-level probe pending |
| 2 | [ShanghaiTech VINS-RGBD](https://robotics.shanghaitech.edu.cn/datasets/VINS-RGBD) | Real D435i indoor navigation captures | ROS Image TYPE_16UC1 / MONO16; mm converted to meters; published color/depth calibration | No manipulation command stream documented | Smallest Handheld Normal.bag shown as 481.6 MB; root physical enp7s0 probe obtained binary 206 through same-host redirect |
| 3 | [MicroAGI-Labs/MicroAGI01](https://www.modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01/) | Real human household manipulation | MCAP depth PNG, unit=1 mm, camera info intrinsics, tf_static extrinsics | Human wrist/hand pose only, no native robot commands | Root API lists open-source-05.mcap at 80,896,273 bytes; physical download probe pending |
| Deferred | [agibot_world/agibot_world_beta](https://modelscope.cn/datasets/agibot_world/agibot_world_beta) | Real robot manipulation | Head-depth PNG; camera parameters directory; dtype/unit need sample inspection | HDF5 action + state including arms, end poses, effector, base | Publisher advertises ~7 GB sample_dataset.tar, but root MS tree has only six entries and this sample is ABSENT |

## VINS-RGBD concrete domestic downloads

Official listing:

- Handheld: https://robotics.shanghaitech.edu.cn/seafile/d/0ea45d1878914077ade5/
- Wheeled: https://robotics.shanghaitech.edu.cn/seafile/d/78c0375114854774b521/
- Tracked: https://robotics.shanghaitech.edu.cn/seafile/d/f611fc44df0c4b3d936d/

Binary entry URLs observed by following official download links:

- Smallest overall, Handheld Normal.bag (481.6 MB UI): https://robotics.shanghaitech.edu.cn/seafile/d/0ea45d1878914077ade5/files/?dl=1&p=%2FNormal.bag
- Wheeled Normal.bag (1.0 GB UI): https://robotics.shanghaitech.edu.cn/seafile/d/78c0375114854774b521/files/?dl=1&p=%2FNormal.bag
- Smallest tracked, Ground and Up-down Slopes.bag (1.4 GB UI): https://robotics.shanghaitech.edu.cn/seafile/d/f611fc44df0c4b3d936d/files/?dl=1&p=%2FGround+and+Up-down+Slopes.bag

The current robotics.shanghaitech.edu.cn host works. Older star-center.shanghaitech.edu.cn links in the GitHub README return 404. Official pages expose binary downloads without a login prompt. There are nine compressed ROS1 bags; decompress with ROS tooling. Topics are /camera/aligned_depth_to_color/image_raw, /camera/color/image_raw and /camera/imu. Published color calibration is 640x480, fx=616.5911254882812, fy=616.6796264648438, cx=324.2193603515625, cy=239.42701721191406. For aligned depth use the aligned stream's calibration, not the separate raw-depth K without checking.

Primary format evidence:

- [Official repository](https://github.com/STAR-Center/VINS-RGBD): sensor and bag topics.
- [Depth decode implementation](https://github.com/STAR-Center/VINS-RGBD/blob/master/feature_tracker/src/feature_tracker_node.cpp): TYPE_16UC1/MONO16 and unsigned-short pixel access.
- [Metric conversion](https://github.com/STAR-Center/VINS-RGBD/blob/master/vins_estimator/src/estimator_node.cpp): depth / 1000.
- [Color calibration](https://github.com/STAR-Center/VINS-RGBD/blob/master/config/realsense/realsense_color_config.yaml), [raw depth calibration](https://github.com/STAR-Center/VINS-RGBD/blob/master/config/realsense/realsense_depth_config.yaml).

License: repository explicitly applies GPLv3 to **source code**. A dataset-specific license was not located. Do not infer a dataset GPL license from code.

## MicroAGI exact sample candidates

ModelScope API snapshot: ../microagi-mcap-tree.json.

- uncut_mcaps/open-source-05.mcap: 80,896,273 bytes, SHA256 d15b301892c2d319c71a65fd96f22d182898df33c4c301e1b65da6ddbc91e474.
- uncut_mcaps/open-source-06.mcap: 208,845,378 bytes, SHA256 e06b5a983dc75683669abe69ec80275dc82d2f6b770bcc4da7d31f836fca8cf7.
- Candidate resolve URL, verify with root direct probe: https://modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01/resolve/master/uncut_mcaps/open-source-05.mcap

The publisher card documents /camera/depth/image (PNG), /camera/depth/info (K), /camera/depth/unit_of_depth_in_mm=1, /tf_static, /tf/camera, wrist transforms and hand keypoints. Camera pose requires a same-timestamp valid health message and is coherent only within valid blocks. This is human demonstration data, suitable for egocentric perception/pose learning. Card license is custom maginoresell, not Apache; exact LICENSE still needs inspection. The currently inspected MS tree is uncut_mcaps; historical card counts and HF content differ, so use API files as authority. [Publisher mainland card](https://www.modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01/).

## LingBot details and license conflict

[Publisher source card](https://huggingface.co/datasets/robbyant/mdm_depth) describes 16-bit PNG millimeters, color/, rawdepth/, gtdepth/, intrinsic.txt. RobbyReal has 1.4M real indoor samples; RobbyVla has 580,960 real Franka/UR7e samples. RobbySim and RobbySimVal are synthetic. Original domestic archives are multipart and mostly larger than 10 GB; a tail part below 10 GB is not a standalone dataset. Root has identified the smaller domestic Voxel51 mirror.

The [subset exporter](https://huggingface.co/datasets/Voxel51/lingbot-depth-subset) reports 13,149 samples from archive-prefix extraction; this is not a random sample of the original corpus. It retains numeric depth and K, but no released robot action schema. Both original and subset have an Apache metadata tag while the upstream body says CC BY-NC-SA 4.0. Record the conflict and avoid silently claiming commercial permission.

## AgiBot: useful but not yet bounded-download verified

[Publisher Beta card](https://huggingface.co/datasets/agibot-world/AgiBotWorld-Beta) proves PNG depth, K/extrinsic camera files and native HDF5 commands distinct from measured state. License CC BY-NC-SA 4.0. HF requires account/contact agreement; domestic auth must be checked independently. The card's ~7 GB sample cannot be used as proof that a domestic sample exists. Parent API root snapshot ../agibot-tree.json has observations, parameters, proprio_stats, task_info and two metadata files, no sample_dataset.tar.

[Maintainer issue response](https://github.com/OpenDriveLab/AgiBot-World/issues/6#issuecomment-2567310201) confirms that the older Alpha release lacks wrist depth. Later response says camera extrinsics were aligned per image frame. Prefer verified head depth and inspect current actual files before generalizing this to Beta wrist cameras.

## Excluded or unproven candidates

- [DAS-Sample-Data](https://modelscope.cn/datasets/GenRobot.AI/DAS-Sample-Data): float32 label/depthmap is explicitly estimated from RGB. It is numeric but not measured RGB-D.
- [RoboMIND2.0](https://www.modelscope.cn/datasets/X-Humanoid/RoboMIND2.0): unified schema lists depth_images and camera_intrinsics, but explicitly says each variant contains only a subset. Generic schema and RGB-D camera names do not prove depth in any particular archive. Need an actual HDF5 sample before selection.
- [AgiBotWorldChallenge-2026](https://huggingface.co/datasets/agibot-world/AgiBotWorldChallenge-2026): Reasoning2Action-Sim has head/hand depth video features and a dataset_without_depth variant. This displayed release is simulation; do not promote it as measured robot RGB-D without inspecting another split.
- ScanNet / NYUv2 / SUNRGBD / ARKitScenes: no primary mainland copy with downloadable numeric depth was established in this search. Mainland VSI-Bench/OVO-S-Bench cards provide source RGB videos and annotations, not the original depth streams.
- [THU-READ](https://ivg.au.tsinghua.edu.cn/dataset/THU_READ.php): official Baidu shares exist, but the page establishes neither metric numeric depth nor K; insufficient for geometric RGB-D ingestion.
