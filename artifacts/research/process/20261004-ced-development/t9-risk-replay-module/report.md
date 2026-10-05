# T9 有限风险候选数值重放首块

状态：软件实现完成并冻结，等待独立审查。真实 RISK、selection 和 METHOD 没有准入证据，保持 UNKNOWN / NOT_RUN。只有新 `research/risk_replay.py` 和对应测试属于本块；默认 risk fit、CLI、协议、采集器、worker、数据集均未修改。

## 实现与来源

本块实现完整有限候选数值工作流：固定 SETTINGS 与候选库存 → 全量 train 的归一化/logistic fit → 独立 calibration 的 isotonic、可观察支持区间与分组残差 → 每条 selection/test 输入的守卫与概率 → 固定完整 selection 人口的 Brier → 最低 Brier、参数哈希平局规则 → 原模型/校准/selection 文件逐项重算比较。所有候选、缺帧、缺标签、失败和用途历史均保留。test 只读取已拟合结果，不影响拟合、支持区间或赢家。

纯数值入口 `replay_diagnostic_candidates(allocations, reconstructed_rows, candidates)` 的输出固定 SOFTWARE_ONLY；它不验证调用方传入向量的真实采集来源。登记入口 `RiskArtifactAuditor(replay_registrations, supervision_registrations)` 复制具体注册对象，内部实例化具体 `RiskSupervisionAuditor`，从原 RAW/监督注册重新读取来源，不接受替代 auditor、回调、serialized receipt、source_accepted 或概率输入为权威。不读取其他 auditor 的私有注册表。

完整 source manifest 为 517 文件，389 个 Python AST 可解析：515 个只读依赖均来自已独审 PASS 的 `risk-supervision-fix-round-1/source`，仅加新 owned2。基准 manifest SHA `389b8f85c08325201f29256235b0c760bbe9be0054d046d9a437e00364fbb8f8`、独审 SHA `336ff27096693abe4940c6946b62196ff04cd3f2a911a604adc62b5dfd98817c` 均在冻结前后核对。监督代码 SHA 为 `b5d0118b733f3da25747d50ac704b9e036a07bdf17aa958868b9d2c411ee268b`，RAW fix2 为 `0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a`。本包是准确的历史依赖覆盖层，不宣称其 515 个文件包含其他代理的后续新模块或当前项目全部代码。

`source/` 与最终独立覆盖层完全相同；只有环境 `.venv` 链接指向既有解释器，无 live production fallback。现场数值诊断实际加载的 72 个 production/test 路径均归入该 manifest。接口、工作流和每次命令见 `plan.md`、`frozen-overlay-setup.json`；source inventory 与字节 SHA、canonical model/calibration 内容哈希、固定 Python/Pydantic/Pillow/NumPy/OpenCV 环境分别记录，不能互相替代。

## 人口、标签及状态

- `assigned_attempts` 来自原 RAW case 库存；`allocated_observations` 来自原每 case 帧数。缺失源不减分母。
- `terminal_labelled_attempts` / `terminal_failure_attempts` 为任务级终止标签计数；`unknown_terminal_label_attempts` 保留原任务分母中无可重读标签者。`task_labels` / `failed_task_observations` 是另行保留的帧级标签计数。两帧同失败任务得到 1 个失败任务、2 个失败帧，不能替用。
- train/calibration 的特征、终止失败标签或已知用途历史缺项使数值拟合 UNAVAILABLE；单类训练、单类校准、空池和全部实际缺项有明确原因。selection 任一行缺失或守卫不满足，整个人口 Brier 为 None、候选 NO_FEASIBLE，不采用幸存子集。
- 校准 point/motion 残差按 group 取最大值、使用 `ceil((g+1)*0.9)` 排位；少于 9 组不能给出有限界限。仅已有标签组可产生明确 `AVAILABLE_LABEL_GROUP_DIAGNOSTICS` 范围的诊断量，所有缺标签与组数另行保留。它不是完整缺失人口的统计保证，也不是动作几何证书。
- 几何域严格为 MARKER_CENTER_TRANSLATION，仅 marker 中心点误差；不能代表 object extent、grasp、whole-target 或 native bounds。motion 与全部动作反事实/执行标签缺项保持 None，四池（包括 test）对应缺项行数均保留。没有伪造 SampleRecord/COMMIT。
- 历史 seen/tuned/train 不得移作独立 calibration/selection/test；case/group/scene 连接成分不得跨池。经授权 development 数据可作 train，但保留原用途与排除历史；未知使用史仍 UNKNOWN。
- 实际源 audit 只能返回 UNKNOWN/INVALID，没有 actual-positive、METHOD、permission、budget 或 execution accessor。诊断 VALID 与文件数值比较 VALID 都不改变实际状态。

## 分步验证与失败记录

1. 保存 missing-module 测试源后运行 RED：30 项因缺模块失败，随后实现完整数值链路。初版 29 通过/1 失败，原因是测试预期 list 与不可变 tuple 表示不同；保留日志，校正表示预期后继续。
2. 45 项完整工作流阶段前的 RED 保留了缺少用途历史、INITIAL 状态传播及 dataclass JSON 复制的缺陷。另存缺比较函数的 9 个 RED；补齐后 45 项 GREEN。原文件 rehash 后改系数、校准界限、概率/Brier/赢家，仍通过独立重算拒绝；缺原文件比较 UNKNOWN。
3. 追加历史、时钟、全部 blocker、opaque ID、实际 VALID 构造限制与注册历史输出反例。分别保存合格 RED 和修复结果；来源变更前后重读、lexical symlink 路径拒绝、原候选库存与严格 schema/非布尔有限数值均有覆盖。
4. 独立数值负控：常量平衡特征得到 raw/isotonic 0.5、Brier 0.25；9 组排位与 8 组无界限分开验证。非恒定特征另用独立一维递推核算 400 步 logistic 系数 `3.1078554459275782`，原 sigmoid 约 `0.9572156140331354`，isotonic 0/1，selection Brier 0。保留解析脚本/日志；初始测试草稿中的系数抄录值在运行前按独立脚本改正，未修改数值实现迎合预期。
5. 任务/帧分母和 action test 缺项的最后 3 个 RED 各自为缺少字段；补齐后专属 66 项通过。first Ruff 113 项格式/导入/行长错误、cold mypy 23 项注解/Any 错误及最后 1 项返回注解错误全部保留，机械格式及显式注解修正后静态通过。
6. 最终 517 冻结覆盖层重新运行：专属 **66 passed in 5.69s**；已批准相关 CPU **249 passed, 1 deselected in 37.59s**。唯一排除是原已有 compiled-dynamics 测试；无模拟 state/step、渲染、采集、GPU、模型服务、网络或控制器动作。Ruff owned2、format owned2、`--no-incremental --follow-imports=silent` cold mypy module1 全通过。mypy 保留原 pyproject 的两个 ROS unused-section note。
7. 最终数值重复两次严格相等；单个登记软件 fixture 保持 1 task / 2 observations、1 failed terminal task / 2 failed task observations，actual source UNKNOWN、diagnostic UNAVAILABLE、comparison UNKNOWN。完整诊断输出分别是 `software-only-numeric-replay.json` 与 `software-only-registered-replay.json`，都不是研究正式结果。
8. posthash 对归档和最终覆盖层全部 517 文件、原基准 515 文件、基准 manifest/review、现场 owned2 及 loaded-source closure 再次一致；没有覆盖历史原包或借用移动依赖。

## 复现与剩余职责

最终复现命令、环境与覆盖层路径见 `frozen-overlay-setup.json`；各 exit code 与耗时见 `frozen-check-results.json`。第三方应只复制本包 `source/` 并按 manifest 核对，再运行这些 argv；不要从当前工作树补源。

仍缺实际独立 INITIAL、真实 clock/calibration publisher、连续 fresh-motion 标签、COMMIT/动作执行对齐反馈、真正 SampleRecord materializer 及原本完整候选模型/selection 文件。当前真实 marker-motion 数据只有另块保存的诊断 RAW/监督用途，不能充当独立 calibration 或 actual risk acceptance。本块不支持 raw-v3，也不修改实际默认 fit 的 source_accepted false。后续 materializer、真实 fresh-motion 标签和实际源准入分别承担其职责；当前数值重放不是这些实现的替代品。

本包依赖与 artifact 从未自动发布训练模型。软件核可以得到明确 DIAGNOSTIC 赢家，真实 selection/METHOD 依然 UNKNOWN/NOT_RUN；不宣称实际科研验收或全系统开发完成。

额外 setup 记录见 `setup-notes.md`：诊断输出脚本最初在覆盖层使用错误相对 artifact 目录，以及误写了不存在的 helper 名称，均保留失败日志/初稿后修正；两次均未改变生产代码、测试结果或来源冻结。
