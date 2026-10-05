# T12：真实 worker 工厂接入

已修改实际 `SimulationWorker` 入口。显式配置角色绑定、事件仓储和机器人身份后，工厂从真实 SQLite job、当前租约和唯一在运行 attempt 构建协调器；原始任务 UTC/单调时钟在初始化之前记录，持久预算保留原始限额和绝对截止时间。

初始化前及 initialize、reset、settle、episode 返回边界重新读取真实租约，并校验完整编译器、角色、仓储、设备和 raw recorder 源码。使用同一个 MuJoCo backend、借用相机和控制器。OPENCV 在真实 reset 前进入 raw observer，SETTLE 只包裹已有 120 次初始化物理步；工厂创建的唯一 SkillExecutor 交给既有视觉执行入口。LEGACY 默认和原始 reset/settle/capture 顺序保留。

验证：55 项 CPU 测试通过，含 15 项工厂测试；明确排除 1 项需要实际渲染的既有测试。Ruff 检查及格式检查 2 文件通过，cold mypy 1 文件通过，git diff check 通过。首次合并执行为 53 通过、1 失败：既有 capture-only 渲染测试因 GLFW 缺少 DISPLAY 失败，保留该失败，不记为通过。

工厂测试使用真实 job/lease/attempt/event SQLite，仅替换物理接口、raw recorder 协议探针和 episode；不运行真实模型或机器人动作。测试覆盖来源漂移、初始化/settle 取消、原始截止时间、真实共享 episode、禁止直接入口编造任务时钟、raw observer 先于 reset 及 sole executor 身份。

本报告证明软件工厂接入，尚不证明 raw COMPLETE、几何/连续运动证书、Max 实测来源、METHOD 或 INITIAL/FINAL 验收。未开启额外恢复能力，边缘模型型号后置。

来源及精确命令见 [verification-summary.json](verification-summary.json)，两个受测文件快照保存在 `tested-source/`。

## 局部补充：原始监督/等待选项透传

2026-10-05：实际工厂现在从原始 SQLite `job.draft.parameter_overrides` 读取 `supervision_period_ms` 和 `advance_physics_during_wait`，在已有 binding setup 的 backend.initialize 之前严格验证。period 只接受有限正数且拒绝 bool；wait 必须为 bool。未指定字段保持 None/False；仅对 period 做毫秒到秒的单位换算，不制造默认周期或强转字符串/flag。late policy 使用同一原值，继续接受真实 runtime 对不可变 job 配置来源的前后核验。原任务时钟、租约来源、source inventory 与唯一控制器绑定保留。

实际 SQLite RED 首先复现 4 个合法原始配置未透传导致的拒绝；加强 zero-setup 断言后，8 个非法配置复现旧检查时间点仍会 initialize/reset/settle 的遗漏。修正后新增 14 个 CPU cases 覆盖整数/小数周期、单独 WAIT、缺省、非法 bool/string/0/negative/Inf/NaN period 和非法 wait flag。非法配置在 initialize/reset/settle、相机/模型/控制回合之前停止，真实 attempt 仍关闭并释放自身 lease；没有实际渲染、provider 或动作调用。

最终精确检查：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_visual_worker_factory.py tests/test_rgbd_lease_handoff.py -q` 为 **54 passed in 35.99s**（其中 factory 29 项），保留 1 个现有 Starlette/AnyIO `BlockingPortal` DeprecationWarning。两文件 ruff 检查通过；worker.py 的 `mypy --follow-imports=silent` 无类型错误，仅现有 unused override 配置提示。本补充未重写历史 source 快照，也不构成 Max 实测、raw COMPLETE、INITIAL/METHOD/FINAL 或实际研究验收。
