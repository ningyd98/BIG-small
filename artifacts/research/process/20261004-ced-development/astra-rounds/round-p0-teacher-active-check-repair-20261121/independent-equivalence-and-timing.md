# 活动检查独立复验

独立新增 15 个 CPU 测试。冻结 e20d228d 上 11 个等价控制通过，4 个新增生命周期控制按预期报缺少生命周期接口。候选源码上新增测试与原 authority 套件共 51 个通过，Ruff 通过。测试使用临时真实 SQLite，跨进程取消用真实运行中的软件 worker。没有启动 EGL 或新增真实试次。 [冻结基线日志](independent-frozen-baseline.public.txt) [候选复验日志](independent-candidate-verified.public.txt)

## 复验范围

- 软件 worker 已持有真实租约，独立进程提交取消后，同物理步的下一次检查拒绝，worker 以 CANCELLED 收尾。旧 authority 套件另外验证应用获取租约、跨独立连接的 renewal、取消、释放和关闭 attempt，以及快照活跃时 writer 等待。
- 租约数据库行保持原样，租约读者使用恰好等于到期时间的下一份 UTC 样本时拒绝。换入另一条可正常关联的有效租约后，应用仍按原 fencing 拒绝。原 authority 还覆盖 heartbeat 失败、异常或重复 attempt、原 worker/origin 变化、无权限的本地模式和带时区的时间戳。
- 首次 guard 放行后，分别测试同一配置对象就地修改、物理计数超限、当前 RSS 超限、owner 计数器到达原 deadline，以及机器人同物理步急停、碰撞、断开。每个拒绝均未增加已放行记录。
- 检查体内置换数据库 inode 后拒绝并撤销当前快照。恢复原 inode 后，另线程可续租，应用可重新读取。原 authority 另测入场数据库替换、schema 缺失及原认证嵌套 writer。独立测试验证外国线程获得不同连接，fork 子进程拒用父 reader，父读者仍可用。故意触发检查体异常、SQLite rollback 失败及两者并发时，原异常优先，连接关闭，后续 fresh read 及生命周期终结验证通过。

## 8 秒动作窗

上一真实开发试次 PRE→POST 为 150,403,383,894 ns，当时跑了 1,920 次原生物理步，登记 PNG 已是 level 1。31,238 次 owner_check 的互斥 owner 和 SQLite 时间分别为 46,546,297,453 与 32,172,434,593 ns。用历史记录做算术反事实，即使这两个分项归零仍余 71,684,651,848 ns。三种 render 返回区间含 GPU 执行和读回，独占 8,886,890,835 ns，合计 8,443 次。RawV3 编码为 11,298,542,979 ns，合计 3,261 帧。文件同步 API 调用共 1,100,041,508 ns，未测介质持久化。历史分项反映当次软件和硬件配置下的测量。 [计时机器读回](../round-p0-teacher-whole-action-20261120/action-timing-readback.json) [原跑登记](../round-p0-teacher-whole-action-20261120/run-registration.json)

两个无打点的完整对照，单次检查均值从 2.3916 与 2.3264 ms 变为 1.4338 与 1.3930 ms。假设 31,238 次检查复用这些离线均值，预计可节省约 29.16–29.92 秒，候选检查本身约 43.51–44.79 秒。该数字依赖历史检查次数、离线均值可迁移两个假设。动作窗结论须由同配方的新 PRE→POST 实测给出。 [CPU 配对原样本](../round-p0-teacher-active-checks-20261121/software-check-active-pairs.jsonl)

可用原帧评估现有 RawV3 与 Native spool 的附件处理。先逐项实测已验证 base64 的重复 decode/re-encode、字符串哈希及遍历，再试由同一帧与 payload 绑定的原始字节共享。任何候选均需要完整保留原非 canonical 内容的保存及拒绝路径、派生哈希、metadata、同步发布位置、异常顺序和磁盘产物字节。渲染侧仍应保持逐步采集、各 pass、状态校验及原时钟，先测清 EGL 渲染、回读和 CPU 转换各自耗时。前轮 6→1 PNG 提速已经纳入历史真跑配方。

## 证据索引

| 文件 | SHA256 |
| --- | --- |
| 候选复验日志 | `27f651a34cc56a336ca3086e16820d322c45e8b0f629916a36cfe4b70099c0d8` |
| 冻结基线日志 | `fc4126808a13bcac662ef195f8f7889db15219d6ea73c5ce0a01695e21a9e477` |
| 新增测试源码 | `898a637e29df2abf8ad2bf0fa45aeed5021926e41a9a36872f4608c136e1a27b` |
| 真跑计时读回 | `4012915b35fc6a1a7e8fdf6f173e373a94375cd0a2b8eced1c1f8dcab8decbf3` |
| CPU 配对原样本 | `603972a9886adab1816396199e57da594c96b21b85a257d8d541cda55548a2e2` |

冻结源码由 e20d228d archive 解包，测试进程在 pytest 启动前断言两个目标模块的真实导入路径并覆盖 pytest 默认 pythonpath。第一次子进程取消控制的脚手架误传字符串路径给需要 Path 的构造器，候选复验使用实际构造器、匹配当前测试源码树的 PYTHONPATH 和取消终态断言。第一次基线尝试的 pytest 默认 pythonpath 抢先导入候选源码，日志保留且排除出基线结果。 [路径遮蔽日志](independent-baseline-path-shadowed.public.txt)
