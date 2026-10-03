# SDD ledger — plan: docs/superpowers/plans/2026-10-03-additional-rgbd-readers.md

BASE: a778fd1f31dd5ad0005812cd00fccb25896c5a1f
Baseline: external RGBD 237 passed, 2 skipped (7.24s); /tmp/bigsmall-next-baseline.log.
Ruling: 继续当前工作区且不提交 — 已批准计划与保留用户改动优先 — 通过测试和文件清单审查而非干净 git diff 区分本次增量。
Ruling: 默认推进新增数据接入 — 最近阶段已下载数据但未接统一 reader，已给用户可选方向且无回复 — 主路线 T3/T4 保持 READY。
Pre-flight: Task 1 produces sealed sample records; Task 2 consumes schema and pairing helpers; Task 3 consumes manifests and records. One versioned format shared across all three; native calibration facts stay in source-specific adapters.
Pre-flight: Task 2 preserves official split and source frame index; Task 3 must not promote a paired subset into a complete robot trajectory. New selected-scope status is separate.
Task 1: complete — RED 11 failures for missing format and exclusion fields; GREEN 248 passed, 2 skipped in external suite. Explicit exclusion preserves raw uint16 and requires policy evidence; sealed records reject path/hash/identity tampering and isolate GT.
Task 2: native-format RED 7 failures; GREEN 7 passed including protobuf/zstd, CRC rejection, ROS none/bz2, numeric-topic guard, official-test/pose retention. Float32 metric equality uses tolerance (source raw is exact).
Ruling: 原子发布与固定清单在 Task 3 一并接入 — 共用 CLI marker 接口避免重复实现 — Task 2 完成状态待真实转换与 Task 3 集成测试通过后记录。
Task 2: complete — 三套真实源全部转换成功；Industry 370 对/6场景/771实例；MicroAGI108对，日志差最大4.918ms；VINS973对，末尾RGB源帧号973未配对。固定原件复验、派生清单和原子完成标记均保存。
Task 3: complete — 三套 SELECTED_RGBD_VERIFIED；实际全帧校验、15帧预览、CPU0/2及首/中/末逐像素一致、pause/seek/resume与GT隔离、重复部署/REUSED均通过，acceptance.json。零新增网络字节。
Task 3 Ruling: MCAP日志时间不等于采集时刻 — 新增RED/GREEN测试并使 replay acquisition_time_unknown=True — 不变造timestamp或宣称采集同步。
Task 4: underway — external267passed2skipped；MUJOCO_GL=egl旧RGBD路径172passed(1条既有Starlette弃用警告)。第一次未设置MUJOCO_GL的扩展回归在既有渲染器abort，栈和环境与已记录的egl要求相符；保留no-egl日志并用正确环境完整重跑通过。
Task 4: review Important待修复：已有完成raw时plan仍要求全转换峰值，可能误报BLOCKED_STORAGE。独立审查由executing-plans要求的一名fresh reviewer执行。
Task 4: complete — 审查 I1 已补两项 RED/GREEN，验证成品免重复转换估算、损坏成品不可绕过核验且余量仍生效。审查者复核2passed，最终0 Critical/0未解决Important。最终 external269passed2skipped；旧路径172passed；Ruff通过，mypy --ignore-missing-imports 检查19源文件通过。修复后再次真实verify_acceptance全部1451对通过，三套REUSED/COMPLETE、0新增网络字节。
Ruling: 收尾沿用既定保留当前分支/不提交不推送选择 — 不重复询问集成选项，不触碰其他工作树 — 本次实现与来源摘要记录在code-manifest.json。
Final: 实现、测试、实际文件、文档及独立审查齐备；本计划的临时workspace移除，进度副本保留于验收目录。原完整数据目标及研究T3/T4未升级。
