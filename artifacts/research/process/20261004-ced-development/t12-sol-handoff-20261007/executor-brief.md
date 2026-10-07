# GPT-6.1-sol 首批任务：P1

先读本文件与AGENTS.md。原设计：docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md。仅执行P1，逐子项返回可独审交付；不自行推进P2或actual，不派子代理，不提交/推送，ROOT独审后负责Git。完整报告写本目录executor-report.md，原子项证据仍在原round67/71规定目录。新问题先发消息给ROOT并保存原始证据，禁止自行修复。接单先回报读取完成、输入检查范围、首次将执行哪项和可追踪报告路径，再继续工作。

## 2026-10-07 执行责任与基线

- 实施模型：`gpt-6.1-sol`，reasoning_effort=`high`，每份派单记录实际agent ID；这是调度请求参数，不冒称独立核验了服务内部模型身份。
- ROOT负责队列、不同作者独审、actual资源调度及Git交付；实施者不派子代理。新问题/计划外失败/范围扩大先保留原件，由ROOT调用`gpt-6-astra`生成新的plan.md/json，复核后交Sol修复。已批准预期RED沿计划进行。
- 用户本轮委派指令替代旧计划只允许ROOT实施或复用旧线程的编排限定；技术边界、冻结原件、运行次数和ROOT-only actual不变。先保存实际作者移交，不假称旧线程恢复。
- 现有目录是普通checkout，并非独立worktree。为保留未提交/未跟踪活动源及原冻结路径，本次原位单写者、逐任务source-before快照；不从干净HEAD覆盖当前状态，不stash/reset/clean。研发分支为`research/20261004-continuation`。
- 只读实核本地/上游/远端均为`a98356c75aafe16a32fe57040ca411ae15370c2b`；旧be1c10cd待推描述是历史。各项交付后重新核对三端SHA。
- 当前danger-full-access/approval never；不传sandbox_permissions。旧require_escalated条款是旧环境记录，不是本轮参数。
- OC2原57/61保持；round69元数据恢复完成，round67源码已有活动增量，已登记63目标case，尚未看到新的完整GREEN收据。
- RW1新82/82 GREEN及mypy通过，两个owned源仍匹配round71输入；待格式、窄回归和他人独审，不重跑82例或mypy。
- Max成功链路继续复用；2026-10-06文本请求只补可用性，不替代当前双图角色/source冻结。4807/4807只证明保存帧OBSERVED。

## 分批执行与状态管理

| 批次 | 任务 | 可检查交付 | actual前置 |
|---|---|---|---|
| A | P1，随后P2/P3软件 | 已知失败收尾、动作可达性合同、角色差异 | 首批CPU与只读 |
| B | P4→P5→P6 | 真实来源前缀、窗口、生命周期 | P1独审与P2合同 |
| C | P7→P8 | 完整动作校准与三个native消费者 | 单组原件合格后才至少九独立组 |
| D | P9→P10 | 机会/200故障、B0、新120、INITIAL、风险 | 角色/native/预算/独立池 |
| E | P11→P12 | T12开发准入与32个预登记episode | INITIAL/risk/selection/native与软件独审 |

P1/P2/P3依赖上独立；同工作区代码仅一个实施者写，只读审查和规划可独立进行。P1的OC2/RW1分别验收。P2发现关键动作无支持路径时停止依赖批量，独立工作继续。actual始终先满足任务所列条件，由ROOT唯一串行调度；无凭据或资源时如实记录，不写入、打印或复制secret。

每任务状态为READY→IN_PROGRESS→AUTHOR_VERIFIED→INDEPENDENT_REVIEW→VERIFIED→DELIVERED。新失败NEEDS_ASTRA；前置缺失WAITING_PREREQUISITE。软件、实际来源、物理、正式研究分字段。恢复工作先读台账，禁止重派已完成任务；新的派单不重置旧命令次数。

每任务保存input-check.json、source-before、完整差异及source-after、命令argv/cwd/非敏感环境/退出码/原stdout-stderr、测试唯一节点分母、SHA256、step-report.md/json和delivery-paths.txt。独审使用完整before/after差异，不能只用git diff HEAD判断有未跟踪源码的本轮改动。已通过且源仍适用的测试不重复运行。独审不能由实施作者自认完成。

不承诺固定工期；运行预算以对应完整实际路径证据为准。T12软件/实际开发/正式研究不是同一出口，METHOD/FINAL/T13和统计收益仍另列。

## Global Constraints

- 云端Qwen3.8-Max已有真实成功链路；复用已有endpoint/profile/secret引用，不索要聊天明文、不重新配置账户、不重复通用35call探针。只验变更角色/源/坐标/成本绑定。
- 边缘模型选型后置；保留用户相机、可见标记、控制器和唯一SkillExecutor/SafetyShield。640×480等开发采集域不得静默冒充默认320×240云图/资格域，实际intrinsics和变换须注册。
- 保留10mm、普通/condition5秒、5000ms接收年龄、1000ms未来规则；0.005秒为SimulationS采样gap，不等于连续速度证明；coverage=0.9，至少9独立支持组件才能出现有限分位。
- D为真实操作计数、含适用suspend语义；S为同backend/episode物理模拟时间。完整未来H_D不能由sim timeout、过去均值、resolution或A/B历史slab推出；缺支持UNKNOWN。
- 原任务/恢复预算、deadline、retry、no-progress不刷新；deadline等值拒绝。抬升≥50mm、保持≥0.5sim秒、释放后完整区域稳定≥1sim秒。硬停止独立。
- 所有方法provider在途上限1、最新待发有界合并；B0周期0.5/1/2/5秒；静态≥90%、整体≥80%、物理违规≤1%；INITIAL不选N。
- 不把source哈希、public bool、caller有限数、观测帧全OBSERVED、软件测试或独立教师真值当native/实际方法权限。原UTC路由、旧冻结及全失败分母保持。
- 最新活动实现可能已超过历史报告；实施前仅核对实际受影响输入与最新验证收据，不覆盖活动代码、不要求全仓安静、不因源码已出现就记PASS。
- 新产品根因/扩大范围/计划外行为失败先Astra；本计划预先包含owned代码的正常ruff格式整理、同一已命名fixture根因修正、独立线程容量不足的root内联回退。若行为AST、断言意义或授权范围变化，不得冒称常规修正。

## Review Focus

1. 缺目标/遮挡/部分可见物体：P8三反例保证缺目标0动作、完整范围不足UNKNOWN，不用离线真值在线补PASS。
2. 主动物体搬运与参考漂移混淆、S/D混用及缺full future：P2/P7/P8固定目标与mutable contact反例，不能制造finite/0。
3. 晚回复、取消、模式/candidate变化与lease重新分配：P5/P6/P11提交再次读取，原deadline不刷新，ACK不等于start。
4. 伪scope/source/软件flag/规则概率及费用：P3/P11/P12拒绝假权限、规则不冒称模型请求，所有已发送超时/retry入账、账单未知null。
5. 同component伪九组、失败组丢失、正式标签泄漏：P7/P9/P10保持infinity/原分母、组隔离与正式label只离线。

---

### Task 1: P1 — 复用既有round67/69/71，关闭当前限定失败

**唯一交付/入口：** 先核对最新完成收据及精确source版本。已看见OC2失败归档实现增量，未取得新GREEN收据前不声称完成；禁止从旧失败快照覆盖活动代码。

**依赖：** 无；可独立开始

**Files:**
- `REUSE astra-rounds/round67-oc2-green-partials/plan.md`
- `REUSE astra-rounds/round69-oc2-preflight-metadata/plan.md`
- `REUSE astra-rounds/round71-rw1-static-format/plan.md`

**Interfaces:** 完全继承这三份计划；RW1→RW2/3继续继承round57-recovery-wall，不为同一mappingproxy/终态/fixture/格式根因另造产品接口。

- [ ] **Step 1:** 读取最新failure→Astra→implementation→verification链；按结果分已完成、待验证、未实施，并保存有限输入核对。
- [ ] **Step 2:** 仅执行原计划尚欠步骤：OC2 partial原件/失败分类；RW1既有82例与静态最终门。已完成RED/GREEN不为新计划重跑。
- [ ] **Step 3:** 各自冻结静止owned来源并独审；恢复wall接teacher依旧等OC2所保护teacher窗口释放，独立文件可继续。

**验证/实际命令：**
- 执行原round67/69/71中的精确命令及原次数上限；本计划不额外增加一次全套GREEN。

**验收出口：** 两个独立出口：OC2软件/失败分母可供P4；RW1软件可供既有RW2/3。方法/真实source仍不晋升。

**失败停点：** 出现不同产品根因、source漂移无法解释或失败分母丢失，保留原输出并下一轮Astra；纯既有格式整理按已批准范围完成。

- [ ] **交付：** 保存本任务局部报告、原始命令/退出码/完整stdout-stderr、输入输出SHA与actual分母；按下述显式路径Git规程提交。

#### P1a：OC2的准确接续

**只准修改：** src/cloud_edge_robot_arm/research/operational_capture_v1.py、src/cloud_edge_robot_arm/research/operational_prefix_v1.py、tests/test_operational_capture_v1.py。

- [ ] 读round67/69计划、round69恢复收据、round67/implementation/recovered-source-before.json与test-registration.json；核对当前增量，记录GPT-6.1-sol接手。已完成元数据恢复不重做。
- [ ] 完成原异常持久化/partial/精确终态分类；primary与secondary分列，不修改通用terminal mapper，不笼统放宽断言。
- [ ] 继承61基础+2新增的63case登记；原验证次数仍有余额时只跑一次完整GREEN，同进程保留JUnit节点。发现已有运行先复用原件。
- [ ] GREEN后运行原计划尚欠的Ruff check、format --check、mypy及四文件R03回归，各至多一次。原计划允许的纯格式整理不改语义；新根因先Astra。
- [ ] 冻结九路径与原件分母，局部报告交独审；最高作者状态OWNED_SOFTWARE_VERIFIED_OC2_TASK23_AWAITING_INDEPENDENT_REVIEW。actual仍0。

#### P1b：RW1的准确接续

**只准格式修改：** src/cloud_edge_robot_arm/research/protocol_generation.py、tests/test_protocol_generation_sources.py。

- [ ] 读round71和round68原82例/mypy/静态失败，核对bounded pins，保存作者移交和两文件before。
- [ ] 在新的round68/round71-static中运行原指定两文件ruff format一次；保留全diff并证明完整AST、参数/装饰器、类型注释与断言字符串等价。
- [ ] 通过等价检查后Ruff check、format --check各一次，再运行原pending_regression窄选择一次。新RED/82GREEN/mypy/collect-only/platform/actual均0次。
- [ ] 冻结两源，明确原测试hash与格式后hash的等价证据，交不同作者独审；最高作者状态VERIFIED_RW1_TASK1_AWAITING_INDEPENDENT_REVIEW。RW2/3和恢复0002仍须后续前置。

**两个分支的完整命令合同：** 本次交接目录p1-command-contracts.json复制了round67/71原verification的完整argv/env/max_runs。执行前核对原plan.json SHA，按剩余次数执行，不能因换模型重置。共享teacher/backend/OC1和原worker/schema保护范围保持。
