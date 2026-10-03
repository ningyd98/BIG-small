# Official domestic RGB-D download candidates

Research date: 2026-10-03. This is source research, not a successful local download record. Only the root agent runs probes bound to the physical interface and maintains the global download ledger. A dataset page on a Chinese domain does not establish that its downloadable bytes are domestic or reachable without TUN.

## GraspNet-1Billion — strongest tabletop/grasp candidate, access unverified

The [official project](https://graspnet.net/) describes 190 real cluttered scenes recorded with Kinect Azure and RealSense D435, with 97,280 RGB-D images, 88 objects, object 6D poses and dense grasp labels. The [official download/format page](https://graspnet.net/datasets.html) links both SJTU JBOX and Baidu, documents RGB PNGs, depth PNGs, `camK.npy`, object masks, XML/MAT object pose annotations and camera poses. It lists train image archives of 20, 20, 20 and 6.3 GB; the smallest advertised image unit is `train_4.zip`, not an individual scene. The page labels its license BY-NC-SA and permits non-commercial use and redistribution under those conditions. Its written license title is imprecise, so preserve the site's terms rather than silently replacing them with a different license.

| Official listed file | Domestic download entry | Advertised size | Access status |
|---|---|---:|---|
| `train_4.zip` | [SJTU JBOX](https://jbox.sjtu.edu.cn/l/SHwJVL) | 6.3 GB | Share entry, not a verified bare ZIP URL |
| `train_4.zip` | [Baidu](https://pan.baidu.com/s/1A3Tyc7l_u9UwgKqhVJSrNg) | 6.3 GB | Share entry; anonymous file delivery not verified |
| `train_1.zip` | [SJTU JBOX](https://jbox.sjtu.edu.cn/l/71Kb9K) | 20 GB | Share entry, not a verified bare ZIP URL |

Numeric-depth proof is strengthened by the [official API source](https://github.com/graspnet/graspnetAPI/blob/master/graspnetAPI/utils/utils.py): it loads depth pixels and `camK.npy`, computes point-cloud Z as depth divided by camera scale, and uses camera intrinsics for X/Y. Its depth-coordinate helper explicitly uses millimeters. This is numerical depth, not merely a colored depth visualization.

The web research service timed out on the JBOX entries. Root separately reports that the physically bound connection completes TLS but disconnects before an HTTP response. Do not classify either event as a successful dataset download. No official single-scene domestic URL was found in this research.

## TransCG — real transparent-object RGB-D, Baidu bundles

The [official page](https://graspnet.net/transcg) provides real RGB-D, raw depth, refined ground-truth depth, transparent object masks/poses/models and D435/L515 camera-intrinsic NPY files. It lists 130 scenes and ten-scene image shards of 13.0–15.9 GB; the metadata/model/intrinsics archive is 149.3 MB. Its site uses the same BY-NC-SA/non-commercial wording as GraspNet. Transparent objects make this useful for difficult depth and tabletop pose cases; its full package is much larger than a small smoke-test sample.

| Official listed file | Domestic download entry | Advertised size | Code |
|---|---|---:|---|
| `transcg-info.zip` | [Baidu](https://pan.baidu.com/s/1IddfXYOGOhuqw4CjXS0wfg) | 149.3 MB | `ncj0` |
| `transcg-data-1.zip`, scenes 1–10 | [Baidu](https://pan.baidu.com/s/1911NmQwLDN8zGvd_km7obg) | 13.9 GB | `3n0d` |
| `transcg-data-2.zip`, scenes 11–20 | [Baidu](https://pan.baidu.com/s/14PGEaJCjHJewt_Uy7UiSdQ) | 13.0 GB | `umim` |

The [author's dataset loader](https://raw.githubusercontent.com/Galaxies99/TransCG/main/datasets/transcg.py) reads raw and ground-truth depth PNG pixels as NumPy float arrays and loads the two camera-intrinsic NPY files. Thus the documentation points to numerical depth with K, not just RGB/depth preview pictures. The info archive alone contains no listed RGB/depth scenes. Baidu shares are domestic entries, but neither a current login/client requirement nor anonymous command-line file delivery was independently verified; no bare domestic file URL was found.

## Omni6D-Real — small real subset promising, exact domestic file still unverified

The [author repository](https://github.com/3DTopia/Omni6D) links the [official OpenXLab dataset](https://openxlab.org.cn/datasets/kszpxxzmcwww/Omni6D), announces the real subset separately from the synthetic Omni6D/Omni6D-xl variants, and documents real RGB/depth/mask PNGs plus label pickle files. It prescribes OpenXLab login and CLI listing/download, supports source-path selection, and publishes shared credentials for login errors. Do not download the 388.9 GB whole collection: that size is not Real-only. The repository's license section links CC BY 4.0 but names OmniObject3D, so the exact application to the Real release should remain a visible ambiguity until its package/provider terms are inspected.

The [author paper, Appendix I](https://arxiv.org/html/2409.18261v1) verifies real Azure Kinect DK capture, reporting 30 scenes, 39 categories, 73 instances and approximately 1,000 images. It gives real camera parameters `(fx, fy, cx, cy) = (605.81, 605.63, 641.72, 363.23)` at 1280×720. It describes SAM masks and manually refined 3D bounding boxes propagated using ICP. These parameters must not be confused with the synthetic dataset's 640×480 K.

Unresolved: exact Real archive path, archive byte size, actual released frame count, depth PNG dtype/unit, and physically bound anonymous file delivery. The official OpenXLab page is JavaScript-only to the web text tool. A third-party converted HF card suggested a 0.74 GB release and fewer frames, but that was used only as a search clue, not as verified evidence or a download recommendation.

## Exclusions and limits

- [SuctionNet](https://graspnet.net/suction) explicitly reuses the GraspNet RGB-D images and splits; it adds suction labels rather than extra real scenes.
- [REGRAD author repository](https://github.com/poisonwine/REGRAD) says its main data is automatically generated in a physics simulator. The full [Baidu share](https://pan.baidu.com/s/1qeWsS1GaZ74wjsTKNF3N3A), code `xjtu`, must not be counted as a real RGB-D release. Its paper mentions separate real validation, but no independently verified domestic real-validation package was found.
- [Jacquard author paper](https://arxiv.org/abs/1803.11469) identifies it as synthetic RGB-D and simulated grasps. Excluded from real-camera collection.
- [Omni6DPose's official download page](https://jiyao06.github.io/Omni6DPose/download/) has genuine ROPE RGB/depth from RealSense D415, but currently links Dropbox. This is a different project from Omni6D-Real and does not qualify as a verified domestic download.
- [NOCS official repository](https://github.com/hughw19/NOCS_CVPR2019) links its real train/test data at Stanford and distinguishes it from synthetic CAMERA. No official domestic mirror was found.
- Searches for official domestic Cornell, BOP, SUNRGBD and NYUv2 mirrors did not establish a qualifying domestic download. This is a research limitation, not evidence that none exist.
- [THU-READ official page](https://ivg.au.tsinghua.edu.cn/dataset/THU_READ.php) links Baidu and describes real helmet-mounted RGB-D action video, but K and numerical depth format were not established, and it is less suitable for static tabletop grasp/pose cases.
- [HOI4D official page](https://hoi4d.github.io/) offers [Baidu](https://pan.baidu.com/s/1ZeX8SzU-gnJ-wpO9ZukulQ?pwd=7gfs), code `7gfs`, alongside separate RGB/depth/annotation/camera-parameter download categories. Its [official instructions](https://github.com/leolyliu/HOI4D-Instructions) describe decoding the depth video to depth frames. Exact bundle sizes, smallest downloadable unit and dataset-specific terms remain unverified.
