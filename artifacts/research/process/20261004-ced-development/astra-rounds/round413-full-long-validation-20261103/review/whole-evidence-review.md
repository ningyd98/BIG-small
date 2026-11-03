# R413 全证据交付审查

实际审查模型：**gpt-6-astra**；一次 fresh whole-evidence review。审查日期：2026-11-03T15:30:03.024461+00:00。

**Critical 0 / Important 0 / Minor 1；ready_for_delivery=true。** 当前冻结报告与精选证据可进入原定交付门禁。这里批准的是诚实记录结果的交付，既不表示软件全绿，也不表示正式研究验收或 Git 推送已经完成。

核心清单 SHA256：`e71dad71edd611e6e0648faa07824e1357764b461e7b9a405983e7666d3868eb`。6716 个唯一常规文件、40535269 bytes，全部逐项大小/SHA及祖先非 symlink 检查通过；核心路径文本和两份主报告 SHA 均与交接值一致。写本审查前再次全量复核，没有核心漂移。

## 唯一发现与明确勘误

**Minor R413-REVIEW-MINOR-01 — [步骤报告](../phase-step-report.md)第7行的“R413计划先于采集/运行”不准确。** 原采集于 UTC 10:01:26.160542 开始、10:01:29.732885 结束，exit0，purpose 为 READ_ONLY_PLAN_INPUT；R413 计划于10:06:25.429394生成，明确将唯一已完成采集作为冻结输入；行为批次于10:11:58.963126开始。正确顺序是“只读计划输入采集 → Astra计划冻结并复用该采集 → 行为运行”。因此计划先于行为运行，但不先于采集。

该处为局部过程叙述错误：计划本身、采集原件及SHA没有隐瞒时间，未发现倒置修复审批、重复采集或变更测试结果。定级Minor、不阻断诚实证据交付；本审查提供随包勘误，**不修改冻结原件**。以后若修改原报告，仍须遵守AGENTS的新计划要求。

## 主要证据判断

两份主报告及根步骤/阶段总结已全文审阅；现有summary、coverage-ledger、python-outcomes和stage-summary完整读入核对。4753唯一节点中，4751软件节点各STARTED一次，2真实外部数据节点零启动；4709 PASS / 35 FAIL / 6原backend SKIP / 1 INCOMPLETE。全部PASS有setup/call/teardown通过，4737节点有JUnit。442阶段摘要中的result均与对应原文件相等；Python实际418阶段为410P/7F/1TIMEOUT，073/076两个管理slot不入行为分母，非Python22项为14P/8F。

原075 TIMEOUT、exit=-15及14个已启动但无JUnit节点的11P/2F/1未完成完整保留。R414原parent session12273自然guard exit1；R414 session80573在未启动tail资源准备处真实FileNotFoundError exit1；R415最终session24010实际exit0只代表队列终态。R414只对尚未开始的7节点移除共享SIMDB覆盖；R415派生execute与原函数文本及既有AST证明一致，仅资源父目录准备和新tail namespace改变，38未启动节点接续，没有把原模块改成整组PASS。

35失败分类为21个RuntimeSpy接口、1个recapture回调、5个租约交接、2个回执验收、2个事件复现、4个中文规范。目标断言未到达的22项未被当成目标验证通过；租约与事件问题没有越过证据宣称已定根因。94闭环、9个T3、native queue5与legacy4的通过均已包含在4751中。原生MOCK ETEAC/PCSC各attempt1、1.475164683/1.610095120秒、lease/thread/FD清空，只支持开发结论。UTC合计4502.508743957秒，600秒原性能线未达，7200秒诊断额度未替代验收。

浏览器42P/1原SKIP，旧19逐项P，E2E06缺duration保持null。研究fixture600组/4200全blocked、actual research NOT_RUN/formal=false。前端43P及TS/ESLint/build通过不掩盖API/Prettier失败。Ruff1156/42文件、format139/706、Prettier11、中文CLI342及覆盖2330、文档18条未经逐条裁定的规则命中均如实分开。Mypy原stderr直接报告缺py.typed、exit2；报告没有称已完成有效源码类型检查。

Phase12 full运行5024.445008153秒，20实验、5580 raw/manifest行。run/analyze/export exit0与verify exit1明确分开。原verifier为PHASE12_REJECTED、THESIS_PACKAGE_INCOMPLETE、NOT_CLOSED，4项检查false，门控权威行0。raw声明调用/完成/权威4860与blocked720不是已完成研究任务；既有内层审计的900条不支持外层完成，其中F20为180不支持/0支持。精选单元首次回执及full首次F20的3份副本与原始字节吻合；full原始行确有SUCCESS而内层main/duplicate/recovery为BLOCKED_BY_ENV。静态源码确认_draft省略input_mode、模型默认RGBD、MOCK进入RGBD_CAMERA_REQUIRED，而适配器无条件发布成功，支持报告的限定推断。没有把结果解释为5580次成功、18000任务、全部Phase11坏或正式CED通过。

1309运行源码pins当前全匹配；HEAD仍ab18abd0f82a024b62f4423c946c6585f8d18c65、研发分支正确、忽略submodule的tracked diff为空、index为空。main与两个gitlink外层index SHA未变。既有最终清理报告记录1934身份无存活、418前置accepted。采样缺周期cgroup记录、旧R407退出UNKNOWN、历史native patched_worktree标签、11月2日状态页等边界都已明确；不能反推OOM或实体硬件验收。

## R416/R417与确定性元数据政策

阅读五轮计划及输入。R413—R415全部输入pin匹配；R416/R417仅原获授权的未冻结helper按计划发生历史hash变化，其余输入匹配。R417当前helper相对其保存快照，差分仅精确五文件准入与一个未生成README链接修正。exit127及未拦截后继apply_patch事实未改写。两轮step-record的NOT_RUN是helper前快照；local-only helper-terminal记录session22870实际exit0，不能误判最终helper没运行。

重新执行只读NUL check-ignore得到与原审计完全相同的40项，均为授权三轮reports目录中的`.gitignore:64:reports/`，候选与核心6716路径完全相同。R416仅6个精确文件、R417仅5个精确文件，未发现DB/WAL/SHM、cache/tmp/resources、权重SDK、完整批量raw、原敏感扫描stdout或gitlink内部路径混入。三个本地大raw示例的大小/SHA重新核对通过；它们仍不属于远端精选文件。

**接受[交付README](../delivery/README.md)所列政策**：核心冻结；仅追加core-manifest.json、core-paths.txt、本审查两文件、R416/admission/final-ignore-audit.json、selected-paths.nul和selected-manifest.json七项。最终6723条NUL路径包括NUL与manifest自身；final-ignore-audit只列自身路径不自hash；selected-manifest记录其它6722文件（含NUL与最终ignore审计）而不自hash，manifest自身SHA单独放local-only门禁回执。不存在哈希递归，也不需要无限后继review。

新增七项仍须全部通过范围、常规文件/祖先、大小/SHA与ignore检查；只允许相同三reports/规则。随后复核核心/source/HEAD/index/refs，唯一一次literal NUL git add -f及stage blob对账，一次普通commit/push/exact remote三SHA门保持。它不授权force-push、改核心、扩大目录、补stage或额外重试；其它prestage/Git/postcommit回执local-only不二次commit。

## 审查限制与行政记录

本次未运行测试、产品、SQL、仓库解析器、报告生成器、curation helper、Git写入、网络或信号。全部核心文件做字节校验，但不声称逐条人工阅读所有日志；未重新解析完整批量raw或打开运行数据库，Phase12全批计数依冻结审计、原verifier、关键原件和原大文件hash核对。未重复主机/proc探测。完整raw与DB在本地，精选不是完整远端复现包。

审查初始`git status --short`未加ignore-submodules，可能内部只读探测子模块；没有直接进入、列举或读取两个gitlink内部文件，但不能宣称该命令完全未探测内部。后续仅用忽略submodule的diff与外层指针，不写Git。

临时stdin展示命令chunk b75aeb先成功校验全部核心，后因stage-summary为list却调用.items()出现AttributeError、exit1；无文件写入或产品/仓库解析器执行。后续按实际结构只读审阅，未修复/重跑任何长测。另一次ls误查R413/evidence报不存在，随后读取实际reports/evidence。以上是审查行政读取问题，不混入测试分母，也不宣称全部行政命令均成功。

已知产品失败、性能/静态缺口与正式研究阻塞作为后续研发项保留，不人为阻断本次诚实报告交付。当前ready结论不替代尚未执行的最终元数据、暂存、提交、推送及三SHA核对。
