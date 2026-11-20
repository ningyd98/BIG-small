# 教师首动作实测与生产路径

一次独立开发实测完成了原 `MOVE_ABOVE` 的 1,920 个物理步，并取得控制器返回、保持、终端采集和真实 POST。PRE 与 POST 使用同一原单调钟锚，相隔 **150.403383894 秒**。原 8 秒门以 `STEP_TIMEOUT` 拒绝，实际耗时为门限的 18.8004 倍。独立的测量和准入字段为 `measurement_complete=true`、`action_pass=false`。正式资格为 0/9。 [生产回执、原件 SHA256](producer-result.json)

## 软件与冻结

复核 Astra 计划全部 39 件输入。新开发入口限定一处源码绑定的发行目录、一个已登记 assignment 和一条独占 worker BEGIN，输出和 SQLite 归属同一运行。保留原 worker 领取、lease、续约、取消、物理安全和 POST。只在新开发发行冻结 PNG1 并传入会话和 RawV3 的两个编码点。旧短窗的 8 秒中途守卫继续作用于旧用途。 [Astra 计划](plan.md)

原 RED 保留 3 个功能失败及 4 个缺失注册能力的 setup 错误。首次整合的早退负控已得到正确的生产终态，测试对该字段的读取名称与接口约定不符，原结果另存。随后相邻回归 130 项通过，冻结源定向 10 项通过。正式 reader 拒绝新发行，whole CLI 拒绝旧短窗路径，两次均退出 1，未生成试次。Ruff 通过。定向 mypy 的 31 条旧诊断在基点与新源逐条一致。 [软件原件与 SHA256](producer-result.json)

正式 v9 与旧开发短窗保留原登记、claim、运行库及回执。新冻结与旧短窗使用相同 seed 11920067、资产、标定、动作时域和物理配置，新的 assignment 与 worker 身份独立。进程开始和结束均核得 457 个冻结源、101 个受保护输入。运行使用原 GPU 共享锁和 RTX 4070 Ti SUPER EGL，启动磁盘空闲 58,518,179,840 字节，CPU 负载为 1.39/1.39/1.28，亲和性为 0–15。生产体原件所录 `ru_maxrss` 为 765,718,528 字节。Python 审计记录 0 个网络事件，任务模型、付费和真机调用均为 0。 [冻结源、设备与进程原件](producer-result.json)

## 原动作结果

北京时间 2026-11-21 00:10:33.352 启动，00:13:19.413 结束，GPU 锁复取成功。完成 120 个准备步后，原 PRE 通过。控制器于物理步 845 成功返回，共推进 725 步。随后原目标保持 1,195 步，到第 2,040 步完成终端采集 `acquisition-3385`。POST 的唯一 Shield 拒绝规则为 `STEP_TIMEOUT`，末端位置条件通过，综合准入拒绝并保存原因 `common_proprioception_or_shield_gate`。首动作后已关闭 guard、recorder、capture、backend 及 owner。原 worker 终态为 `BLOCKED_BY_ENV`，CLI 退出 1。 [阶段、退出与源身份](producer-result.json)

生产端保留 2,040 个总物理步、8,813 次渲染 pass、16,947 个索引原件和含 inventory 的 2,121,333,976 字节。32,704 次 SQLite 检查全部使用真实 UTC 只读快照。动作锚后累计 31,240 次 SQLite 上下文，包含重叠区间的 32.090 秒，互斥开销以原独立计时读回为准。物理、像素、POST、lease 与时序的独立证据另行交叉读取。 [生产量与原计时 SHA256](producer-result.json)
