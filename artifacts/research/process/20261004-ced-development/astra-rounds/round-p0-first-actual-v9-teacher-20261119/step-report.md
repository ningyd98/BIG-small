# v9 教师唯一首组的真实尝试

## 实际运行

2026-11-19 23:28:54–23:34:48 CST，冻结生产 CLI 对 `native-p0-20261119-0001`（种子 11919001）取得唯一 claim 并运行唯一一次 worker attempt。核对 487 个冻结输入，运行前后字节一致，187 个项目实际导入与冻结清单相同。GPU/EGL 按共享锁独占，前置卷余量 58.88 GB，满足原 32 GiB。生产角色明示零模型请求和空 provider，执行的网络审计为零，未使用物理硬件。

实际 PRE 允许。MOVE_ABOVE 在物理步 120 dispatch，860 返回成功，2040 完成保持并采集 POST。首动作执行和保持覆盖原 1920 个模拟步，其中控制器 740 步、保持 1180 步。生产 POST 的唯一 Shield 拒绝为 `STEP_TIMEOUT`，原单调钟 332,828.674 ms，限额 8,000 ms。POST 原件里的必要动作语义条件为 PASS，当前 v2 预览为 `DERIVED`，登记目标区为 `FULL_NOMINAL`。旧顶面可视性仍为 UNKNOWN，原因 `visible_top_interior_unavailable`。本次首个准入阻断为墙钟超时。

生产 worker 终态为 `BLOCKED_BY_ENV`，collection 为 `COLLECTION_PARTIAL`。控制器返回动作 1/8，经过完整准入的动作 0/8。失败快照采于急停之前，随后原件记录已接受的急停命令 151，原运行止于物理步 2040。启动源、租约、原件写出、owner/相机/recorder/后端关闭及最终生命周期收据已保留。实际 2,040 个物理步、3,373 个分配采集和 8,789 个完整渲染 pass，原件写出 2,054,839,447 B，RSS 峰值 602,570,752 B。worker 核对 lease 已释放。上层命令会话在运行中失联，原始 stderr 保留未捕获生产异常，实际外层退出数值不可恢复。终态后检查 OS 进程已退出且 EGL 锁可用。采样资源日志保留其开始至会话失联的原始范围。

## 独立完整组读回

以同一冻结源码运行正常 `--verify`，23:35:15–23:38:00 CST，退出 0。读回重建 3,373/3,373 个分配帧，核出 2,040 个总物理步。首组的 source、horizon、geometry complete 均为 false，完整动作列表为空，组分和联合误差界为空。中间至少 12 帧（acquisition-1015 至 1026）出现 `known_marker_not_observed`，reader 仅公开该类错误的前 12 条。其余 8 组仍为 `NOT_RUN`，正式验收 0/9，资格 `UNKNOWN`。独立物理判定 `LIFT_BELOW_THRESHOLD`，对应尚未进入抬升的部分轨迹。此次 claim 已消费，未重试或扩组。

## 原件

本地忽略目录为 `experiments/results/phase9/p0-first-teacher-20261119/formal-v9-first-20261119/`。生产用协议 SHA256 `6ac30e905b25b1bef8e137e00249affc0b1e87c97624a2a585b5dc33c9d6a40f`。终态 SHA256 `5fcdefecf40468bdd347d3da826c6273b57b277e52002d643e2d406a33a428af`，原件 inventory SHA256 `9e07118109e49852dadb8f34ede3254d975d0d97028fae1195a25579865e8849`，独立分组结果 SHA256 `8554b36513606a525be8a5ac2ea9139f29be22727385b82e401d6e1a2ba6741a`。 [公开结果](result.json) · [离线墙钟与中间帧读回](../round-p0-formal-teacher-offline-timing-20261119/step-report.md)
