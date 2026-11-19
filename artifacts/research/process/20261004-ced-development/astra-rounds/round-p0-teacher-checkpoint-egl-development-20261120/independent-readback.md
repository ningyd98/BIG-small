# 教师 checkpoint 真实 EGL 开发短窗独立读回

唯一开发组 `native-dev-checkpoint-20261120-0001`（种子 11920067）于 2026 年 11 月 20 日 00:28:44–00:29:03 CST 运行。正常开发 CLI 因原保护退出 1。独立两次读回均退出 0，原始 stdout 逐字节一致，SHA256 为 `20d33461e7adf6d6770fd3f34a1297d62fb722142c1df3d814441dae96f3dcc8`。正常正式 `--verify` 对同一开发协议退出 1，在输出目录建立前拒绝。

## 原授权与实际停止

MOVE_ABOVE 的原 PRE Shield 允许。实际动作从物理步 120 到 219，8 秒窗内覆盖 99/1,920 个原动作步。总物理步包括 settle 共 219。独立按原库存核验 1,228 个文件、174,716,670 B，重建全部 242 个分配帧及 705 个渲染 pass。逐步采集 219 帧，显式动作边界 2 帧，隐式缓存 21 帧。原件无 observer、audit 或悬挂 operation 错误。

| 事件 | 相对原 8 秒截止 |
| --- | ---: |
| 最后允许的 CAPTURE BEFORE，operation 700，步 219 | −1.957341 ms |
| CAPTURE AFTER 触发唯一 `_CheckpointDiagnosticDeadline`，operation 701，同一步 | +29.226082 ms |
| 原 guard 退出 | +35.043479 ms |
| 采集、recorder 与后端清退 | +419.171966 ms |

operation 701 在截止前获准，所记录的原始帧是 acquisition-242。此在途采集的 raw 记录包络跨入截止后的约 1.259–10.930 ms。拒绝后保留 hold 与已接受的急停 22 号命令和其内部 CONTROL，均位于物理步 219。急停前快照为 false，原命令从步 220 起生效，原件没有步 220 或关机后的物理状态。owner 与租约都完成清退。

## SQLite、冻结来源和资格

独立 reader 将静止的原 runtime.db 复制到私有目录查询，原数据库 SHA256 前后相同，且现场无 WAL/SHM 文件。实际表中 job、唯一 attempt、唯一有效 worker lease 及 `RUNNING`、`BLOCKED_BY_ENV`、释放记录相符。活动 owner join 核到 2,290 项允许与 1 项拒绝，动作窗内 1,088 项有单调钟及原 guard 序号，独立确认最后许可和原租约归属。

实际 recorder 的 SQLite 计数原件记录 `UTC_LEGACY_VETO`、2,795 次成功只读快照。动作窗内调用 1,331 次，测得 context 进入至退出合计 1.345148 秒，含每次两次计时读取。独立核验使用原 SQLite、owner 和 guard 逐事件证据。耗时是生产记录的合计，逐 SQL 语句及具体阶段的净时仍未知。

冻结来源 456 个文件，登记 recipe 455 个来源，其余 92 个既有受保护输入按原摘要核对。运行后的实际导入验证 618 个文件模块，其中 188 个为项目模块。本次没有付费模型、云请求、网络尝试或真机。实验为开发短窗，正式资格仍为 `UNKNOWN`，正式组积分为 0，联合界为空。

冻结运行原件保存在 `experiments/results/phase9/p0-first-teacher-20261119/checkpoint-egl-development-20261120/`，独立读回原回执保存在 `experiments/results/phase9/p0-teacher-checkpoint-independent-reader-20261120/`。 [公开小回执](independent-readback.json)
