# T7 大模型候选复测与独立比较

已按指定顺序筛选 Qwen3-VL 8B、Llama-3.2-Vision 11B、InternVL2.5 8B，并统一使用 `normalized_1000`。Qwen 8B 仍未达到可靠性门槛：新独立集正常任务成功0/40（0.0%），缺失目标误操作11/20（55.0%）。Llama 因指定后端与双图契约不兼容而未测性能，InternVL 的实际筛选不合格。当前结果不支持替换默认模型，也不提升正式 G1 或现有任务验收状态。

原 T7 配置已经使用这一坐标系，本轮没有把坐标切换当作新的独立改进。预先登记的质量门槛是目标缺失零动作、定位 P90≤10 mm 和正常任务成功率≥90%。

## 新独立测试结果

新冻结 60 个场景，40 个目标存在、20 个要求不存在的紫色方块。两套通过固定入口探测的配置同场景配对，共 120 个任务，全部保留。定位 P90 只对首轮回复命中真实目标且深度有效的定位计算，并同时给出覆盖数；它是预测可见顶面点到独立稳定刚性方块顶面几何中心的三维距离。缺失目标误操作率按实际执行≥1 个物理技能计数，拒答和重观测后的动作均计入。

| 配置 | 缺失目标误操作率 | 定位 P90 与有效覆盖 | 正常任务成功率 | 端到端延迟 P95 | 每任务费用 |
|---|---|---|---|---|---|
| Qwen3-VL 4B Q4_K_M 基线 | 16/20（80.0%） | 10.31 mm；40/40 | 4/40（10.0%） | 10.64 秒 | 0 元；总费用未测 |
| Qwen3-VL 8B Instruct Q8_0 | 11/20（55.0%） | 33.52 mm；28/40 | 0/40（0.0%） | 10.42 秒 | 0 元；总费用未测 |
| InternVL2.5 8B BNB INT8 | 筛选不合格，未进入闭环独立集 | 未测 | 未测 | 未测 | 未测 |
| Llama-3.2-Vision 11B Q5_K_M | 兼容性阻塞，未测 | 未测 | 未测 | 未测 | 未测 |

本地 API 账单费用均为 0；用户确认没有机器计费单价，含电费与折旧的总费用未测。请求数、输入输出 token 数和推理时间见[完整统计](comparison-summary.json)，不能据此宣称零总费用。延迟含失败任务；失败任务可能快速停止，不代表完成任务更快。正常失败按 120 秒惩罚后的 P95，原 4B 为120.00秒，8B 为120.00秒。推理调用延迟、误完成数及置信区间如下。

| 配置 | 误操作率 Wilson 95% 区间 | 正常成功率 Wilson 95% 区间 | 全60任务成功率 | 误完成数 | 模型调用合计延迟 P95 |
|---|---|---|---|---|---|
| Qwen3-VL 4B Q4_K_M 基线 | 58.4%–91.9% | 4.0%–23.1% | 4/60（6.7%） | 3 | 3.95 秒 |
| Qwen3-VL 8B Instruct Q8_0 | 34.2%–74.2% | 0.0%–8.8% | 0/60（0.0%） | 1 | 8.17 秒 |

分位数使用 NumPy linear 口径；配对场景分层 bootstrap 为10,000次探索性估计，差值方向均为 Qwen 8B 减原 4B。

| 指标 | 差值点估计 | 配对 bootstrap 95% 区间 |
|---|---|---|
| 缺失目标误操作率 | -25.00 百分点 | -55.00 至 +10.00 百分点 |
| 正常任务成功率 | -10.00 百分点 | -20.00 至 -2.50 百分点 |
| 条件定位 P90 | +23.21 mm | +15.20 至 +30.15 mm |
| 端到端延迟 P95 | -0.22 秒 | -2.08 至 +2.41 秒 |

未进行多重比较校正，区间跨零时不能断言存在稳定改善。定位覆盖不同的条件 P90 不应被解释为全体任务的定位精度。任务成功须同时满足在线完成、独立物理成功以及目标确实存在。

## 候选筛选及兼容性

Qwen3-VL 8B Q8_0 固定 S01 的1冷3热探测4/4通过，真实双图、完整技能契约、目标与目的区域命中、CUDA及权重身份均已核对；冷请求8.59秒，热请求2.41–2.84秒。峰值显存11,541 MiB，16GB显卡足够，因此没有触发Q6_K资源回退。16场景开发筛选通过8/12目标存在及2/4目标缺失；T7闭环20例正常成功2/12，目标缺失误操作1/4，仍未达到可靠性目标。[探测证据](qwen8-probe/probe-report.json)、[场景筛选](qwen8-scene-screen/summary.json)、[20例复测](qwen8-closed20/summary.json)、[独立物理复核](qwen8-closed20-validation.json)均保留。

Llama-3.2-Vision 11B Q5_K_M 记录为兼容性阻塞，未下载完整权重或测量模型性能。当前 Ollama 0.35.1 所绑定的 llama.cpp b11232 不识别 `mllama`；用明确无权重的架构能力探针实际得到 `unknown model architecture: 'mllama'`，这不属于 Llama 推理或质量测量。旧版 v0.6.8 又显式限制 mllama 每条消息只接受一张图，无法直接保留现有同消息 RGB+depth 契约。官方标签不提供所请求的 Q5_K_M；未用 Q4 或改变图像输入代替。见[兼容性记录](llama11-compatibility.json)与[本机后端能力探针](llama11-backend-architecture-probe.json)。[官方架构源码](https://github.com/ggml-org/llama.cpp/blob/b11232/src/llama-arch.cpp)、[旧版单图限制](https://github.com/ollama/ollama/blob/v0.6.8/server/prompt.go)、[官方标签](https://ollama.com/library/llama3.2-vision/tags)支持这一范围内的判断。

InternVL2.5 8B 使用官方固定权重、Transformers 4.48.3 / Torch 2.6.0 CUDA12.4 / BitsAndBytes 0.45.2，实际加载258个8位线性模块。固定 S01 四次探测全部未通过入口；开发场景筛选通过0/12目标存在及0/4目标缺失。固定探测目标和放置区均0/4命中，英文场景重复reason并耗尽512 token、未闭合JSON，未通过定位与输出契约入口；按候选协议不进入T7闭环或独立任务比较。最初未约束版本20次回复全部带Markdown围栏；联合schema解码适配曾失败，均已归档。最终JSON object模式仅约束语法，未修正坐标、标签或置信度，且在任何独立测试前固定。[未约束结果](internvl8-unconstrained-scene-screen/summary.json)、[接口失败结果](internvl8-json-interface-failed-screen/summary.json)与[变更登记](candidate-protocol-amendment-json.json)保留。运行元数据、原始双图 SHA、原始模型输出和逐次计时保存在[原生运行证据](internvl8-runtime.json)、[筛选结果](internvl8-scene-screen/summary.json)、[闭环未运行记录](internvl8-closed20-not-run.json)、[原生请求日志](internvl8-native-events.jsonl)。

固定探测记录中的辅助 `grounded=true` 仅表示存在结构化草稿，其 `parsed=false`、`observed_scene_present=false` 及两个几何命中标记才是未通过入口的依据。原始字段保留，未改写为成功；[筛选证据复核](internvl8-screen-evidence-audit.json)也区分了两次未评分诊断与20次评分请求。

## 比较范围与来源

在线控制器、物理资产、抓取标定、安全门槛、120秒时限及重观测预算保持原版。数据真值只用于离线定位与任务语义评分，未传给模型或在线控制。测试前固定所有配置、场景、代码与权重身份，协议SHA为`269db265baea87244f83bf057f0f685e1b9a56ee697f50aa134ce3d79625ac57`。新场景对1422份历史场景记录执行种子及精确几何去重；扩展图像审计与2090份历史 RGB 摘要无重合（包含本轮候选筛选的174份去重摘要），见[历史图像去重](candidate-historical-rgb-audit.json)，两模型初始RGB及depth完全一致。独立复核226,006个物理样本、999帧、349个动作，`valid=true`、`errors=[]`，见[复核报告](independent-validation.json)。

本轮以模型区块串行执行，避免模型切换冷加载进入任务延迟，区块内使用相同随机场景顺序；模型加载和未评分热身排除在任务延迟之外。区块时间与热状态可能混杂延迟比较，不能把它当作完全随机交叉调度。Qwen使用Ollama GGUF及JSON schema约束；InternVL使用原生多图Transformers及LMFE生成阶段JSON object语法约束，完整VisualDecision schema仍由同一提示与严格解析器验证，未修复或重写其原始回复。这是实际部署栈比较，不能把差异全部归因于参数规模。已执行的候选请求均使用320×240图像；InternVL内部448图块、最多4块加缩略图、ImageNet归一化、greedy解码配置在测试前固定。[官方8位及多图说明](https://internvl.readthedocs.io/en/latest/internvl2.5/quick_start.html)提供部署依据。

所有模型文件通过 `enp7s0`、显式AliDNS、TLS验证与SHA-256校验下载；依赖仅安装到`.venv-vlm`，Python头文件仅解包到工作区。默认模型和生产配置未替换，未驱动真实硬件，未commit/push。候选筛选数据与新独立测试分别保存，原60场景对比不被重新标为本轮新样本。

[最终文件与来源核对](verification-summary.json)及[产物 SHA-256 清单](artifact-manifest.json)用于检查本轮证据完整性。

## 复现入口

先读取[候选筛选协议](candidate-protocol.json)及[新独立测试协议](independent-60/protocol.json)。下载和探测脚本会保留校验及原始证据；已存在的测试输出默认拒绝重跑覆盖。

```bash
PYTHONPATH=src .venv-data/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/deploy_qwen.py
MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_model.py --config artifacts/research/process/20261004-t7-larger-vlm-candidates/qwen8-normalized.json --output NEW_QWEN_PROBE_DIR
PYTHONPATH=src .venv-data/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/download_internvl.py
.venv-vlm/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/internvl_bridge.py
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/internvl_screen.py
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/candidate_compare.py development
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/candidate_compare.py preregister
 # 固定入口筛选失败的InternVL不进入独立闭环集；关闭临时服务释放显存。
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/candidate_compare.py run --method qwen8
MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/candidate_compare.py run --method qwen4
.venv/bin/python artifacts/research/process/20261004-t7-larger-vlm-candidates/candidate_analyze.py
```
