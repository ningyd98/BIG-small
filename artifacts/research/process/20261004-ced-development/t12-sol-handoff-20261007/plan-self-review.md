Ruling: 新问题先Astra；本编排不授予跳过原命令次数/失败原件/审查的权力。

## Per-task consistency scan

|Task|Text/files/tests/interfaces|Result|
|---|---|---|
|P1|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P2|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P3|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P4|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P5|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P6|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P7|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P8|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P9|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P10|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P11|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|
|P12|原任务接口、文件与测试/命令完整继承；PROPOSED不当已有实现|一致；actual按各任务门|

## Shared file and dependency interface scan

|Tasks|Shared file/interface|Ruling|
|---|---|---|
|P1/P4|; P1验收→P4输入|仅按依赖/单写者串行；前置原件独审后消费|
|P1/P9|; P1验收→P9输入|仅按依赖/单写者串行；前置原件独审后消费|
|P2/P5|; P2验收→P5输入|仅按依赖/单写者串行；前置原件独审后消费|
|P2/P7|src/cloud_edge_robot_arm/research/native_geometry_calibration.py, src/cloud_edge_robot_arm/vision/native_calibration.py, tests/test_native_calibration_source.py; P2验收→P7输入|仅按依赖/单写者串行；前置原件独审后消费|
|P3/P9|; P3验收→P9输入|仅按依赖/单写者串行；前置原件独审后消费|
|P3/P12|; P3验收→P12输入|仅按依赖/单写者串行；前置原件独审后消费|
|P4/P5|; P4验收→P5输入|仅按依赖/单写者串行；前置原件独审后消费|
|P4/P7|; P4验收→P7输入|仅按依赖/单写者串行；前置原件独审后消费|
|P5/P6|; P5验收→P6输入|仅按依赖/单写者串行；前置原件独审后消费|
|P5/P11|src/cloud_edge_robot_arm/vision/worker_runtime.py|仅按依赖/单写者串行；前置原件独审后消费|
|P6/P7|; P6验收→P7输入|仅按依赖/单写者串行；前置原件独审后消费|
|P6/P8|src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py, src/cloud_edge_robot_arm/vision/execution.py; P6验收→P8输入|仅按依赖/单写者串行；前置原件独审后消费|
|P6/P11|; P6验收→P11输入|仅按依赖/单写者串行；前置原件独审后消费|
|P7/P8|; P7验收→P8输入|仅按依赖/单写者串行；前置原件独审后消费|
|P8/P9|; P8验收→P9输入|仅按依赖/单写者串行；前置原件独审后消费|
|P8/P11|; P8验收→P11输入|仅按依赖/单写者串行；前置原件独审后消费|
|P8/P12|; P8验收→P12输入|仅按依赖/单写者串行；前置原件独审后消费|
|P9/P10|; P9验收→P10输入|仅按依赖/单写者串行；前置原件独审后消费|
|P9/P11|scripts/run_rgbd_pilot.py|仅按依赖/单写者串行；前置原件独审后消费|
|P9/P12|scripts/run_rgbd_pilot.py; P9验收→P12输入|仅按依赖/单写者串行；前置原件独审后消费|
|P10/P11|; P10验收→P11输入|仅按依赖/单写者串行；前置原件独审后消费|
|P10/P12|; P10验收→P12输入|仅按依赖/单写者串行；前置原件独审后消费|
|P11/P12|scripts/run_rgbd_pilot.py; P11验收→P12输入|仅按依赖/单写者串行；前置原件独审后消费|

P1子项：OC2完成67剩余验证→独审；RW1只完成71格式/窄回归→独审。初始作者不得提交或自审。
计划自检覆盖设计1–9，五类Review Focus均由原对应任务测试覆盖。
文档验证：document-verification.json；产品/actual验证未由编排运行。
