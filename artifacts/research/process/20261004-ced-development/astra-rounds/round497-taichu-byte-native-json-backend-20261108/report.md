# Taichu FP8 双图适配阶段结果（2026-11-09）

本轮完成了研究脚本中的字节级 JSON 约束适配，以及同一 S01 捕获帧的 8 次真实 GPU 对照。严格格式改善明确；空间定位没有达标，暂不具备替换项目默认模型的依据。未进行产品接入、控制器动作或正式研究验收，也未据此重排全部候选模型。

## 实测结果

| 项目 | 自由生成 FREE | 约束生成 JSON |
|---|---:|---:|
| 完成 / 计划 | 4 / 4 | 4 / 4 |
| 严格 JSON（原 VisualDecision） | 0 / 4 | 4 / 4 |
| 暖态端到端中位数（各去掉本模式首条，n=3） | 12.50363 秒 | 10.84884 秒 |
| 生成 tokens（每次） | 176 | 134 |
| 目标 mask 命中 | 不可评分：原输出带围栏 | 0 / 4 |
| 放置区域 mask 命中 | 不可评分：原输出带围栏 | 0 / 4 |
| 达到 512-token 上限 | 0 / 4 | 0 / 4 |

暖态端到端中位数减少约 13.2%，同时输出长度减少；这不是纯解码吞吐提升的证明。约束回调累计耗时中位数 0.14957 秒/请求。首个模式请求分别为 13.00262、11.05611 秒。模型加载 2.13992 秒，复用了此前 JIT/权重页缓存；没有实测 TTFT。

JSON 组四次贪心输出相同：归一化目标 [500,400]、区域 [300,200]，按既有转换映射为 320×240 图上的 [160,96]、[96,48]。离线实例图均为 table，期望分别为 object_geom 与 target_region_geom。`grounded=true` 仅表示现有解析/深度回投链返回，并不能代表语义定位正确。自由组未剥围栏、修 JSON 或以宽松解析代替原校验。四次重复同一静态帧，不能当作四个独立场景；置信度 0.8 也不能用于证明准确性。

## 固定条件与适配范围

官方 FP8 权重、revision bc77dd791da3c27de68c96a5eb44ced02b83b8a7，已记录权重 SHA256 c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a。本轮没有重新全量哈希 12.67GB 权重；加载前 stat 与原冻结记录一致。RTX 4070 Ti SUPER 16GB、Torch 2.10.0+cu128、Transformers 5.22.2、FLA 0.6。每次生成后 248 个 FP8 层保持原量化状态；BF16 视觉 patch 层保留。SDPA，vision flash-attn 关闭，causal-conv1d 仍为原 Torch 参考路径。

单次模型加载，交错顺序 FREE/JSON/JSON/FREE/FREE/JSON/JSON/FREE。原两张 RGB/depth 可视化图、system/user、1030 个输入 IDs 及视觉 tensor 摘要冻结一致。短作用域 `enable_thinking=False` 产生空 think 区间后恢复原模板方法；固定 seed=0、greedy、max_new_tokens=512、num_beams=1、use_cache=True。无额外模型预热、跨请求 KV 或候选重试。没有 RGB-only/移除深度的消融，不能证明模型因果使用了深度图。

原 LM Format Enforcer 路线在 Unicode/合法字符串前缀门槛未全部通过，未进入 GPU。保留全部失败后，依据 Astra R497–R504 使用隔离叠加环境 llguidance 1.9.1；原运行环境包未被替换。新的 byte-native 适配器只对原 logits 做允许集合屏蔽，不强制注入输出、不修改权重/原 schema/原 tokenizer，不做输出修复。每请求独立状态，仅消费生成后缀，核对完整输入前缀并保存 mask 与选择 token 的一致性证据。原三个 EOS [248044,248040,248046] 保留，在 JSON 未完成时全部禁止，完成时须原生 mask 已允许才可结束。

约束有明确边界：固定属性顺序、不允许外部空白；D28 token ID 子集屏蔽（1 个空字节 sentinel、27 个 added-tag 分类差异），27 个字符串另有普通 ASCII IDs 的可表达见证。不能声称任意合法 token 序列或所有 Unicode 语言与原 schema 完全等价。NFC 相关测试区分原 HF canonical IDs 与仅测试副本 normalizer=None 的原始 UTF-8 BPE 见证，生产 tokenizer 未改。

最终 CPU 合约 `cpu-contract-r504.json` 为 PASS：21 个用例（6 合法、11 非法、4 边界），合法样例同时验证 canonical 和原始字节见证，另有 27 个 added-tag ASCII 见证；重复前缀、请求隔离及三个 EOS 策略通过。此前 R503 的阶段时间窗到期保留为原始失败，不能用最终 PASS 覆盖历史。CPU 合约不替代真实模型/空间/实机验收。

## 多场景阶段

R501 已冻结 16 个旧 DEV 捕获（12 正例、4 缺目标），保留其原 v1 来源，完成官方 processor 的 CPU 预检、消息/图像/IDs/tensor SHA；它们不是 held-out 数据。B 脚本与 scorer 仅为语法检查过的未执行草稿。

授权前，距离 B 截止仅剩 198.329 秒，少于按 A 实测估计的 240.122 秒。依 R501 时间门槛记为 **B_NOT_RUN_TIME**，没有写授权文件、没有 B 模型生成，也没有重载模型。原驻留进程在 16:06:10 UTC 正常退出，rc=0。原结果的 `conditional_b_gate=WAITING_PROVENANCE_PLAN_TIMEOUT_NO_SECOND_LOAD` 是原程序状态原样保留；具体预算门槛见 `b-not-run-time.json`，不据该字符串推断没有计划。16 场景准确率、缺目标拒答率、3D 误差及 P90 均未测，不计算为零或通过。

## 后续选择

保留现有默认方案，Taichu 继续作为研究候选。下一轮应先给多场景验证预留完整运行窗口，沿冻结协议评估格式、目标/区域 mask、缺目标拒答，再依据结果决定是否调整视觉输入与提示；任何新问题先由 Astra 制定新轮计划。当前唯一可交付的正向结论是该配置下格式兼容性改善。位置与深度使用、泛化、抓取控制和完整模型选型尚未验证。

## 证据与交付边界

主证据：`run-stage-a.json`（8 次实际调用、248 FP8、kernel counters、正常退出）、`score-stage-a.json`（原严格解析与离线 mask）、`comparison.json`、`cpu-contract-r504.json`、`tokenization-proof.json`、R501 `b-not-run-time.json`。原始失败及每轮真实 Astra 计划在 R491–R504，步骤归并见 `phase-summary.md`。

实际输出 IDs、未经修复的响应、mask trace、GPU 采样、全部 CPU case 原生消息，以及权重、环境和 JIT 留在本地 CACHE；Git 仅包含显式交付的适配脚本、计划、派生报告、CPU 合约/故障证据与 SHA 清单。完整 GPU stdout/stderr 亦作为原始运行日志留本地并列入哈希清单。此提交不是完整远端复现包。源输入与原始字节未为通过校验而清理。共享产品修改不在本轮交付范围。
