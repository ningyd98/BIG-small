# 径向装配原生时限专项软件读回

候选与父代在 778 张历史帧、三代 d02 的 335 张原帧及 +15 mm 外移装配两种深度的 44 张静态帧上，当前 RGB-D 观察器的完整返回逐字段相同。两个独立进程先封存历史结果，再联结物理真值。原臂、双码臂的已选顶心误差 P90 分别为 2.418 和 2.207 mm，八个历史首拒全部恢复。[软件放行](replay-release.public.json) · [全字段读回](semantic-equivalence.public.json) · [历史盲读签名](qualification/replay-blind-seal.public.json)

| d02 旧批次 | 原图 | 在线观察记录 | servo 与 Shield 接受目标 | 原控制器完成记录 |
| --- | ---: | ---: | ---: | ---: |
| train-current-grid-01 | 75 | 74 | 70 | 69 |
| train-feedback-deadline-01 | 130 | 129 | 122 | 122 |
| train-radial15-01 | 130 | 129 | 123 | 122 |

三个批次各有一张终帧仅用于离线评分。所有实际下发目标与依据新观察重新计算的目标相同。100 mm 旧板在第 1088 步仍因读到 7 和镜像 28 拒绝，115 mm 板在该步独立读到有效 ID7。正常深度和配对噪声深度在 22 个静态姿态的逐码顶心或抓取点最大误差分别为 3.539 和 3.727 mm。16 个负控全部拒绝，4 个正控全部通过，其中两枚各自有效但目标相差 203.548 mm 的负控保留了双侧位姿和冲突拒因。[控制见证](qualification/replay-controls.public.json) · [逐项差异](semantics-differences.public.json.gz)

独立读回冻结父代和候选各 566 个文件，唯一变更为当前帧格网模块。七个软件测试通过。软件 release 的 110 个来源文件 SHA 全部复核，release SHA 为 `284c149700f70b050fe92ddfc1d222fd105f229993becf0b8af1a78bc6cd2120`。本报告记录离线软件与静态几何资格。原生时限和新动态作业由各自的证据判定。[两代完整源码清单](source-snapshot.public.json.gz) · [逐帧来源](software-local-raw-bindings.public.json)

