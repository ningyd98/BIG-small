# G1 径向装配错校准负控见证修复计划

模型 `gpt-6.2-astra`，Git 基线 `f02cc9db7311c4016fd7bfa3b74cfc747bbff6c3`，失败构建 `4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d`。

## 原始失败与归因

+15mm 新构建首个可见双码正控的 servo/target 均通过、物理步0。11个负控已采完并封存，wrong-calibration 的 original_guard_evidence=false 阻断预检。旧 g1_dual_probe.expected_refusal 要求 measurement.reason=registered_camera_mismatch 且两个错误串均含 calibration；历史沿既存 tracker 更新得到 registered collection geometry unavailable: observation_calibration_version_changed。新径向适配器以 tested 当前包重新构建 tracker，在更早的初始几何层得到 initial registered geometry unavailable: registered_camera_mismatch。两种情况下原生伺服均给出 servo MuJoCo calibration does not match frame intrinsics and pose。新包无目标、无 accepted servo、零命令、零物理步；未放行的旧运行原件一律保存。

## 限定的开发修复

仅修改 scripts/graduation/g1_visibility_mount_runtime.py 中 negative_controls 的 wrong-calibration 见证与 tests/test_graduation_g1_visibility_radial_runtime.py。保留 frozen probe.expected_refusal、生产 tracker/servo、准入、相机、资产、时限和碰撞策略。用现有分支真实拒因，在开发适配器精确枚举两条已验证路径，不修改错误文字或制造例外。其余负控沿原规则。与本 case 无关的异常一律为未证明；不得改用宽泛包含 camera/mismatch/calibration 的规则。

## 判定契约与软件 RED

封存的 source/tested 文件改动仅允许 calibration_version 由 f33940579c533afe 变为 g1-intentional-foreign-calibration、独立 frame_id/observation_id 和据原模型重算的 checksum；RGB、depth、mask、内外参、scene/episode、采集钟及 sim_time 完全相同。重算原包/测包摘要与模型校验，核对结果绑定 tested ID/checksum。要求实际 servo_refusal 精确等于上述 MuJoCo 校准错误，observer 的顶层 reason=registered_camera_mismatch、usable=false，目标层拒因仅允许上述两条原生错误，target_emitted=false、servo_accepted=0、commands=physics_steps=source_step=0。用原新包复现老验证器 RED 并让新见证通过；为旧见证双姿态及错场景、过期、遮挡/歧义、错误源/几何、丢失某一原生拒因、串换包或输出动作做反向断言，防止异种失败误放行。完整径向及既有可见性回归须通过。

## 选型和设备重验

原静态 +15 mm 选择可以沿用，前提是 XML 47aae36ececab0d6bedd055a976fd74ce895e85a9827e1d0689afa6e3c3f8715、注册物理变换、相机、用于筛选的原稠密轨迹、几何与像素算法和封存报告逐项等同。重核旧 d01/d02 稠密 clearance、原八姿态和1088光学结果及 SHA、新代评分独立偏移绑定；只放行验证器差异及由此派生的合法源/构建身份。正常径向 prepare 生成全新 generation，在独占 EGL/原解释器、依赖、顶视 320×240、16GiB、919 原件和旧账本核验后从正式的开发 CLI preflight 运行。独立 owner、4 个预定零步复位（双码、仅7、仅8、全遮挡）、11 负控、新装配当前包两次独立像素读回与 seal、真实源校准绑定、零运动/零步以及全遮挡惟一保护 hold 全部核实方可生成新 preflight.json。所有原包/结果、原生错误、软件与新现场记录独立封存。

## 验收边界

本轮开发预检仅签发该新代历史训练资格；沿机械计划为 d02 创建新唯一 train- 标签单槽单次、原八意图 native capture/audit、双盲像素与独立物理 score；复核稠密接触、实际抓持/释放及原时限。已知 d01 碰板按机械计划独立验证。真实历史完整物理成功和主计划其他门槛满足后才可冻结候选进入四个新开发摆放。不得以软件见证或静态选择代替动态成功。遇其他拒因、装配/算法漂移或计划外失败先保留证据交 Astra。步骤报告及阶段总结分列开发软件、零步、历史动态、正式与实机，本专项正式、实机、任务模型调用为0。

## 输入文件与 SHA256

| 路径 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/plan.json` | `f73a383f23408f6d53d30677928545ed4e515419ab0ed16da7b391c1275ed015` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-selection.public.json` | `509b79dacf796a20038b510c49a7204f6260614a13335d04186faa0941eb2511` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/assembly.public.json` | `c5fcdcf05cbffc6d527bd2c3e538a6be41f5415094e900c9174ff34dad7ec140` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-clearance-15-summary.public.json` | `8286ea088e119ae70b17d500d20b71932480ae42a23b0fffe005e14cf7d24903` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-clearance-15.public.json.gz` | `73ab945d884f58327e4a1c1859661d9fefde4df0dc2a9f40ffdf6502be5ec826` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-optical-15-summary.public.json` | `3dd4cfd9ebd4624af37f1e6033d05afa6a8955d5ba462ce7aeb9e19557cf3be1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-optical-15.public.json.gz` | `87150ea9f7479cc7a61bf27454438007f1b0515f80e8e519ce4af2c5b32458d0` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/first-preflight-calibration.stderr` | `93511a6efe64f3ce285c45bfd50a8c1aa01bb6061a97350fb399cb41cb70217f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/runtime-first-preflight.public.json` | `ea669a33b3083c0d3968606985633045dfdb0566ef6a342a3965e6ce1269d366` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-first-refusal-dual-marker-20261124/zero-step-probes.public.json` | `e8d1cbee3e655bfb8eb2daa54ed4236fa738e312ef9e2ce7b7cbc91773931c55` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/negative-controls/wrong-calibration/source.rgbd.json` | `ff270858cf5861612cebb64f6b3e906d20bd6b9c1349157a9b63e009fdf52060` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/negative-controls/wrong-calibration/tested.rgbd.json` | `ecf0a0667d31078b43177a4687a65dbd3e3175512b42a2118a8814b77a8a7e1d` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/negative-controls/wrong-calibration/result.json` | `b98ef8d438df6d71ab33e5be15e9ec84a9a5921b4000f4afc1f6d7f63b144e2a` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/negative-controls/seal.json` | `c615941db275d00933993ea2650f6092d2343c75bf8664f8970467fa531f9e84` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/sample-evidence.json` | `409a3ccb0e63ea05148846680241703b0750588d03c0f3b504c3d5fbcadbdb8f` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/trace.json` | `bca544a84ba98113f9aaf12b1271cc9a16ef66eb9b8c8e6136edf8399dfa55d6` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/positive/interrupt.json` | `d6fb78b7e0a65b12c3bae33df8053e6f91eea8ab835661f554515193504a1b0d` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/zero-step-radial-n4ffe8zw/compiled-geometry.json` | `93d151a0b047165077b3395e586c48e30b36b1ec89f66b7a0e1cf27a240b5dbc` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/runtime-build.json` | `4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d` |
| `scripts/graduation/g1_visibility_mount_runtime.py` | `f2329b442b2189b58a9f068bd4c2832219eedf6edc9f736df3984a357478bcd7` |
| `tests/test_graduation_g1_visibility_radial_runtime.py` | `4c52bfe52f0eb55227d1e8a94388ebf2b8d57387e81e4e0adaa63d4ca68cb3bc` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/scripts/graduation/g1_visibility_mount_runtime.py` | `f2329b442b2189b58a9f068bd4c2832219eedf6edc9f736df3984a357478bcd7` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/scripts/graduation/g1_dual_probe.py` | `a1f0586834a134d91e7c9c22fb644f72a12575e1e3b6ffee57ef7807d5daf7b0` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/scripts/graduation/g1_dual_observer.py` | `a6c919b82e769d432c4ce425b4f44c6b8c228bff8ef4b1d7787f28689c416db3` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/scripts/graduation/g1_visibility_trials.py` | `d858fa02c897e6d404ac783cfb20ade52a8190aea109f047b4fb750169fa3760` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/scripts/graduation/g1_dual_pixel_readback.py` | `93c82f96233e480bef041fee1655401d20ed7ffb0dc1e3442c26e30f34af238e` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/src/cloud_edge_robot_arm/vision/servo.py` | `991f67035706026b5219b43e398f020be98fabba311246846a30bb9372962768` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/src/cloud_edge_robot_arm/research/native_collection_grounding.py` | `fd7c8052cb936e12a90be858f826a8038970404a4018ecbc90eeb26a6beb7aad` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/4077ed4f0d6d9114305a9605a11a512b44a6437e9872c608ed7951e3d902739d/runtime-source/assets/robots/franka_panda/scene_g1_development_dual_id7_y115_id8_x115_low_bracket_v3.xml` | `47aae36ececab0d6bedd055a976fd74ce895e85a9827e1d0689afa6e3c3f8715` |
