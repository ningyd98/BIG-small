# Astra Round83：AGENTS.md 新策略文档前置限定恢复

规划 gpt-6-astra；准备实施 gpt-6.1-sol。状态 PLAN_ONLY。本轮只新增本目录计划、有限只读观察及pins；未修改产品/原件/Git，未运行测试。

## 问题与真实证据

原失败 `t12-sol-handoff-20261007/delivery-rw1/preparation-failure-1.json`：在 explicit candidate selection/static dependency closure 阶段，stdin第69行 AssertionError，exit1，原tool chunk `ccb59a`。这是候选准备前置失败，尚无branch/copy/stage/tests/commit/push；原收据不得覆盖。

本代理独立只读核验：交付worktree `/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall` HEAD为 `4d40a65059ab75292fa1842bacf62653829808e6`，porcelain status空，symbolic-ref -q HEAD返回1/空输出，符合detached状态。base的AGENTS.md不存在；base→用户1007的该路径变化为A。primary当前AGENTS.md与1007内文件均1774 bytes，SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`，字节相等。pyproject.toml和configs/research/recovery_faults.yaml在base与primary各自字节相等。命令与结果存readonly-observation.json。

根因：预检把“所有策略/配置文件必须已在base存在且等于当前”错误应用到了用户1007首次加入的AGENTS.md。它是用户已提供的研发规程，R77/R81已依赖，允许作为明确新增策略文档导入；不能把缺失伪记为base已有，也不能因此一般化放宽其他文件前置。

## 有限输入SHA256

完整路径和bytes见input-pins.json及plan.json。以下7项实施前逐字节复核：

- AGENTS.md：`8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- pyproject.toml：`b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c`
- configs/research/recovery_faults.yaml：`fbe896fe5cbb5746b1abf500c59f3e6b490f65f32d89ecf2c2bdf662c59b8c44`
- 原preparation-failure-1.json：`34290cd0c67d582b6fb728c1329a97ec74bd9ac2f3426a6ba5ecec79517e8f6b`
- R77 plan.md：`e257da0697374bc961e1bb6f2918d12df772214d7b8c4fb3baa0ddd9fe918c4a`
- R81 plan.md：`320207db652f8b5b8c764ea4b699dd1dbf125c9ee886a696bc68ff0dad947d9b`
- 本轮readonly-observation.json：`1957ecfb7196b5bd258e940ed8004c28b80547685699fe0930b1876b1aa9642e`

## 限定实施步骤

1. gpt-6.1-sol先复核上述pins、交付worktree仍detached固定base且clean，以及R77/R81有效。保留原失败文件，只在新执行收据记录恢复。本代理未读取准备器源码；stdin69及执行上下文来自真实原收据，实施者须定位原条件而不能凭行号猜改其他逻辑。
2. 仅将精确路径 `AGENTS.md` 从“base既存且必须相同”集合转入明确新增文档集合。该特例同时要求base确实无此路径、primary与用户1007该blob字节相同、SHA/bytes等于本计划冻结值。用独立显式条件验证，不能删除整体assert、catch后继续、对所有不存在路径直接pass或仅凭basename匹配。
3. 在候选manifest新增且只新增该策略文件条目：target=`AGENTS.md`，change=`A`，semantic_role=`NEW_PROSE_OR_METADATA`，provenance=`user commit 34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e / AGENTS.md`，bytes=1774及上述SHA，reason=用户研发规程及R77/R81执行依据。它接受严格文档质量检查，不作为VERBATIM_EVIDENCE空白豁免。把原始字节复制到隔离候选，之后重验源/候选/staged blob相同；不改primary AGENTS、1007、用户主branch或脏嵌套树。
4. pyproject.toml、configs/research/recovery_faults.yaml和所有其他未变更源码依赖继续原base存在/字节一致验证；没有额外新增文件例外。重跑一次失败的候选选择/静态依赖预检，将真实argv/exit/输出及本次AGENTS分类修正写入新收据。若剩余条件失败，保留现场并交下一轮Astra，不按此单一特例放宽。
5. 通过后恢复既定R77/R81流程：完整明确路径及依赖闭包、语义类别和逐blob pins；完整cached check保存真实退出码，原件空白仅按R81逐项说明且未分类=0；严格当前代码/新文档子集exit0。既定66项candidate closure验证仍只执行原计划的一次，不因本策略文档添加重复产品测试或改变分母。后续commit/push仍由ROOT最终执行，核验base祖先、1007非祖先、范围与受众、明确non-force refspec及交付branch本地/upstream/live远端三SHA。
6. 新步骤报告写明“base缺AGENTS→按冻结用户规程明确新增”，汇入阶段总结。计划、原失败、新观察/恢复收据及报告仅按明确路径进入相应小证据候选，不递归打包本目录或其他文件。完整raw/DB/权重/SDK、秘密及无关文件继续排除，不把manifest称为完整远端复现包。

## 验收与停止边界

此次恢复只证明新增策略文档前置分类正确；不证明软件或真实研究新增通过。验收要求原失败保存、AGENTS精确字节且base缺失事实记录、其余依赖比较未放宽、失败预检真实通过，并继续全部R77/R81门槛。发现hash漂移、新根因、未审新增文件或计划外失败时停止受影响准备，实际Astra再规划；OC2独立工作继续。

actual=0，formal=NOT_ACCEPTED。本轮不运行模型/采集/产品测试，不增设真实运行授权；未来actual仍须既有ROOT串行调度及Gate C/D、精确源/环境/租约/完整原始分母前置。本轮没有自动审批拒绝，不额外请求用户重复批准这个既有规程文件的限定研发交付。
