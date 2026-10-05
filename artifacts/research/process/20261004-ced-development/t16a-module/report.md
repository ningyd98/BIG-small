# T16a 配对统计、全分母诊断与阶段判定

Status: **SOFTWARE_ONLY_IMPLEMENTED_PENDING_INDEPENDENT_REVIEW**. 本轮交付六个新文件的 CPU 统计和审计软件。所有正式研究目标默认 **NOT_RUN**；没有真实物理成功、正式功效验收、INITIAL/FINAL 方法验收或节约结论。`source_verified`、PHYSICS 声明、哈希一致及调用方写入的 `formal_accepted` 均不能替代独立原始来源重算。

## 接口和输入

- `statistics.EffectEstimate` 保留点估计、原始双侧 95% 区间、原始和校正 p、独立分母和方法名称，另列单侧 95% 上下界。`paired_binary_effect(pairs)`、`stratified_paired_bootstrap(records, metric, iterations=10000, seed=20261003)`、`holm_adjust(mapping)` 保持计划接口。
- `metrics.compute_research_metrics(records, opportunities, gate_records, *, software_only=False)` 保留全部记录和固定机会分母。只有显式 `SOFTWARE_ONLY` 允许声明结果用于数学诊断；`formal_accepted=False`、`accepted_physical_success=0` 始终不变。
- `acceptance.evaluate_goals(metrics, protocol, *, software_only=False)` 使用冻结目标。`GoalVerdict` 明确 PASS、FAIL、INSUFFICIENT_EVIDENCE、NOT_RUN 和 evidence_scope。默认全部 NOT_RUN；软件数值 PASS 不能成为研究或物理 PASS。
- 生产复用入口为 `cloud_edge_robot_arm.research.acceptance.analyze_research_runs(runs: Path, protocol: Path, output: Path, *, software_only=False) -> Mapping[str, object]`。`scripts/analyze_rgbd_research.py` 调用同一函数；重建工具无需执行历史命令。正式默认返回 exit 3 / NOT_RUN，显式完整软件诊断 exit 0 / SOFTWARE_ONLY。

FINAL 分析必需 `protocol/protocol.json`、`runs/assignments.json`、`runs/records.jsonl`、**`runs/pools.json`**，没有后备池路径。池文件格式与 T15 输入一致：JSON object，`formal` 是原始 2400 条 scene/scene_hash/stratum_id/perturbation 记录，可保留其他阶段池键。`content_digest(formal)` 必须等于 FINAL `spec.pool_hashes['formal']`；整个文件实际字节 SHA256 另写入 `source_hashes['pools']`。不通过新自称版本或哈希声明授予验收。

分析先从该完整池调用同一 `build_assignments` 重建七个核心方法 JOINT/B0/B1/B2/NO_UNCERTAINTY/NO_TIME_VALIDITY/NO_LOCAL_REPAIR，比较**完整有序分配清单**。因此冻结 N、12 层均衡、场景前缀、完整场景和扰动、物理种子、网络时序、方法和协议散列以及随机执行顺序均不能通过重新散列删样本改变。然后严格逐条加载 T15 记录，要求全部分配恰好一条原始记录，包括 BLOCKED/STOP/timeout/fallback/失败。缺池、删失败、重复、少方法、缺层或配对错位 => coverage INCOMPLETE / NOT_RUN；不计算不完整子集收益。纯数学 `compute_research_metrics(..., software_only=True)` 可使用无绑定的明确 MOCK fixture，不进入 FINAL CLI。

## 统计方法和数值反例

匹配二项差定义 `D=JOINT-baseline`，四格聚合为 D=+1/-1/0 的多项分布，参数 `P(+1)=(q+delta)/2`、`P(-1)=(q-delta)/2`、`P(0)=1-q`。固定 null delta 后，直接最大化多项似然得到约束 q 根；在 `|delta|<=q<=1` 范围求解，然后用 `sqrt(n)*(delta_hat-delta)/sqrt(q_tilde-delta^2)` 的得分反演。80 次二分收敛到浮点精度；没有 Wald 零方差替代或人为方差下限。这是代码中明示似然的解析推导，未声称使用未核验第三方论文实现。

独立解析反例 ++40/+−20/−+10/−−30 给差 .1、零差双侧 p=.0678891549；相同边际但更高不一致率给 p=.1572992071 和更宽区间。100 对全一致样本差区间仍为 ±.0369934982，单侧上界 .0263427208，与解析 `z^2/(n+z^2)` 一致。零事件单侧上界使用精确 `1-alpha^(1/n)`；100 个独立组为 .0295130496，永远不报告零宽度。安全和门控零事件附加界明确针对“独立基础组内任一事件”，没有将组界冒充逐帧事件率界。

bootstrap 至少 10000 次、固定种子、在每层按基础场景簇配对重采样。帧不增大 N；重复种子先留在同一基础场景簇内，配对种子/网络时序**多重集合**必须相同。正式主效应一场景一方法一条记录；重复主组拒绝，不能把重复种子误当独立成功样本。连续主收益采用明确方向的相对减少，基线零为 N/A，含无定义重采样的区间为 N/A，不过滤坏重采样。检验与区间分列：双侧原始95%百分位区间；配对标签交换的一侧 p，n<=16 精确枚举，其余固定10000次 Monte Carlo 且加一校正。该检验依赖固定配对中方法标签在零效应下可交换；没有可交换性或完整来源时不能作正式解释。

G3 从两方法公共固定机会内汇总每组误放行数后配对 bootstrap，保留零事件组，不把机会/帧作为独立样本。VALID / INVALID / UNKNOWN 分母分列；UNKNOWN 不补为错误拒绝。回放永不计入任务物理成功。

固定五假设族为 G2_REQUESTS/G2_SUCCESS/G2_SAFETY/G3_FALSE_ACCEPT/G4_DURATION。缺未执行假设保留在族内，校正时 p=1，原始缺值仍 None；Holm 校正 p 和原始95%区间分列，未声称区间同步做多重校正。NI p 在成功差−.03（greater）和安全差+.01（less）处求值；不以“未显著”证明非劣。

## 目标与诊断

成功差单侧下界严格 >−.03，安全差单侧上界 <=+.01。G2 请求减少30%另要求原始区间改善、完整 N 和三个相应 Holm p<=.05。G2a 字节25%与惩罚P95时长15%单独显示。G1 数值门为定位P90<=.01m、独立静态成功>=.9，覆盖/目标身份/有效深度来源仍须另验。G3 相对误放行减少50%、绝对误放行<=2%、错误拒绝<=5%、完整固定 N 簇和可靠区间/Holm 分别判断。G4 必须200故障组、成功>=80%、恢复中位数可靠减少30%、已完成不可重复动作重提为0。未产生源绑定 G1/G3/G4 表不能填 PASS；G0、G5、C1、C2 均不从声明补齐。

方法表报告完整分母、在线 DONE 分母上的误完成、fallback、UNKNOWN、no_progress、总云请求（含远程 JUDGE）、角色调用、应用字节、Tcap 惩罚P95、声明组件决策延迟、推理未知和提供者版本。失败恢复60秒；当前无独立恢复来源验证，任何元数据成功不缩短60秒。未记录的 provider refusal / fault response 率和延迟为 None，明确 NOT_RECORDED，而非补零。实际原始物理、捕获、模型、决策和故障时间线验证器尚未接入；相关统计不能用于正式接受。

独立审查修复第一轮：G2 请求收益点未达30%时的明确 FAIL 不再被未定 NI 覆盖；成功差单侧上界<=−.03、或安全差单侧下界>+.01 表示明确劣于，数值结果为 FAIL，而跨界未知仍为 INSUFFICIENT_EVIDENCE。正式默认 NOT_RUN 保持。条件 UNKNOWN 的规范分母是全部条件评价次数，fallback 的规范分母是全部决策轮次；当前没有经来源限定的条件/轮次记录，故 `unknown_condition_count/rate`、`condition_evaluation_denominator`、`fallback_decision_count/rate`、`decision_round_denominator` 和规范 `fallback_rate` 均 None/NOT_RECORDED。保留 `unknown_episode_count/rate` 和明确命名的 `fallback_episode_count/rate` 作为额外集级诊断，不能改称规范决策/条件比率。一个UNKNOWN+99PASS跨两集的fixture不以.5冒充.01。

输出 report.json、metrics.json、goal_verdicts.json、goal_verdicts.csv、goal_status.svg；点/区间固定种子、无虚构时间戳，图用固定 SVG salt / 空 Date 元数据。相同输入重复调用得到相同内容，存储 cmd 字段不执行；输入原始记录不改写。

## 验证和发布

TDD 初始25个缺模块/实现失败；新增簇/重建反例3个失败；数值目标门6个失败；重散列删失败和缺池2个失败；完整五假设/零事件/固定机会簇3个失败。相应 RED 日志保留。冷进程出现共享 typed EvidenceVerdict 导入环，失败日志保留；共享 owner 修复后重新执行。

最终 T16 专项 **40 passed in 9.39s**（green-final.log）。范围包括全部4200条明确软件 BLOCKED 记录、每方法600条/主配对600组、失败Tcap120、不改变原始字节、正式默认全 NOT_RUN。Scoped Ruff passes（ruff.log）；mypy 4 个源码无问题（mypy.log，仅原有 ROS 配置提示）。T15+T16 合并 CPU 回归结果见 green-regression.log。未运行全套、GPU、渲染仿真、模型网络或真实正式研究。代码及六个新文件 source/、source-hashes.json、review-package.diff 以本次发布为准，独立审查结果另记录。

原始独立审查 `review.md` 为 REQUEST CHANGES，原始全部六文件保存在 `fix-round-1-baseline/source` 及原manifest/report/diff。新增四个判定/分母反例 RED 转 GREEN（fix-round-1-red.log / fix-round-1-green-targeted.log）。修复后完整 T16 专项 **43 passed in 9.55s**（fix-round-1-green.log）；scoped Ruff 与 mypy4再次通过（fix-round-1-ruff.log / fix-round-1-mypy.log）。本次源发布为修复后六文件，新旧差异另存 fix-round-1-review-package.diff；等待独立复审，未声称实际研究接受。
