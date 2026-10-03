独立最终证据复审，2026-10-03。

**结论：未发现阻止 T3 在限定范围内 DONE 的 blocker。** 冻结探针可以声明当前校准场景族中的双图视觉定位、RGB-D 空间规划与拒绝门禁通过；不能声明泛化评测全部通过、G1 已达成或机器人抓放执行成功。两批开发验证合计为 **29/32**，所有失败均保留。

本次复审只读取源码和既有产物、运行 CPU 重构检查；没有请求模型、运行 GPU、改生产源码、改资产或重跑场景。除本文件外未写入产物。人工查看的场景图只有第一批 positive-08；其余场景采用落盘请求、响应、校验和及计数复核，没有宣称逐图人工核验。

冻结证据见 [probe-report.json](probe/probe-report.json)、[model-frozen.json](probe/model-frozen.json) 与 [model-frozen-evidence.json](probe/model-frozen-evidence.json)。独立调用 `verify_frozen_bundle` 返回 `True`；当前探针相关源码及资产指纹、候选配置 SHA 均匹配。对四次捕获逐次重建 `RGBDObservation` 和消息，实际文本、两图 SHA、完整消息 prompt hash、RGB/深度 SHA、观测 checksum、sidecar request evidence 全部一致。归一化点映射、落盘实例标签命中及支撑高度到 TCP 的计算也逐次复算一致。冻结快照 SHA-256 为 `a543288cf74bb6ac6e69a7d6a15ee80ad67112a602325813e204c530011bacbc`。

| 冻结探针指标 | 实际值 |
| --- | --- |
| 模型 | `qwen3-vl-candidate:4b-instruct`，4.0B，`Q4_K_M` |
| 权重 digest | `d18dda6d10491bbe92186dbc7c854623bf99f48eb75829dbe290ef0f97626107` |
| 请求协议 | 320×240 RGB + 对齐深度可视图；`normalized_1000`；`temperature=0`、`num_ctx=8192`、`num_predict=512`、`think=false` |
| 样本 | 同一 `S01_NORMAL_STATIC` 的 1 次冷启动 + 3 次热调用 |
| 双图/解析/grounded/目标命中/目的区域命中 | 各 4/4 |
| 输出目标/目的归一化点 | 四次均为 `[560,498]` / `[418,309]` |
| 对应原图像素 | 四次均为 `[179,119]` / `[133,74]` |
| 技能 | 四次均为合法 9 步：首 HOME + 必需 8 个有序技能 |
| 冷调用 wall latency | 3857.666 ms |
| 热调用 wall latency | 1483.330、1456.603、1519.680 ms |
| 热调用 p50 / p95 / mean | 1483.330 / 1516.045 / 1486.538 ms，样本仅 3 次 |
| TTFT | 未测量，`stream=false` |
| GPU | RTX 4070 Ti SUPER；每次调用均有匹配 digest 的 Ollama GPU 驻留证据 |
| 显存 | Ollama `size_vram=4236697927` bytes（4040.430 MiB）；采样整卡峰值 5740 MiB，不能当作模型独占峰值 |
| 估计对象高度 | 68.432093–71.218431 mm |
| 估计指端到支撑余量 | 14.216046–15.609215 mm，最低允许值 2 mm |
| 3×3 顶面世界 z 跨度 | 1.531363–3.002763 mm，允许上限 8 mm |

四次 RGB 和物理状态相同，深度观测不同；4/4 是同场景重复探针证据，不能计为四个独立场景。消息只含视觉提示、JSON schema、自然语言指令与两图；实例标签和真实场景参数只用于响应后的离线核验，没有进入模型请求或顶抓在线计算。

生产 planner 要求真实尺寸帧显式选择 `mujoco_upright_box_v1` 且来源为 `mujoco_camera`，否则返回 `REQUEST_MORE_OBSERVATION` / `NOT_CONFIGURED`，不产生 observed scene。该 profile 是可信调用者对当前资产与场景族的保证，不是模型标签推断或形状识别结果。资产 SHA-256 为 `182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08`。

顶抓标定只适用于在测得水平支撑上直立的刚性方块、所选可见顶面中心与当前 MJCF 夹爪朝下姿态。高度限于 0.05–0.10 m；`1e-7 m` 仅补偿 float32 表示误差。TCP 为顶面高度减去估计对象高度一半再加 0.01 m；指端在 TCP 下方 0.03 m，并要求支撑余量至少 0.002 m。无完整有效 3×3 深度、顶面不平、高度越界等情形拒绝。返回对象中心明确标为 `RGBD_GEOMETRIC_ESTIMATE_NOT_GROUND_TRUTH`。小于 64 像素的软件 fixture 兼容路径不是可冻结的校准证据。上述限制不证明任意形状、倾斜物体、任意夹具或实机执行安全。

两批开发验证见 [第一批 summary](scene-validation/summary.json) 和 [第二批 summary](scene-validation-43001/summary.json)。分别独立从 assignments 和全部 outcome 重算 summary，结果与落盘一致；两批全部 32 条请求的文本、两图 SHA 及捕获 checksum 复核通过，assignments、dataset config 和候选配置的 provenance SHA 匹配。两批之间保留各自源码指纹；第二批当前源码指纹匹配，冻结探针复核仍为 `True`。

| 开发验证 | 正例通过 | 缺失目标明确拒绝 | 总通过 | all_cases_pass |
| --- | --- | --- | --- | --- |
| 第一批：正例 seed 41001–41012；负例 42001–42004 | 12/12 | 3/4 | 15/16 | false |
| 第二批：正例 seed 43001–43012；负例 44001–44004 | 11/12 | 3/4 | 14/16 | false |
| 合计 | 23/24（95.833%） | 6/8（75%） | 29/32（90.625%） | false |

两批共有 32 个不同 scene hash 和 RGB hash；完成 32/32，error、missing、duplicate、unknown 均为 0。每例一次调用，没有重试剔除或缩小分母。双图传输 32/32；正例的解析为规划合同、grounded、目标/目的命中、校准偏移等门禁各 23/24。此为预登记的 nominal development validation，`held_out_test=false`，不是冻结 gate。颜色、对象尺寸、位置、相机、照明和干扰物仅覆盖该名义分布；深度噪声和无效比例均为 0，不能外推至更广场景。

必须保留的三例失败如下：

- 第一批 `negative_absent-04` / seed 42004：模型以 0.98 置信度幻觉出 purple block，输出 `[540,927]`，映射 `[172,222]`，离线标签为机器人 `hand`。测得局部 relief 为 0.009847 m，被 0.01 m 可见凸起门禁拦截；`observed_scene_present=false`、合同 0 步。它不是模型主动拒绝，不能计为负例通过。
- 第二批 `negative_absent-01` / seed 44001：模型以 0.95 置信度幻觉出 purple block，输出 `[570,924]`，映射 `[182,221]`；局部 relief 为 0.009755 m，同样被拦截，无 observed scene、合同 0 步。两批 8 个负例最终均无执行规划，但只有 6 个达到模型明确拒绝标准；不能据此宣称未来幻觉都会被几何门禁拦住。
- 第二批 `positive-04` / seed 43004：返回有效 JSON、置信度 0、双 null 点和空技能，错误地拒绝正例，理由是不能确定绿色放置区域。无基础设施错误、无 observed scene、合同 0 步；该失败保留在 24 个正例分母中。

第一批 `positive-08` 的离线质心诊断另有非阻塞局限。其报告目标可见像素均值偏差为 9.700199 px、可见表面世界点均值偏差为 46.650227 mm。直接读取落盘 `instance_geom_ids.i32` 后，`object_geom`（ID 11）实际含两个断开的连通分量：234 px 主分量 bbox `[183,105,200,117]`，以及 32 px 分量 bbox `[117,151,132,167]`。只对此例查看 RGB，可确认主分量在红块处，而第二分量位于黄色干扰物边缘；碎片成因未在本复审中定位。模型原图点 `[192,111]` 落在红块主分量内，因此本例已有目标命中结论不受影响，但汇总全部 ID 11 像素得到的质心被异处分量影响。该离线均值距离不能解释成对象中心误差、抓取精度或物理执行误差，也没有用于在线控制或验收门禁。本次没有修正或筛除该诊断数据。

最终可接受声明为：当前冻结小模型在指定资产与直立方块标定范围内，固定探针 4/4 通过且冻结链条可复核；附加开发验证明确记录 29/32 与三例失败。无机器人动作执行证据、无 held-out 泛化结论、无 G1 达成声明。
