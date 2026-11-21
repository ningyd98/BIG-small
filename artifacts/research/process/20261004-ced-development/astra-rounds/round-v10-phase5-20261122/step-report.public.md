# Phase 5 v10 再登记与首组启动预检

2026-11-22，以 `becd1ab6` 为基线。实施计划由 `gpt-6.2-astra` 制定，32 项工作树输入和 3 项冻结输入的 SHA256 已复核。[计划](plan.md)

## 登记

用现有 `--prepare-only` 入口在两个独立目录生成登记，得到逐字节相同的 80,136 字节文件。唯一释放组为 `native-p0-v10-20261121-0001`，seed 为 `11921001`，其余 8 组为 `PREASSIGNED_NOT_RUN`。权威登记目录只有 `protocol.json`，claim 数为 0。[v10 登记](registration/protocol.json)

| 核验对象 | SHA256 |
| --- | --- |
| 协议文件，含末行 LF | `da431fdb96f8b2672fb621d4ca4c87b673835f26ce874c7ce03da8fb043a7972` |
| 协议 canonical JSON | `bca768e63e0e7a1fa5d4e4c1b0ca322f64eb8cd1c5c66fa126758942e8036a91` |
| 456 项来源清单的 canonical JSON | `186e76435e7dc470175190622e4f3658eaaad4298e6fab214e08110d0e9112b0` |

456 个文件分别与基线 Git blob 和工作树字节交叉核对，并通过 `read_protocol` 和 `_check_protocol_sources`。v10 固定发布 YAML 的 SHA256 另行核对。

## 首组启动预检

在普通文件复制的私有登记上调用真实 `NativeCollectionApplication.from_startup().prepare_once()`。正式发布工厂、OC1 和隔离 SQLite 均参与预检。唯一数据库作业停在 `QUEUED`，只有 `CREATED` 和 `QUEUED` 两条状态事件，租约和尝试均为 0。副本保留 1 个 claim，任务期限为 1,800 秒，尝试上限为 1，OC1 owner 已关闭。

第二组、重复 claim、重算 generation 的错来源、控制器截止与终步漂移、增加第二个释放组均被拒绝，相应启动输出目录从未创建。执行入口观测为零，未初始化物理后端。

## 物理步边界

登记网格为 1/240 秒，以下控制器截止和终步均相对各自派发步。120 步 settle 后，八动作合计到第 12,960 步。

| 动作 | 绝对派发步 | 相对控制器截止 | 相对终步 | 绝对终步 |
| --- | ---: | ---: | ---: | ---: |
| `MOVE_ABOVE` | 120 | 1,920 | 1,920 | 2,040 |
| `APPROACH` | 2,040 | 1,920 | 1,920 | 3,960 |
| `GRASP` | 3,960 | 240 | 240 | 4,200 |
| `LIFT` | 4,200 | 1,920 | 2,040 | 6,240 |
| `MOVE_TO_REGION` | 6,240 | 2,400 | 2,400 | 8,640 |
| `PLACE` | 8,640 | 1,920 | 1,920 | 10,560 |
| `RELEASE` | 10,560 | 240 | 480 | 11,040 |
| `RETREAT` | 11,040 | 1,920 | 1,920 | 12,960 |

八个窗口均接受截止相等并拒绝多 1 步。LIFT 的报告返回步包含运动截止后的 120 步内建接触保持。RELEASE 从返回到终步至少保留 240 步。首动作 1,920 步对应 8.000 秒模拟时间。墙钟作为诊断记录，1,800 秒任务时限照常生效。

## 离线读回及验证

- 权威登记在预检前后经 CLI `--verify` 得到逐字节一致的回放摘要，9 组均为 `NOT_RUN`，资格为 `UNKNOWN`，联合界为空。
- 隔离副本经 `read_native_full_horizon_group` 和 `reconstruct_native_full_horizon_registry` 读回。首组因缺少完整原件而保留 `UNKNOWN` 和空得分，其余 8 组为 `NOT_RUN`。第二组的单组读回按发布门拒绝。
- v10 发布门、Shield、执行窗口与回执读回共 52 项软件测试通过。v9/v10 离线重算与终条 POST 复用共 6 项通过。完整软件轨迹每版核对 8 个动作、17 条准入、16 次 Shield 与 27 条 tracker 时钟，使用来源、物理、几何、生命周期和完成条件 RGB-D 的软件夹具。[验证清单](validation.public.json)

真实冻结 v9 的两份协议和正式原件清单在预检前后的 SHA256 均一致。本轮正式仿真运行 0 次，冻结 v9 正式资格沿用 0/9。正式启动依赖明确授权、无 claim 的匹配登记、新输出根及真实运行环境的资源与安全前置。隔离预检证明启动排队，软件测试证明规则及读回行为。[阶段汇总](stage-summary.public.md)
