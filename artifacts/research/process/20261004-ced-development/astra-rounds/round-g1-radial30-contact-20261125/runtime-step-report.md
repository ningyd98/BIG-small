# 130 mm 装配现场资格步骤报告

本报告覆盖开发构建与真实仿真零步资格。静态门复核了 3432 个历史状态和 31 个相机锚点的两种深度输入。四种新鲜顶视输入与十一项负控均达标。历史试次、四个新摆放、正式批和实机分别计数。[静态选型原件](screen-selection.public.json) · [现场资格与 100 份私有原件索引](runtime-qualification.public.json)

## 源码和装配

Astra 计划 `6a8eb89a5609a01dbbd5560c28a5379b95b72c7061522299185c7ced94fc3d9c` 的 58 个输入全部一致。89 个静态门输入逐项核对。父代的 565 个文件逐项验 SHA，父代的时间预算、两份检测源码和五个原评分文件全部复核。四份继承文件发生变更，分别为开发构建入口、试次入口、预检分派与资产提供程序。新增独立接触登记代码与 130 mm 资产，冻结树共 567 个文件。父代原件及 +15 d02 的接触失败成绩保留。[计划](plan.md) · [接触原始证据与静态门](screen-selection.public.json)

| 项目 | SHA256 |
| --- | --- |
| 115 mm 父代 | `f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892` |
| 130 mm 静态门 | `4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178` |
| 130 mm 新代 | `2d67f55f990226db232ac8c09ee454d2ae40fabc31b43156ff05f5d069dd372d` |
| 130 mm 原生资格 | `4f7a4af2ae46a6be8b9a2adcba1f2bb6dc7d085fb2ef2ad63d43e22bcf66f59b` |
| 两次独立像素读回的共同封印 | `571a8496918d1f217cd291f8508c55c42c0125b26d5789f42c16befb81067527` |
| 本轮原件索引 | `844348dd02599b359639745f74a548370646c2a74031d63e80992b2d87692313` |

ID7 中心沿物体系 +Y、ID8 沿 +X，各为 0.130 m，均高 0.03505 m。原顶视相机的标定版本为 `f33940579c533afe`。MuJoCo 原生编译与重置实读的组合体质量为 0.10126432 kg，质心为 (0.0132673921, 0.0132673921, 0.0069772508) m。惯量主值为 (0.0004242658, 0.0002560382, 0.0002373030) kg·m²。实读轴向、惯量、几何与各码装配登记均封入清单。独立盲读延用原评分器，逐码使用 130 mm 独立刚体变换。[资产、注册、相机与环境记录](runtime-qualification.public.json)

## 原生零步资格

在原历史资格摆放和原 seed 重新创建四个独立作业。每个作业均通过当前 lease、反馈、注册和目标检查，结束时正常释放。正例三次各通过 12 项，遮挡例通过 10 项。共 0 积分步、0 运动命令。全遮挡例原控制器发出一次原地保持。232 项运行时导入逐项匹配隔离源清单。[每次实帧与作业凭据](runtime-qualification.public.json)

| 顶视输入 | 实读可用 ID | 选中 | 控制结果 |
| --- | --- | --- | --- |
| 两码可见 | 7、8 | 7 | 当前测量通过 |
| 仅 ID7 | 7 | 7 | 当前测量通过 |
| 仅 ID8 | 8 | 8 | 当前测量通过 |
| 全遮挡 | 空 | 空 | 反馈拒绝，原地保持一次 |

十一项负控覆盖双码冲突、重复 ID、缺深度、无码、陈旧帧、未知 ID、错资产、错标定、错场景、错来源和错刚体变换。每项都保存了源包、测试包和原生拒绝结果，均无目标和运动。两次冷启动盲读各读 4 帧，逐帧文件、帧号、校验和与选择结果一致。旧正式 919 份原件及 8 项原有 claim 已核对。[封印与逐包 SHA](runtime-qualification.public.json)

## 操作记录

以下命令从该研发工作树运行。签发的 `--gate` 固定为本轮 130 mm 静态门；父代软件与时间预算使用构建记录核验。

```bash
PY=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python
R=artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125
S=4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178
G=2d67f55f990226db232ac8c09ee454d2ae40fabc31b43156ff05f5d069dd372d
export MUJOCO_GL=egl
"$PY" -B -m scripts.graduation.g1_visibility_trials prepare --radial-contact "$S"
"$PY" -B -m scripts.graduation.g1_visibility_trials preflight "$G"
"$PY" -B -m scripts.graduation.g1_visibility_trials issue-training "$G" train-radial30-contact-d02-01 d02 --gate "$R/screen-selection.public.json" --gate-sha "$S"
```

前两条由资格负责人执行。两历史单槽由总协调人单独调度。d01 预登记名为 `train-radial30-contact-d01-01`，只允许分组 `d01`，签发取同代 d02 的真实联合评分、两份独立读回及安全接触证据。跨代旧资格和错误静态门均被拒绝。后续四个开发摆放还需同代真实八动作、双指、抬升、放置、两历史危险段及安全结果；本报告的资格阶段真实开发试次、四槽、正式与实机计数均为 0。

私有验证目录为 `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/g1-visibility-pose-repair-20261124.QGkYvI85/runtime`。下表记录两次正常入口的命令与输出。两次命令均正常退出。

| 操作 | 命令 JSON | stdout | stderr |
| --- | --- | --- | --- |
| `prepare` | `89b995cf2bef700eeda04aa1a349e4cc3661e0ac11ff170ce0254e6119a61f82` | `5319cb861f5f64d30b3b04542e46967634068952787b251147a8519c618b7502` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `preflight` | `aa11970e73653739e8174c9a8720863ca1ce2a3510504d613397b025573c5487` | `e881ebb23e944cb1c4db9ec6ce8e1d7dfefffeedc813b0b34e6b2c926e1108c8` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

私有复核脚本 `contact30-runtime-audit.py` 的 SHA256 为 `dd39cecdb179f18e0ca16c11f2ea4b841d95db61821c312c374748f1e1133b8f`。它在隔离源码目录对原始租约、四个 RGB-D 包、十一组拒绝、真实质量和两次像素读回逐项核对。

## 签发后的采集拒绝

总协调人使用新静态门签出 d02 单槽，批分配 SHA256 为 `342b3f33a974f3ca29b8d7af45f66a4fa6411414475da1ddea9fd0b81ccdc731`。首次 `capture` 在冻结入口第 1337 行把本轮静态门传给旧离线软件门验证器。两个 schema 不同，验证器抛出 `ValueError`。堆栈在第 1359 行的设备上下文及其后的 `before_start` 预留动作之前终止。实际目录中只有批分配、单槽分配、门副本和来源清单，共四个文件。此次命令对应 0 个 attempt、0 个物理作业、0 个帧包、0 步和 0 条运动命令。[拒绝原件索引](capture-rejection-before-reservation.public.json) · [脱敏堆栈](capture-rejection-trace.redacted.txt)

采集接入缺口已单独上报 Astra。父代软件入口、本代 4/11 资格、冻结分配和原失败合并日志保留原始字节。
