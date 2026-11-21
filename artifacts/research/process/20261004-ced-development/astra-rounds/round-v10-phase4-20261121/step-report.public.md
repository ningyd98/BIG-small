# Phase 4 v2 准入与 SafetyShield 离线回放

以 `c4f9d79c` 为基线，在 `research/harness-candidate-v10-phase2-20261121` 实施。主计划和归档来源、时钟域、租约续期三份补充计划均由 `gpt-6.2-astra` 制定。计划输入及交付源码的 SHA256 均已核对。[主计划](plan.md) · [归档来源](../round-v10-phase4-historical-sources-20261121/plan.md) · [时钟域](../round-v10-phase4-clock-domains-20261121/plan.md) · [租约续期](../round-v10-phase4-lease-renewal-20261121/plan.md)

## 原始失败与修改

- `c4f9d79c` 的完整 v9 软件轨迹在 `registered_pose_evaluated_at` 触发 `KeyError`。完整 v9/v10 读取器按 v2 重建 B/E 登记、每步绑定、采集反馈、tracker 时钟、回执、条件和白名单。末条准入沿用第八个 POST 的原 Shield 调用，并独立校验自身的观测和决策。
- Shield 重算使用原配方和记录的时间。v9 按单调墙钟判步骤超时，现版 context 同时核对绝对物理步。已核验的早期 v9 context 保留原字段形状。v10 从该动作的派发步计算相对物理步。POST 从同一步 PRE context 更新生产者实际刷新的字段。
- 归档 v9 使用当前读取器重建固定协议，同时从显式 `source_root` 重新枚举并核验每项原来源。`read_native_full_horizon_group` 和 `reconstruct_native_full_horizon_registry` 均接受该参数。原冻结协议与错误源码快照配对会被拒绝。
- 两版软件正控先复现了原始执行区间和 OC1 相互比较造成的误拒。回执现在在各自时钟域检查顺序，另外保留 UTC 包络。两版也复现了旧租约快照到期造成的误拒。登记交接仍使用原租约限期，后续采集与绑定核对各自保存的同一租约有效期。

## 开发验证

| 检查 | 基线 | Phase 4 |
| --- | --- | --- |
| v9/v10 完整回放与发布门聚焦测试 | 完整回放复现错读字段 | 70 项通过 |
| v9 兼容及相关回归 | 223 通过，52 失败 | 233 通过，52 失败，包含 10 项新增发布门测试 |
| 原始记录与时钟回归 | 165 通过，2 失败 | 165 通过，2 失败 |
| 两个修改模块的 mypy | 45 项诊断 | 41 项既有诊断，新增 0 项 |
| Ruff、py_compile、diff 检查 | — | 通过 |

软件正控分别经公开 group 入口重放 8 个动作、17 条准入、16 次 Shield 与 27 条 tracker 时钟。准入前的来源、物理、几何与准入后的物理结果、指标、生命周期由隔离的软件边界夹具提供。固定合同的最后两项显式条件使用可重放的软件 RGB-D 事实。另用原颜色 tracker 验证缺少显式稳定性证据会在第八个 POST 停止。

第一步 v9 墙钟等于 8.000 秒时通过，超限负控触发重算差异。v10 在墙钟 8.500 秒时仍按相对第 1,920 步通过。重封后的缺字段、错准入及回执版本、错步数、伪造 Shield 输出、错误 TERMINAL 复用、单域逆序、原租约到期和续期时尝试号变化均被拒绝。

52 项旧准入夹具在基线和本轮的失败节点均一致，异常均为 `teacher checkpoint database identity changed`。时钟回归剩余两个节点也与基线一致，错误来自 observer publication。基线临时树补入仓库中同一份冻结软件夹具后，原件 codec 测试单独复验通过。保留的测试节点、诊断和原始日志指纹见验证清单。[验证清单](validation.public.json)

## 冻结原件与正式状态

两套冻结 v9 协议各自核验了 454 个来源文件。匹配正式首组原件的清单又校验了 16,885 个原件。对原有首动作执行只读组件复核，PRE 精确重算为 `ALLOW`，POST 精确重算为 `STOP`，Shield 记为 `STEP_TIMEOUT`。原记录只有一个动作，完整组门保留其失败。两份协议和正式原件清单核对前后的 SHA256 一致。

本轮正式仿真运行 0 次。冻结 v9 的正式资格结果沿用 0/9。软件回放、冻结首动作复核和正式资格分别登记。[阶段汇总](stage-summary.public.md)
