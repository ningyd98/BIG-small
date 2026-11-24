# G1 正式仿真的范围与入口核验计划

gpt-6.2-astra · 2026-11-24 · 研发基线 `2da8a704a0ee249ea060aed681728e429fea5815`。机器可读计划列出 40 份输入的 SHA256、v10 八处来源差异和预检输出判据。[计划及摘要](plan.json)

用户已指示开展正式仿真。当前可立即执行正式研究入口的准入核对。正式采集要先确定所测对象：独立测量眼前的低位双标候选，或按开题路线取得 T16 冻结标称测试层的数据。原 v10 是单独的教师标定分组。

| 对象 | 实际入口与冻结状态 | 可取得的证据 |
| --- | --- | --- |
| G1 双标候选 | `scripts/graduation/g1_dual_trials.py` 的 issue/capture/audit 绑定开发计划、开发 schema 和实际源码代。11 月 24 日两臂各 0/4，双标 3/4 进入接近，两例失标，一例夹指接触载板。双标有效 362/366 帧，条件误差 P90 为 2.927 mm。 | 采用独立新登记、冻结单臂或配对方法、新摆放和真实采集适配，可先测候选，按摆放给出有限范围的率与不确定性。 |
| 原 v10 教师 | `scripts/collect_native_calibration.py --collect-once` 读取 Phase 5 权威登记。九组均属 CALIBRATION_ONLY，仅 0001 释放且 claim 已存在。Phase 6 该组尝试一次，6,240 步、11,109 帧，LIFT 后置 UNKNOWN 后停止，其余八组预分配未释放。456 项来源中当前树有八项与冻结代不同。 | 原结果可从原件读回。继续教师标定需要独立后继释放，不可改旧登记或复制新账本重跑。 |
| 最终 T16 | `scripts/run_rgbd_research.py` 读取实际 FINAL 和冻结池；本树约定位置缺 `protocol.json`。合法元数据进入 `run_assignment` 也会因缺真实适配停止；现有注入适配只接 MOCK。`scripts/freeze_rgbd_protocol.py --stage final` 固定拒绝。 | 真实 T15c 运行、T16 标称层原始轨迹及正式 G1 评分有待研究链就绪。R07 的同名 producer 目录属于恢复试验历史来源。 |

开题要求正确识别且深度有效时物体顶部几何中心的误差 P90 ≤10 mm，另报覆盖，独立静态抓放成功率 ≥90%。90% 用于评判已取得的结果。软件准入、开发候选实测、独立候选测量、T16 最终验收分别记载。既有 4 对开发样本和 v10 预分配均不进入新候选测量分母。

## 可立即执行的入口预检

在基线工作树根先检查 `artifacts/research/protocol-final/protocol.json` 的真实存在性，若出现则暂停缺文件探针并核对其正式来源。以新建私有目录作为 `CHECK_ROOT`，其 `entry` 子目录应不存在。保存运行前后 claim 清单、数据库及库存文件 SHA。命令如下。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. ../harness-candidate-20261118/.venv/bin/python scripts/run_rgbd_research.py --config configs/research/formal.yaml --protocol artifacts/research/protocol-final --output "$CHECK_ROOT/entry"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. ../harness-candidate-20261118/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_research_runner.py::test_formal_runner_requires_final_protocol_hash tests/test_research_runner.py::test_valid_metadata_without_actual_adapter_is_blocked
```

对照实际 CLI 退出码 3、输出 report.json 的 NOT_RUN、real_runtime_integrated=false、assigned_denominator=executed_assignments=physical_success=0，以及所缺的协议文件路径。两个软件测试分别检查冻结要求、真实适配缺失后的原始 BLOCKED 和零物理步。将这次执行记录为入口预检。只有 MuJoCo 实际启动与原件归档才能计为新仿真。

## 执行与验收边界

1. 先核对基线、输入 SHA256、正式协议与 claim 的文件集及时间；独立读取已有原件的索引、首组回执和历史保全记录。原件有异动时查明原因后再执行。
2. 检查研究根 artifacts/research/protocol-final/protocol.json 的实际状态。当前不存在时执行只读来源预检，将入口报告写入唯一私有目录；若在执行前出现，先验证协议的正式来源，停止此缺文件预检。用两项软件测试独立验证合法元数据缺实际适配时的拒绝语义。保留 exit code、stderr、report、测试输出、前后 claim 与原件指纹。
3. 若选择单独 G1 测量，先制定该范围的 Astra 实施计划。独立冻结候选 XML、实际加载的源码与依赖、相机、姿态标记/感知策略、在线门控、静态摆放抽样分布、数量、顺序、独立来源组与物理初态。逐项查重开发/标定/策略选择、正式测试池、场景祖先和实际摆放。为新登记和预分配的每槽提供真实 worker 一次性派发、并发和中断去重、原生保护/急停、独立复位、私有原件封存及盲评入口。旧开发 allocation、状态标签与 plans 均原位保留。运行前用隔离夹具验证准入/拒绝、重启和全分母读回，用非持出样本验证实际适配、时钟、来源、磁盘和封存能力。
4. 单独 G1 采集时使用真实 MuJoCo/EGL、当轮冻结来源和专用新目录/账本。每个预分配保留拒绝、失败、超时和安全停止；禁止重跑直到成功。线上记录图像驱动八动作与安全决策，真值仅用于独立离线评分。归档 RGB-D、逐步状态、安全事件、manifest、claim 及作业/租约，核对时间、SHA 与全分母。定位对正确 ID/有效深度目标顶部中心计算三维误差 P90，另报覆盖；抓放成功须在线完成且独立物理成功，升高至少 50 mm 持稳 0.5 s，释放后区内稳定 1 s，保留安全评价。报告摆放数、置信区间与仅限该代候选、该分布的结论。
5. 若选择开题完整正式路线，在形成合格教师/独立静态与安全证据、B0 四周期 120 组筛选及合格 B0 后，依项目依赖推进互斥 120 组基础先导、INITIAL、方法冻结、另 120 组功效先导、FINAL 及正式实跑/验源适配。先核真实冻结协议/池/方法引用和真实适配路径；按功效规则锁定每方法 N，再运行 T15c 并在 T16 冻结独立标称层评 G1。条件变动或拟改源码前另列分轮 Astra 计划；已有软件占位、冻结失败及预定样本不计实测。
6. 只有后续明确指向 v10 教师续跑，才以独立新版本计划处理具体释放范围/代际、旧试次谱系、冻结来源、正式登记及退出规则；保留当前单次 claim、release YAML 与登记。新版本未签发前，现 v10 登记无可派发组。

若相关上下文仍不能消除范围差异，只问一次：本次是先测低位双标候选（建议 4 个全新独立摆放，单臂各跑一次），还是推进开题 T16 的完整正式实验？如已有指定的独立样本量或要求单/双标配对，按该范围登记。 此处 4 个是独立候选小批的建议工作量，开题最终正式 N 按原功效规则确定。若上下文已选路线，则直接沿该路线进入下一轮计划。

原 v10 文件 SHA 为 `da431fdb96f8b2672fb621d4ca4c87b673835f26ce874c7ce03da8fb043a7972`，唯一 claim 为 `6599b24b95016ddddf0ad8df47c3a96d64b13b7eb6fc7abba06809b756ccdee7`，原件清单为 `1f031851148dbb633504adf3d82ec2122dc35d786e632be5e5010fd8a3ee699d`。11 月 24 日历史保全逐项通过 55,583 文件、6,578,143,222 字节，本轮编制复核协议、claim、数据库、主要回执和库存文件摘要。
