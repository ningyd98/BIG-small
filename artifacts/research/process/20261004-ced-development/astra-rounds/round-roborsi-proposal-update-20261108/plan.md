# 开题—RoboRSI 开发方案更新：Astra 文档限定计划

实际规划模型 `gpt-6-astra`。核查时点 `2026-11-08T07:29:24.663341+00:00`；HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`。仅文档更新，不释放运行额度。目录创建前确认不存在。

## 问题与原始证据

上轮回答把10/25暂停状态、10/22 Qwen计划当成当前状态，此对话错误由ROOT报告并保留原对话；不虚构日志。当前 `ced_roles.yaml` 已为 `gpt-6.1-sol`，边缘为规则/成本provider，模型后置，dispatch/local_recover均false、NOT_ACCEPTED。R460记录4次历史RGB-D真实API回放；R465记录reader6/adjacent134及静态检查通过，只是软件交付。R468真实教师采集被监督器临时SQLite文件ENOENT中断，rc-15、physics≥13/render≥41为下界，native UNKNOWN/formal NOT_ACCEPTED。R469和R470是后续限定计划；补充定点读取R470终态：full FINISHED、rc1、已回收且无存活后代（07:22:58 UTC结束），read rc0但九组scores全null、joint_bound_m=null、native_authority=UNAVAILABLE；首组八动作missing，其余missing_group。本轮只记录状态，根因未分析，不修复或重试。R469仅有计划证据，不推断当前运行状态。

根因是证据截止日期和层级混淆，无需修产品。两份开题材料的排期及专业措辞不同：本轮只采用10/24申请表为月度排期参考，明确与旧报告2月正式实验安排的差异，不修改原件或推断学籍变化。

## 输入与适用性

全部直接输入SHA256见下表及plan.json；不递归旧轮次祖先。DOC原件仅hash，正文读取ROOT用bundled LibreOffice提取的TXT；DOCX仅zip/XML只读解析。外部RoboRSI固定commit和论文v1摘记由ROOT已读取提供，本规划未重复联网。

| 输入 | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `configs/research/ced_roles.yaml` | `a8c21a58b28d7850e5d577027409e4e1db18be659219f33c2ed029fc06479e47` |
| `docs/superpowers/plans/2026-10-22-post-opening-development-plan.md` | `a71f8e7c98646a6a130b768c7497c6a0c1d5f569ae62e9cf398d38d3672beb05` |
| `docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md` | `dae788ab850288de1a524de37e21391e1e026b62375eaf06c798b8c87d49e0c1` |
| `output/doc/20261021-proposal-revision/开题报告-2501220176 宁业栋_修改版.doc` | `4fe39c32f990be2adc2789fba08c2600382c8a03247f9fef66ae6dc982288ccd` |
| `/tmp/bigsmall-roborsi-plan-20261108/开题报告-2501220176 宁业栋_修改版.txt` | `d7643b92f4b2834f278c128ee831d2ddcb03d192e294ad2292e39e4aff8a5767` |
| `output/doc/20261024-opening-application/开题申请_含系统架构图_计划至202704.docx` | `ae87dbffc7d3a1cd2623051c4cc03d220bfe3e1301de7b75ae8c73d54058e987` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round460-openai-sol-real-replay-20261108/implementation/step-report中的阶段总结` | `fd3af49d8e401996c31451614ce46b814be2ab12134ab276c059c913388b8c1c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round461-sol-evidence-reader-and-mainline-plan-20261108/implementation/step-report中的阶段总结` | `67ec8b5865781a052ac78e56005e50f895b0ad8dc6764c4dd77a1186770ae5ff` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round465-reader-wire-numeric-type-alias-20261108/implementation/step-report中的阶段总结` | `54a0418385240cf24f8b84c5d8307cb0adbdb7cfa9755f3ec33aa67ad2271967` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/implementation/step-report.md` | `2ca67be22ed38961a9a0f2640458ef1eb4266eea972eb25dbdaa69692d16914c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round469-current-sol-nominal-runtime-20261108/plan.md` | `f6f163d8fa04e8c059d190e3625d70713f61ecc38c509c17f522571d54a093da` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/plan.md` | `024abb0913f9718241eec89c76a49b97558af5aaf4b3952b94559979a8f98136` |

实施前重新核对直接输入、HEAD、分支与index。仅新提交的文档不当然使研究输入失效，但任何影响结论的变化必须先判适用性；新根因/范围扩大/计划外失败先下一轮实际Astra。并行R469/R470只读定点核查最新报告并加时间/来源，不据目录存在推定成功。

## 限定产物与执行步骤

1. **D1**：实施前重新hash全部直接输入、核对HEAD/branch/worktree/index及本轮目录独占；精简input-manifest按直接输入记录，不递归祖先。并行R469/R470新报告只读定点核查并加入来源，标截止时间；没有新报告就写未在本轮核验。
2. **D2**：新增高层开发更新文档：开头明确补充覆盖10/22模型/起点/排期及10/04旧云模型描述，保留三层设计、G0–G5、B0–B5、样本/统计/冻结规则和现行微观计划；以状态分层表和开题三项研究映射展开。
3. **D3**：写RoboRSI借鉴矩阵：结构化反馈与有界上下文、离线审查经验包、同条件版本评测；逐项列可借鉴/适配接口/研究问题/验证/不直接迁移内容。研究核心实验共用固定context/experience，经验开关另作可选对照。
4. **D4**：按当前源码正常正链→标定及合格B0/INITIAL→一致性/协同→局部恢复→METHOD/独立功效先导/FINAL→正式研究组织依赖；按10/24申请表给出条件化月度排期与最近可核验交付。所有实际修复/运行回到适用Astra计划，不从本文件派生新额度。
5. **D5**：仅做Markdown链接、JSON、hash、diff及内容静态核对；步骤报告保留命令/退出码/输入适用性/未运行项与限制，并在本轮step-report汇入阶段总结，不改共享历史总结。显式路径提交推送研发分支并核对local/upstream/remote SHA；并行branch/index变化时先复核，不纳入他人staging、不reset、不force。

ROOT允许新增：`docs/superpowers/plans/2026-11-08-proposal-roborsi-development-update.md`，以及本轮plan.md/json、input-manifest.json、step-report.md/json；提交后可新建本地delivery-receipt.json。不得修改旧计划/spec/开题原件、共享历史总结、源码、测试、配置、资产、冻结pins、raw或数据库。

## 新方案必须保留的设计与实验边界

- 三项主线：视觉观测与动作条件一致性；风险与通信成本下云边协同；执行反馈和效果依赖局部修复。
- 保留OpenCV/RGB-D/可见姿态标记/顶视相机/既定控制器；当前云gpt-6.1-sol，边缘规则/成本provider、模型后置。
- 结构化反馈可列observation/task/plan版本、三值条件及原因、已验证效果、合法候选、余预算及来源；仅列拟适配，不虚构现有接口全部具备。上下文裁剪不得删除当前身份/新鲜度/取消/预算/失败证据。
- 离线经验仅来自隔离开发来源，保留失败和适用条件，经审查冻结包与hash；当前帧重新定位，不重放旧xyz；不向在线agent暴露独立真值、teacher或state.success。
- 核心策略实验保持相同模型/provider/提示生成规则、上下文预算/打包算法、经验版本、控制器、安全层、种子和网络日程；不强制不同触发时刻的观测字节相同。经验有无为独立可选研究，不冒充云边策略收益。
- 论文动作审查跨度4的结果仅为特定任务外部结果；不是事件触发策略，不能直接移植百分比作为本项目目标。
- 区分物理时间和墙钟；延迟分解和等待环境推进模式预登记；保持现有等待时物理推进约束，诊断暂停模式另标且不混入主比较；禁止放宽TTL换成功率。
- 保留旧研究门槛、失败分母、来源组隔离、INITIAL/METHOD/FINAL、样本量与多重检验规则；上下文长度、经验命中、状态新鲜度等新增观察项不自动成为新硬门禁。
- 不做RoboRSI全栈迁移、VLA/27B训练、在线自改安全规则；不将计划完成、reader通过或历史API通过写成当前正常物理正链完成。

结构建议：①版本和证据时点；②开题三项内容与RoboRSI借鉴矩阵；③当前缺口与分阶段交付；④公平对照和消融；⑤按验收顺延的11月—4月安排；⑥运行/数据/Git边界。首个当前源码正常正链与合格B0/INITIAL优先，不能因引入经验系统推迟基础闭环。月度计划是目标，不是资源授权或完成保证。

## 验证、真实运行前置与验收

仅stdLib JSON/哈希/链接/diff及内容静态核对，不运行产品import、软件测试、GPU/render/physics/API或服务操作，不读凭据/数据库。步骤报告保存命令、退出码、核查输入、未运行项、限制；phase-summary只汇总本轮。核验三研究问题的适配与比较变量，核验旧门槛/样本/分母/隔离/冻结规则未降低，明确经验包不是在线自主学习。

任何未来真实运行仍须适用Astra计划、当前源码/协议/角色绑定、阶段条件、精确授权额度、资源准入、GPU串行锁、失败清理和独立读出；本文件不替代R469/R470或后继轮。新增观察项不成为新门禁。仅文档质量与可追溯交付可在本轮验收；native、formal、实机和真实正链均不能由此晋升。

交付前检查并行分支/index是否变化，按显式允许路径提交推送并核对local/upstream/remote SHA；不纳入他人staging，不reset、不force。完整raw、DB、凭据、权重、SDK留原交付边界，远端manifest不能冒充完整复现包。

## 规划操作记录

读取与SHA/ZIP/XML解析均只读；产品import、测试、API、GPU、physics、凭据/数据库读取、Git写入均0。首次`python`命令不可用(rc127)，使用已存在`python3`继续只读检查；未安装依赖或修产品。原工具失败保留于对话。

外部依据为ROOT传入的RoboRSI commit `e17ddeebc0ac8b0abc1559032657607a7c67504e`及论文 https://arxiv.org/html/2610.22471v1 §3.1。动作审查跨度4的SR23.61→25.83、tokens减63.5%仅说明该研究的特定设置，不等同事件触发、不作为本项目收益承诺。

## 冻结前补充

R470新终态仅用于当前状态记录，不在本轮分析或修复。新增直接输入：

| 输入 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/full-evidence/result.json` | `e37eb2561ba2a110ccb24f71d27ecabede9d0cd767f8e5ae0190c6983a4face5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/read-evidence/result.json` | `67edaa806a96782a529e0489b19aebbd5cea9ec87d4e191ea4e4ca47f98ee313` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/readout/diagnostics.json` | `e9d349c8e3874122b5cc0c702a7c6b924a964512856e1e32b2877d3de5b4fed1` |

最终核查时点：`2026-11-08T07:30:04.665876+00:00`。开题DOC正文日期同为10/24；较晚申请表的2月冻结/功效、3月正式实验/初稿、4月交付只作条件化排期，不称导师批准、不选择专业、不改变答辩日期。

按六个明确路径交付：新方案、plan.md/json、input-manifest.json、step-report.md/json。本轮阶段总结并入step-report，不另建文件；提交后的delivery-receipt.json仅本地记录local/upstream/remote SHA，避免自引用第二提交。ROOT已核查当前三者同为输入HEAD且index空，实施时重查。

ROOT已只读确认的复用定位：vision/messages.py build_visual_messages；vision/supervision.py SupervisionContext/decide_supervision；planner.py RGBDPlannerAdapter；auto_mode/joint_policy.py JointEvidencePolicy.decide/estimate_action_costs；cloud/replanning/visual_dependencies.py find_repair_window；cloud/replanning/visual_repair.py build_visual_repair(full_remaining=...)；research/cost_ledger.py CostLedger。这里只作未来方案接口定位，不创建第二套执行器，不声称本规划独立检查过这些源码字节。

ROOT另保留只读路径猜测缺失及受限DNS失败记录，后续已找到现存路径/在适用权限上下文核对远端；这些不构成产品修复，本轮不新增运行授权。
