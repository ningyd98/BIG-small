# SQLite checkpoint 的真实 EGL 开发诊断

这次独立开发诊断由真实 worker 执行 `MOVE_ABOVE`。首动作 8 秒内从第 120 步推进到第 219 步，完成 99/1,920 个注册物理步。截止后的首个失败检查在采集返回处触发。原控制器未返回，保留了当前关节保持、急停及清退记录。正式教师资格仍为 0/9。 [派生结果及原件 SHA256](execution-summary.json)

## 软件验证与发行

复核了 Astra 两份计划和 18 件输入。原相邻回归日志按独立定位回读，公开版只脱敏了一处应用虚拟环境路径。先保留新入口缺失时的 4 条计划内 RED，再验证正式与开发登记双向拒绝、登记防迁移、真实 worker 的原磁盘拒绝及一条真实 SQLite UTC 快照。CPU MuJoCo 负控在测试时钟的 8 秒边界拒绝 `PHYSICS/BEFORE`，物理推进为 0，原急停生效。 [诊断计划](plan.md) [回归日志原件定位](regression-log-reference.md)

相邻回归最初 84 项通过、2 项失败。两处原生命周期辅助调用读取了原调用对象不存在的诊断字段，其中一处跳过了原 recorder freeze。Astra 兼容轮把诊断状态改为两个辅助函数的显式可选参数。原 2 项与新增 5 项定向通过，相邻回归最终 86 项通过，保留一项现有 Starlette/AnyIO 弃用警告。Ruff 通过。实测源另有一条新增 mypy 诊断，位于已保留的诊断终态 JSON 读取分支。 [兼容轮实施记录](../round-p0-checkpoint-helper-compat-20261120/step-report.md) [软件日志 SHA256](execution-summary.json)

诊断只接受固定 seed 11920067、用途独立的 `protocol.json` 和一次专用 claim。注册目录内的 `run/` 使用独立 SQLite，按正常 CLI 调度 `SimulationWorker.poll_once`、真实 lease、owner 时钟、`NativeFullHorizonRecorder`、EGL RGB-D 和原 SkillExecutor。首动作 PRE 及原参数与 v9 一致。诊断窗使用 PRE 的 monotonic 起点，后续控制与物理许可均经过原同步守卫。原正式 POST 门继续依据原超时语义。 [发行与源冻结摘要](execution-summary.json)

## 真运行与时间窗

2026-11-20 00:28:44 至 00:29:03 CST 使用 RTX 4070 Ti SUPER、独占原共享 GPU 锁启动一次，CPU 亲和性 0–15，进程启动时三段负载 1.96/1.95/1.97，空闲盘 71,272,824,832 字节。Python 网络审计记录 0 次尝试，任务模型、付费及真机调用均为 0。退出后同锁复取成功。456 件冻结源配置、资产与 92 件历史输入前后字节一致，其中包括正式协议、唯一正式 claim 和 22 组开发的 BEGIN、END、场景以及清单。导入核验记录了 618 个文件，其中 188 个项目模块，并保留已映射 MuJoCo/EGL 库的 SHA256。 [设备、进程、源和 SQLite 原件摘要](execution-summary.json)

PRE 允许，距原 executor attempt 入口 0.824214 秒。最后一次许可在截止前 1.957341 毫秒，发生于第 219 步的 `CAPTURE/BEFORE`。获准的在途采集 op701 的 owner 区间在截止前 1.357580 毫秒开启，RawV3 区间位于截止后 1.259018 至 10.929967 毫秒，owner 在截止后 24.967419 毫秒关闭。下一次 `CAPTURE/AFTER` 在截止后 29.226082 毫秒拒绝，同一步内完成保持和急停。守卫退出为截止后 35.043479 毫秒，采集、recorder 与后端清退为 419.171966 毫秒。之后物理状态未知。控制器此前签发 20 条关节目标，未返回；未进入 hold 或 POST。 [原件时间偏移、控制器与停机记录](execution-summary.json)

CLI 退出 1，worker 按原规则持久化为 `BLOCKED_BY_ENV`，primary 为诊断 8 秒截止。原件保留 242/242 个分配帧、705 次实际渲染 pass、219 条物理状态，inventory 索引 1,228 件共 174,716,670 字节。把 inventory 自身计入后，生产记录共 174,874,258 字节。记录为 2,290 次允许、1 次拒绝、1 次守卫失败结尾，observer 和 audit 原错误数均为 0。原始 SQLite、RGB、深度、控制器、守卫和 owner 记录保留在 Git 忽略的受控目录，公开摘要附复核定位与哈希。 [运行原件清单](execution-summary.json)

## 可定位的时间开销

实际 worker 的 2,795 次 `check_active` SQLite 段全部进入并完成新只读快照，其中首动作窗记录 1,331 次，SQLite 上下文累计 1.345148 秒，约占该 8 秒窗的 16.8%。计时含读取上下文进入、退出以及两次单调钟采样。在原件中能配对 117 个完全位于窗内的采集区间。RawV3 采集区间并集 1.069169 秒，raw 关闭至 owner 上沿的尾段并集 1.655190 秒，完整采集 owner 区间并集 3.042196 秒。尾段含文件转换与落盘、END 检查和 owner 封口。它与 SQLite 计数窗口重叠，分项无法相加为总墙钟。另有一份授权在途采集跨窗，单列于叙述与机器摘要。 [分母、定义及分角色时间](execution-summary.json)

这 99 步证明新 SQL 实际穿过生产采样和控制路径。即使移除首动作窗已观测的全部 SQLite 时间，剩余墙钟仍超过 6.65 秒，采样只覆盖原时域前段。旧正式组来自不同 seed、完整 1,920 步且在 POST 测得 332.829 秒。旧辅助 EGL 短窗没有生产 worker、SQLite 与原 recorder。三者各自保留原分母。此次诊断不计入资格，原 v9 首组 claim 保持已消费。 [正式首组原报告](../round-p0-first-actual-v9-teacher-20261119/step-report.md) [SQLite 软件验证](../round-p0-teacher-checkpoint-cost-readonly-20261119/implementation-report.md)
