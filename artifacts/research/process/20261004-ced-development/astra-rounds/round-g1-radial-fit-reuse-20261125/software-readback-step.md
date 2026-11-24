# 逐帧拟合复用的独立软件读回

与原生 36f9658b 对照，候选 cefc2388 的 20 组逐字段核对均为零差。778 个历史原帧和 335 个 d02 原帧分别经过两次独立冷启动完整读回；115 mm 装配的 22 个静态姿态在两种深度输入下分别双读。每对原始输出逐字节相同。原生消费者记录核对 332 个观察、315 个进入 servo 与 Shield 的实际目标，以及 313 个控制器完成记录。三个批次各有一张终帧只进入离线评分。[完整核对](semantic-equivalence.public.json) · [各独立进程签名](full-blind-seals.public.json)

| 原生 d02 数据集 | 原帧 | 在线观察 | servo 与 Shield 目标 | 控制器完成 |
| --- | ---: | ---: | ---: | ---: |
| train-current-grid-01 | 75 | 74 | 70 | 69 |
| train-feedback-deadline-01 | 130 | 129 | 122 | 122 |
| train-radial15-01 | 130 | 129 | 123 | 122 |

8 个历史首拒均已恢复，4 个正控成立，16 个负控全部拒绝。两枚可读标记的独立抓取点相差 203.548 mm 时仍触发冲突拒绝。第 1088 步的旧板原图继续拒绝镜像 28，外移板原图仍接受 ID7。另用完全相同的外移板像素往返切换 115 和 100 mm 登记，两侧抓取点相差 15.000 mm，恢复原登记后完整输出逐字段恢复。[正负控](qualification/replay-controls.public.json) · [装配切换原始返回](candidate-full-context.public.json.gz)

29 项拟合、边界与读回测试通过。针对原生第 1080 和 1088 步的 272 和 244 个实际拟合，候选的解、秩和奇异值与原 NumPy 求解逐字节一致。独立读回按原图、原拟合输入与两张完整观察返回的哈希完成交叉核对。[回归测试](software-regressions.public.json) · [实际拟合证据](actual-lapack-equivalence.public.json)

168 个来源文件全部通过 SHA256 复核。离线软件放行 SHA 为 `81bf8af00c237912b963b73263041ed7340ed2f921bba5545fa59213f0586ea8`。原生时限与后续作业由各自的运行记录判定。[软件放行](replay-release.public.json)

