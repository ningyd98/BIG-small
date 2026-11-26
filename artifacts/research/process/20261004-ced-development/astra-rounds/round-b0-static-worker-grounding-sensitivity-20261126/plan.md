# B0 首动作的光学输入敏感度与 owner 证据读回

Astra 基线为 `89c196562e58429e6f6f3b95898b8f676d9c70b3`。本轮只读冻结原件进行计算，新增 EGL、物理、模型、控制器或网络调用均为零。改动限新轮目录的诊断、独立读回、登记和收据。

## 问题与证据

同一 STATIC 开发组有 11 份同步 RGB-D 和 2,401 个物理状态。首帧 RGB 开发选点的物体中心误差为 4.435 mm，tracker 可见顶面估计误差为 0.849 mm。生产 `prepare_worker_step` 使用 tracker 面中心 X/Y，Z 取当前面中心加上初次 calibrated TCP 高度与初始 tracker 面中心高度之差。此后才调用 `_resolved_parameters`、`bind_step_grounding` 和 `runtime.publish_grounding`。先隔离云点位误差传递，再考虑动作校准。[原始实测](../round-b0-static-worker-support-window-20261126/step-report.md)

## 执行

1. 核对指定提交、登记、源码、原 75 件收据文件。光学进程只读 RGB、深度、有效掩码、标定和原 RGB-only 种子，先封存结果。实例和物理 JSONL 由另一个进程在封存后访问。
2. 首帧第 120 步用原 tracker 和固定种子 (167,112) 得到唯一可见目标支持，目的区固定 (128,67)。枚举支持内可被生产 `normalized_1000` 还原的像素，每像素用最小合法整数坐标表示。走原 `ground_observation`、`resolve_top_grasp`、初始 tracker、`validate_grounded_colors` 及 worker 的带遮挡参数目的区几何函数。保留每个拒绝与分母。样本是构造的接口敏感度输入，包含远离中心的点。
3. 分列 planner 单像素中心/TCP 与 worker 的 X/Y/Z 输入、目的区和 support 值。报告首帧及其余十帧，若这些帧光学数据与标定逐字节相同且身份与时钟单独验证，则对等输入的纯几何数值可复用，保留每个原帧的绑定。由于当前输入无实际 owner 原合同、checkpoint 或 action lease，本轮止于可观测坐标字段。
4. 独立读取封存候选，复算坐标映射、极值见证对和固定种子。然后读取完整物理清单，从原中心、旋转、半尺寸、原支持及当前标定工具偏移生成对应参考。分估计量给出原种子、最大偏差、>10 mm 候选和最大成对跨度。报告这些都是同一独立开发组。错误帧或标定、目标与目的对调及将 planner XY 冒充 worker XY 必须被检测。
5. 只读核对 owner 顺序、时钟和缺口。当前 CLOUD_RETURN 早于首次 worker grounding publication。核对实际原合同与冻结编译的 action horizon、模拟时钟 S 与墙钟 D 的各自含义。被动窗口不填完整 owner 时域，固定命令的数学不变量不填物体参考速度。列出缺失的真实 original、checkpoint、lease、PRE、派发、返回、末态及映射。原 OPEN/CV 稳定性缺口仍单列。

## 完成条件

若只有上游单像素估计超出 1 cm，后续优先补现行 worker owner 与独立场景标定。若 worker 输入存在经独立复核的超限点，保留见证和原因，另立计划研究关联或支撑/Z 偏移。输入身份不符、光学访问真值或负控失败即停。原 1 cm 门、原生校准源、PRE 与正式分母均保留。
