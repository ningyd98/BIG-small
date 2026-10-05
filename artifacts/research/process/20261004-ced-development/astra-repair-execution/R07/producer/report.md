# R07 单组真实恢复生产器软件交付

软件可独立审查；真实运行仍为 **0/200**。只新增三个 owned Python 文件及本 producer 目录，不改原验收合同、旧 collector、rootdocs、R1/R2 或 Git。原四个文件 SHA 与 fix-round-2 一致。沿已授权 AstraR7 设计执行 brainstorming/TDD/systematic-debugging/verification 流程，先缺模块与源合同 RED，再最小接现 T5 与被动 hooks GREEN。

## 锁定输入与正式域

新 seed2026100507 完整 v2: formal2400、foundation120、ood300、power120、recovery200、selection120。31 份显式本地原 metadata 连接7563 groups、6361 scene hashes、7440 physical keys/components，unresolved0；跨资产/颜色/camera别名不产生新物理组。完整 catalog 与每个来源SHA归档，不只是两个有限交集。此结论仅覆盖显式本地库存；外部或未登记使用历史仍须补入新 catalog、重新冻结审查，不能默认为不存在。

最终 namespace 是 `producer/protocol-final`，审查 hash:
`66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724`。
23 个执行源码/模型资产 pins、6 个输入 payload pins、Python/package版本、原配方、全部±方向/eligibility日程、2400 candidates 与预算归档。旧 protocol/protocol-reviewed 软件包已被源码变化淘汰，不能用于实际运行；均无实际分配。

首组 recovery-0001/attempt1，新 group `g-77a8915dc8c2eb94596a37633248a6d8`，scene hash `0cb7d448e904fa514ab555ad37a2f99cf90cde5a888a05f1afe3db6cbffc4e74`。原 raw320×240、同顶视camera/controller、dt.0041666667、120settle。registeredScene depth noise0 是现研究池明确 clean-raw 合同及既有 apply_scene 的 `_sensor_noise_std_m=0`，不是擅改 native默认.001m；扰动 schedule 保留另行原始/扰动观测边界。本 slice 不运行 cloudtransport，不用旧640原件降采样充新组。

## 实际接线与保全

只有 execute-once 延迟导入/创建现 MuJoCoCaptureSession。apply_scene只在fresh reset设置场景；reset0至terminal连续观察与每步PRE actuator均被原 hooks收集，原 command_seq1起及T5半开 ranges不改。settle120后以正确 `direction_y` 注入.02m/s1s，等待真实FINISHED；只有此后进入原NORMAL教师、settle0、原9动作与独立物理评价。保留actual ActionResult、完整RGB-D trajectory frames与失败unframed actions，不增加执行器，不用布尔success代替证明。最终被动adapter和原 `_recovery` 重算故障/动作/控制/安全/终点；整体 deadline是faultstart+60s。

分配先写独占ALLOCATED再actual；fresh nonsymlink输出、固定namespace/hash、不可重入或通过复制包重置ordinal。首attempt1、零隐藏重试。excluded/failed/partial均计入固定200分母；未启动组仍unattempted。回调只detach/enqueue，后台有界32768队列写journal，每64记录及close fsync。队列溢出明确失败；崩溃前缀和allocation保留，缺尾迹仍INCOMPLETE。普通无故障成功、forgeable summary都不能PROVEN。

首批预冻结wall1800s、retained2GiB、free reserve10GiB；raw/actuator每行保守16384字节预留，再检查实际文件总大小。不承诺200吞吐。生产器间fcntl lease拒绝并发，root仍需独占其他不使用该lease的renderer；SIGALRM对native阻塞的响应可能延后，外部watchdog可强制截止但只能保全已fsync前缀。

## 定向验证与反例

20项纯CPU测试通过，28.82s，见 green-final.log；owned Ruff check/format通过、mypy两源码通过。默认CLI与prepare均exit0，actual_calls0，未创建 allocations。真实backend.initialize在软件hook集成测试中被patch为禁止；软件原件fixture仅校验接线与原独立验收，不算actual证明。未运行旧完整批次或full suite。

RED原件完整保留：缺模块/预算/执行；组件物理别名；catalog入口；durable spool；wall alarm；copy-namespace绕过；renderer并发。合格CPU collector接线先复现队列2048饱和并失败（hook-contract.log），增有界32768后GREEN；没有隐藏忽略或丢行。最终静态修复仅同一路径的长字符串拆行，20测试之后无行为变化。

## 唯一首actual命令（待root独审，尚未执行）

```bash
MUJOCO_GL=egl PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/generate_rgbd_protocol_evidence.py --protocol artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/protocol-final --assignment recovery-0001 --attempt 1 --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/raw/recovery-0001/attempt-1 --expected-protocol-hash 66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724 --execute-once
```

这是单新组、单attempt调用；失败立即保全并结束，不自动挑下一组或重试。执行前确认 renderer队列独占和free reserve。实际wall/peakRSS/原件大小及失败完整性需首组测量。输出 `raw/recovery-0001/attempt-1`，6文件可验source在其/source，所有原件与result同目录；调用退出0仅表示原独立重算PROVEN，其他状态exit3。

## 下一接口与明确未完成部分

固定机会collector仅审计接口：现已归档 exact候选 MOVE_TCP、半径.02/timeout8，实际collector仍NOT_IMPLEMENTED，2400正式机会全部待真实source。root下一步应保留原双RGBD/实例与calibration/pass-state/context/object/action bindings及全arm碰撞范围，不能把候选JSON当真实label。

实际后由root从不可变locked pools创建新 derivative evidence-inputs，按all allocations登记每个attempt/source，包括failed/partial或missing-source诊断，调用公开prepare/verify；不得修改原锁定pools或只保留成功组。一个实际完整组即使PROVEN，整个2400/200池仍INCOMPLETE，G4仍false。该汇编接线和root独审/首actual不在本轮执行范围。

精确owned SHA、原四文件未变、命令、pin校验、预算、缺口见 report.json/source-hashes.json；新增源diff见 review-package.diff，独立副本见 source-package/。
