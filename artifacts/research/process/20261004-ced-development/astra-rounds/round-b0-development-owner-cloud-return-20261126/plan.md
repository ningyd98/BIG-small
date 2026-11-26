# B0 开发 owner 的原合同、租约与 CLOUD_RETURN 读回

gpt-6.2-astra 基线 `134463bb50c063d69454f98f678ad49d6e5691d4`。在新私有 SQLite 保留真实 owner 状态和拒绝。使用已排除开发组 `g-e361d32e58d73ff085a20b4cdce1a440`。既有 182 个光学候选产生同一个 worker 抓取输入。现行证据门在首次 worker 落地发布前运行，原几何和运动界为空。本轮固定原 RGB 种子，测试一个本地语义响应。[冻结源证据](../round-b0-static-worker-grounding-sensitivity-20261126/step-report.md)

## A 零曝光历史帧负控

在新 SQLite 用 PilotWorkerAttempt 和当前源码绑定开发角色，形成真实作业、租约及 attempt。真实 VisualWorkerRuntime 发出首帧采集 claim。用与旧曝光相同的 episode ID 成立新开发 runtime，仅隔离测试 UTC 前置条件，该作业没有原物理 episode 所有权。将完整旧第 120 步帧原样送入 complete_capture。软件 RobotState 仅用于时钟负控。要求原拒绝 `registered capture episode/calibration/claim clock mismatch`，原 UTC、episode 和校验和不得重写。查 SQLite 确认保留 pending claim，无完成采集、模型、原合同或 CLOUD_RETURN。旧帧若只在一般条件中被拒绝，仍保存具体拒绝。任何计划外错误封存并停止。

## B 本地新鲜采集与真实 CLOUD_RETURN

1. A 通过后，用同编译 XML、固定种子、原 45° 320×240 相机和共享独占 EGL；新作业和真实 episode。记录原 CONFIG、RESET、120 步 settle 和两次原自动曝光；之后只允许一次已发 claim 的原 RGB-D/实例曝光。限制额外积分、技能执行及所有后端动作命令。核对每次采集时钟、装配及原窗口首帧的图像一致性。外部隔离禁止网络与凭据读取。
2. 用真实 PilotWorkerAttempt、VisualWorkerRuntime、原 capture 与 raw v3 记录器。采用 _VisualEpisode.recapture 执行首帧。原 SQLite owner 发 reserve_plan，调用现行 adapter.plan，仅在 _request_visual 返回封存开发响应，确认原 RGB-only 目标 (167,112) 和目的区 (128,67) 的模型码解码不变。按原 planner 路径附角色摘要并由现行 complete_plan 完成。保留角色绑定为本地 fixture，真实云端身份、费用、等待时钟均不由本实验提供。
3. 使用原 _VisualEpisode.run_worker_online(draft) 作为有界入口。从实际原方法保留 adopt_plan、持久化 checkpoint、tracker、监督初始化及 CLOUD_RETURN。判定若 STOP 则保留原 STOP；若 REOBSERVE 则在 recapture(advance_steps=1) 入口截断，禁止领取下一帧和积分；若意外 CONTINUE 则在 prepare_worker_step/execute 前拦截并报告。不使用整机 run_visual_episode 的终止停机包装器。不要绕过任何真正的原生准入或硬停止。先于目标边界的拒绝如实归档，禁止重试、补拍、点位重选。
4. SQLite 关闭后用只读连接复核 bootstrap、作业、租约、attempt、原合同、owner publication、checkpoint、phase 和路由选择。A/B 分开。CLOUD_RETURN 不是 PRE_SAFETY 或 PRE_SKILL，三者分别计数；没有有效 grounding publication 时保留空值。记录实际框架时钟与研究时域缺失。两次独立冷读需一致，真实 public 摘要不携带完整图像或 DB 字节。原始校准、门限和正式分母不变。本轮不另走 prepare-only 分支。新增控制命令、真实请求、正式试次及硬件均为零。
