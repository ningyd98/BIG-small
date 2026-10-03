# T7 同 episode 视觉闭环验收

验收日期：2026-10-04（Asia/Shanghai）；工作开始于 10-03，证据目录保留原日期。

**状态：T7 DONE，仅限当前 MuJoCo 资产的开发验收。** 同 episode 闭环、真实模型/步进证据、20 场景开发门槛、runtime 异常与最终回归均已通过。T8、T17a 进入 READY；T6b 保持 TODO。

## 实测结果与分母

| 证据 | 全部分配 | 结果 | 范围 |
| --- | ---: | --- | --- |
| [smoke v2](smoke-20-v2/summary.json) | 20 | 2 SUCCESS、18 FAILED、0 blocked、0 false completion | 正常场景 2/12；全部分配 2/20（10%） |
| [最终独立复算](smoke-20-v2-validation-final.json) | 20 | valid=true、accepted=true、errors=[] | 34,353 个连续物理样本、154 帧、52 个动作 |
| [smoke v1](smoke-20-v1/summary.json) | 20 | 0 SUCCESS、20 FAILED | 独立复算有效，但开发门槛未通过；原证据保留 |
| [真实模型重探](model-probe/probe-report.json) | 4 | 1 冷 3 热请求均通过固定场景门槛 | 双图、GPU、严格合同及独立定位核验 |
| [离线 selection](offline-selection/derived-summary.json) | 5 | 1 规划定位通过、4 目标命中、3 深度拒绝、0 blocked | 不是动作成功或正式 G1；test 接口另由契约测试覆盖 |
| [独立数据作业](data-job-real/verification.json) | 1 组 | COMPLETE / SUCCEEDED、model_calls=0、task_success=false | 数据生产完成，不表示机器人任务成功 |

v2 成功案例为 `case-02`、`case-07`；预分配为 12 正常、4 目标缺失、2 无效深度、2 安全停止。全部失败保留，失败原因和阶段覆盖见 summary。v1 与 v2 使用相同开发分配，以便诊断修复；没有调整场景、模型或物理通过阈值。这是用过的开发样本，不能作为独立泛化估计。**2/20 表示闭环已跑通但可靠性仍低，不满足正式 G1 的成功率声明。**

v1 失败分析、`diagnostic-01/02/03`、v1/v2 各 34 份源码快照均保留。修复了遮挡下的 RGB-D 时序身份、边缘混合深度及抬升保持观测；没有用实例真值补足在线感知。`diagnostic-03` 的单例双成功只用于诊断，未追加到 20 例分母中。

## 已交付行为

- 同一 backend/episode 完成采集、模型规划、已有技能执行及动作后重采集；借用相机会话不 reset 或关闭 owner。
- 条件统一返回 PASS/FAIL/UNKNOWN。目标身份、时间戳或深度缺失不能通过，释放夹爪和 TCP 高度不能单独证明放置或抬升。
- 保存技能返回、在线判定和末尾独立物理判定三层证据。在线只使用 RGB-D 与机器人本体状态；物理样本在尾评分阶段评价，不能反向参与动作或恢复选择。
- 开发预算为重观测 2、重试 0、连续无进展 3、截止时间 120 秒；缺少恢复能力时停止。实际部分动作、取消和预算检查点保留，不把技能返回值当任务完成。
- 默认 RGBD / VISUAL_PLANNING，显式提供 CAPTURE_ONLY / VISUAL_PLANNING / VISION_CLOSED_LOOP。前两者始终 task_success=false。HTTP 和 WebSocket 共用模型工厂，active profile 优先于环境冻结目录。
- DATASET_GENERATION 是单独作业，不调用模型，输出由 worker 固定在作业目录；校验配置、注册资产和符号链接，保留取消/超时后的已提交样本。
- 模型调用有界、心跳独立运行，取消或超时后的迟到回复不再派发动作；后台真正请求结束前不释放其调用容量。租约过期不能续活，旧 worker 不覆盖新 owner 的文件、attempt、状态或索引；RGB-D 中间文件按 lease 隔离。
- 工作台固定 S01 的语义尾评分与在线/物理结果合取；JSON 安全转换保留真实事件和预算的 ISO 时间，不能因 datetime 归档失败而丢失完成证据。

可选 HOME 步骤因当前固定速度接口无法验证受限执行意图而明确记录 NOT_EXECUTED，实际闭环最多执行 8 个核心技能。安全检查使用显式研究范围与绝对关节速度，T4/T5 资产、控制器和独立物理评价门槛未放宽。

## 验证与来源

最终 `MUJOCO_GL=egl` 合并回归 **454 passed、1 warning，96.55 秒**，无跳过或排除；覆盖 28 个测试文件，包含真实无模型采集、取消/超时、租约交接、发布失败、闭环和 T2/T3/T4/T5/T6a 相关回归。测试前后 58 个源码/测试文件 SHA 保持不变。见 [测试日志](final-tests.log)、[命令与来源](final-tests.json)。现有 warning 为 Starlette/AnyIO alias deprecation。没有声称整个仓库测试套件通过。

30 个相关生产/CLI 源文件 Ruff、mypy 通过，12 个新/相关测试及 worker 复现脚本 Ruff 通过，见 [检查范围](final-check-scope.json)、[Ruff](final-ruff.log)、[mypy](final-mypy.log)、[测试 Ruff](final-test-ruff.log)。最终 83 份源码、测试与依赖副本及 SHA 见 [source-manifest.json](source-manifest.json)；工作区已有其他改动，未用 Git HEAD 冒充本次完整来源。

[真实 worker v3](worker-closed-real-v3/verification.json)完成一次本地模型调用和 4 个物理动作，因 `LIFT_HOLD_NOT_VERIFIED` 如实结束为 FAILED，online/physical=false、semantic=PASS、task_execution=EXECUTED、error=null、consistent=true。52 条验证记录和 12 个事件时间戳已正常归档，`verification_state` 可检索。它证明端到端运行与失败归档正确，不增加成功分母。之前 `worker-closed-real` 保留真实 datetime 序列化错误；`worker-closed-real-v2` 保留验收辅助脚本缺少仓库 import 路径而 BLOCKED 的启动记录，未执行模型或动作；修正辅助脚本路径及不存在的 close 调用后另建 v3，没有覆盖旧结果。

发布 I/O 失败反例已关闭：自有 worker 在本次成功发布失败后，通过 owner/lease 比较将 SUCCEEDED 修正为 RECOVERY_PENDING，保存已执行证据，最多尝试一次失败归档；持续文件写入失败时清除成功文件索引、释放租约，不自动重复执行。该保证以 SQLite 可写为前提，不能声称持续不可写的磁盘仍能产出文件。

文档全局检查仍有 18 条已有问题（后续阶段尚未提供的脚本引用与旧内容模式检查），本轮无新增；见 [差异记录](docs-check-delta.json)。未声称仓库全部文档检查通过。

已完成独立审查：[执行引擎](execution-final-review.md)、[条件与独立重评](conditions-final-review.md)、[Runtime](runtime-final-review.md)、[逐项需求](requirements-review.md)。最终无未关闭 P1/P2；早期执行审查所列 worker 语义接线问题已由后续 runtime 审查、454 项回归和真实 worker 验证关闭。

模型仍是本地 `qwen3-vl-candidate:4b-instruct`（Q4_K_M，权重 SHA `d18dda6d10491bbe92186dbc7c854623bf99f48eb75829dbe290ef0f97626107`），320×240、normalized_1000、temperature=0、num_ctx=8192、num_predict=512、think=false、`mujoco_upright_box_v1`。T7 重探冷请求 3891.851 ms、热 P50/P95 1489.424/1516.331 ms，显存采样峰值 5746 MiB；TTFT 未测。现行冻结包[只读验证通过](model-frozen-verification-final.log)，使用 localhost Ollama，本阶段没有下载、训练或权重更新。

旧 T3/T5 绑定的共享 capture 源码与现行源码不同，不修改旧冻结包来掩盖漂移。T3 的 8 份、T5 的 12 份历史来源已保存；[T5 保存清单](t5-prerequisite-preservation.json)核验其余 11 份来源未变。旧教师数据继续按原协议解释，后续教师生成须新版本。为保留 T5 原序列化，教师结果不新增在线完成字段；字段缺席等同没有在线判定，不能算入在线成功分母。

## 复现

从仓库根目录运行；真实模型和 EGL/GPU 作业串行执行。输出必须使用不存在的新目录，不覆盖历史证据。

```bash
.venv/bin/python scripts/probe_rgbd_model.py --verify-frozen \
  --output artifacts/research/process/20261003-t7-visual-closed-loop/model-probe

MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_smoke.py \
  --scope closed-loop --episodes 20 --config configs/research/visual_smoke.yaml \
  --frozen-dir artifacts/research/process/20261003-t7-visual-closed-loop/model-probe \
  --output artifacts/research/t7-smoke-reproduction-new

.venv/bin/python artifacts/research/process/20261003-t7-visual-closed-loop/verify_smoke.py \
  artifacts/research/t7-smoke-reproduction-new

MUJOCO_GL=egl .venv/bin/python \
  artifacts/research/process/20261003-t7-visual-closed-loop/run_worker_check.py \
  --frozen-dir artifacts/research/process/20261003-t7-visual-closed-loop/model-probe \
  --output artifacts/research/t7-worker-reproduction-new
```

工作台启动、独立数据作业、API 与结果字段说明见 [使用说明](../../../../docs/rgbd_visual_closed_loop.md)。`final-check-scope.json` 记录本轮检查文件范围。

## 限定范围与下一阶段

仅限当前 MuJoCo S01 资产、可区分颜色的直立刚性方块及已标定顶抓。工作台语义 PASS 仅支持文档列出的中英固定红块到绿区指令；其他颜色为 FAIL，否定、多任务或未列出的改写为 UNKNOWN。语义评价发生在执行结束后，不能声称它已经预防所有误抓。任意自然语言、真实 RGB-D 数据集上的模型训练、泛化抓取或真实机械臂均未验收。

T8 的请求/字节成本账本与 120 场景基础先导、T17a 的能力界面已进入 READY，尚未实施；T6b 仍为 TODO，等待 T8 预算。正式 G1—G5 和论文权威运行数不因开发 smoke 改变。
