# 首动作活动检查总体方案

总体方案；项目指定 gpt-6-astra 修复计划单列。基线 e20d228d5220c49b0194c4d2563ba23c2a3fde80。

## 失败证据

seed 11920067 首次 MOVE_ABOVE 控制 725 步、保持 1195 步，末帧齐全；PRE 至 POST 150.403383894 秒，唯一拒绝 STEP_TIMEOUT，限值 8 秒。原正式资格 0/9。窗口内 31238 次 owner_check 与 SQLite，互斥耗时 46.546297 与 32.172435 秒。历史账面即使全扣仍余 71.684652 秒；render 调用累计 8.886891 秒，编码封装 11.302026 秒。它们只是原执行测量，不能推出跨实现的硬下界。

## 源码诊断

check_active 通过 policy 及 protocol 两遍解析登记协议。在 UTC_LEGACY_VETO 的单一已锁 BEGIN 快照中，外层、worker._raise_if_cancelled_or_timed_out、read_visual_worker_lease 各自 get_job，读取并反序列化相同 job。_guard 随后独立读取当前机器人状态，_consume_capture/recorder_source 使用完整活动回执。同一物理步可发生多个需要新观察的边界。

## 实施范围

先用原件对齐 CONTROL/HOLD 的检查点，用零模型、真实 SQLite 和运行中 worker 夹具交替配对计时协议解码、job 读取和物化、配置 canonical、快照生成。依独立 gpt-6-astra 修复计划选择有收益的最小改变。优先在一次调用中只解码协议一次；若跨调用派生标量，绑定不可变的冻结原字节，维持公开访问器返回副本语义。可在单个真实 teacher 快照内按键复用原始 SQLite 行，每次返回独立模型；这只消除 SQL，仍须测净收益。事务/异常退出即销毁，保留每检查点新事务、前后数据库身份检查；本地时域、嵌套 writer 和其他调用方沿用原路径。保留全部 guard 与每次取消、身份、lease/attempt、heartbeat、时钟、RSS、配置及物理资源读回。保留配置原位变更检测。

## 软件验收

同物理步相邻真实检查间用独立写连接提交取消、释放/替换 lease、关闭 attempt；逐项覆盖 lease 自然到期、任务截止、owner 原截止、heartbeat 失败、RSS/步数超限、配置原位更改与机器人急停/碰撞/断连。下一原检查点按原顺序拒绝，无后续副作用。测试数据库文件替换、嵌套 writer、异常清理及跨线程/进程隔离、同快照返回数据独立性。对比成功/拒绝回执字段、事件顺序、采集计数并运行相邻回归；计划外失败另开 Astra 轮。

## 开发实测

负控及回归通过，冻结候选源、原协议/控制器与原登记 SHA，确认 MuJoCo/EGL、磁盘及原注册预算、独立 reader 可用。以新 ID/数据库/输出目录一次同初始位姿独立开发实测；固定 seed、控制器与保持、逐步采图/校验、渲染与分辨率、原 PRE/POST 同锚 8 秒、原安全和清退路径。一次领取/尝试，零重试、零任务模型/付费/真实硬件。独立核对物理、计时、停机、租约/attempt 原件及实际动作准入。保留上轮冻结、历史 claim 与 0/9 正式资格。

## 后续边界

若仍超时，用新原件重做互斥计时，对剩余主要耗时逐项评估安全等价方案，交替离线配对、给出可证节省上界与未测因素。新根因/范围变化提交新 gpt-6-astra 计划。取得具体改进证据及新登记后才再运行；若无法跨越门限，写实测阻断及其适用边界。

## 输入 SHA256

- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/phase-summary.md f0be70dc15ebb4336abfb4eabf3948a1d4b54a8258d0406411a020ee476282cf
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing.md 5788ac34229122ffe94e52d78ace4ba904b646ea8c4497f023725786a2e8138a
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/independent-physical-readback.json d0fbf0e3b20e889a5a3031ebad10950fc709b6ee2f09b19e134fdc427365f777
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/producer-result.json 02745d929df383deb550fc7fc42202f825f52705f0a0447198f3401c869ef9ad
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/run-registration.json 4a31cc0705ee761942967503fbe3c7ae9bc2e9e442bcb069eb0bea943541e305
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/retention.json 9b64b5ff8d013c8b41b61741a89b388dbffc0ec561fd048fdc035f9fe86a6cd2
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/plan.json 2024cfd0cce983f29ceea54deb242b97907a627c12d35bf964848ee4252cc9e1
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing-negative-readback.json c7755b41df52f842af63ca88aec687a691f081e7e8b43d7a0cbc31511daa0396
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing-probe-benchmark.json b7370079e61e3a69224dce435ba4fd85be7af90ea5ba25fabdc4c1fca00566c6
- artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing-readback.json 4012915b35fc6a1a7e8fdf6f173e373a94375cd0a2b8eced1c1f8dcab8decbf3
- src/cloud_edge_robot_arm/research/native_collection_application.py 409911c4e218d3b070ea1eed9ddf3682bcd382332e5352bb3da09cb1e221fb32
- src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py cdd3c626c15331dfef43771619e958158c55ba75f664f39a976516cdcebbb7c1
- src/cloud_edge_robot_arm/simulation_runtime/worker.py 35844661596f08b704ee4b5a04a16c487f2d708e8283918e4353208e318b433e
- src/cloud_edge_robot_arm/vision/worker_owner.py 8128f8253e82deef5fab75fe5d24e79cd896c5588b9548b5ea4afe563731a21c
