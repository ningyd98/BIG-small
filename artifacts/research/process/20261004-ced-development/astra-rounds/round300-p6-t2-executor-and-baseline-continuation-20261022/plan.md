# R300：执行席位与基线接续计划

**Actual planner: gpt-6-astra。** 2026-10-22；仅计划冻结，未执行任何gate、产品、测试或角色操作。

## 目标、事实与边界

用户已要求连续解决RPC超时与执行链路卡点；不需要逐步重新确认。当前先完成实际席位/HEAD接续、R298元数据和R296原唯一诊断，随后据新首因交实际Astra限定修复与行为验收。本计划不启动后续正式实验。

R289两wait限定通过，dual仍child1/wrapper0且未到commit-loss注入；37420B/7events/10dropped只证明RPC cap→迟答→入口拒绝的观察链，迟答根因未知。R299仅源码准备；R298五输出仍不存在，R296三gate/两角色/预留/运行目录仍不存在。原R289三槽spent；R296原唯一0/1，新增运行额度0。

## 已只读确认

- 当前HEAD `b6b3a8835b149e53cfb41c572aec1bbfc0152bbb`，分支 `research/20261004-continuation`；只有两个原nested physics脏状态。
- `04def61…`是首次收录旧冻结材料的已知Git比较基点，不冒称旧运行时HEAD；到当前195变更路径均在docs/artifacts/output，与有限运行输入集合交集为空。真正释放仍须当前物理pins。
- 已读相关gate/runner/metadata脚本没有直接执行HEAD断言；旧文件/来源/角色/argv条件保持，本轮加当前HEAD与非重叠前置，不改旧期待值。
- 原R296 prerequisite supplement SHA `c5dc9272778f79247bf8d5fd2a2b324f68cebc4638e6b62af707de36fbf326b5`固定，保持；原runner `1371a63d…`、当前plugin `08df0496…`。
- 保存的原完整源审阅4片可逐字重构94400B runner1371；2片可重构30437B旧plugin bca。当前plugin审阅只需R297四处＋R298 EOF证明接续，不反复整仓阅读。

## 1. 真实执行席位

ROOT直接调用spawn_agent(task_name=runtime_repair_sol, model=gpt-6.1-sol, fork_turns=none)，沿本工作区；保存真实完整返回及实际agent canonical name/id，不能把拟名当已创建。若实际返回名字不同，绑定真实返回名字但记录拟名与差异；模型必须确为gpt-6.1-sol。

ROOT确认真实创建及职责接收后独占新AUTHOR角色；本R300明确授权该接任者执行原soleSol职责，不修改旧plan.scope.author或历史native/角色。新身份记录由source-gate.fixed_inputs固定；机器账本仍使用原R296 ROOT/AUTHOR路径和schema，不加入不兼容字段。

角色接续记录保存于 `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round300-p6-t2-executor-and-baseline-continuation-20261022/executor-binding.json`。记录真实spawn参数/回执/canonical/id/model、旧作者不可用、ROOT独立复核、sole writer、原物理账本及同一R296预算。不得改旧plan里的作者名或伪称旧作者仍在。本Astra规划席位不自行变成执行者。

## 2. 直接准备与ROOT门后执行

### S0 — ROOT

可直接创建真实gpt-6.1-sol接任席位、保存spawn原回执和executor-binding；准备本R300有限元数据脚本及完整source/native/argv审阅记录。旧作者身份不改写。

**出口：** ROOT独立确认真实模型/agent与单写者职责；源脚本/两个模式argv已阅读固定。

**放行边界：** 仅准备，无产品/metadata/diagnostic自动执行。

### S1 — ROOT

按commands.applicability唯一执行当前接续元数据核对；复核HEAD195路径非重叠、原30/27/211/8before及实际源/角色世代；复用完整旧审阅，不重跑旧gate。

**出口：** exit0/真实applicability.json。

**放行边界：** 仅使ROOT可记录R298源/native/argv放行，不消耗R296槽。

### S2 — ROOT then actual bound Sol

ROOT依据已完整读的284行R298脚本、metadata-source-native-actual两阶段真实native、原11pins及输出缺失记录r298-metadata-release.json，逐字复制原R298 tool_arguments发给绑定Sol；Sol仅执行一次原脚本，保存原actual到原R298 outputs.actual，独立流未捕获保持null。

**出口：** 原脚本exit0且metadata_complete=true，原R297_expected_match=false、R298_exact_generation_match=true，实际四输出及caller actual齐全；ROOT独立读回为r298-metadata-acceptance.json。

**放行边界：** 失败含部分输出立即STOP，新Astra；不重试、不改脚本。该阶段不是product runtime。

### S3 — ROOT

组合原完整runner/bca审阅+R297四处计数改动+R298唯一EOF证明和真实源；changed regions全读，unchanged仅精确字节证明复用。记录final-source-review，执行publish-gates唯一模式形成原R296尚不存在的三门及新native链。原prerequisite-supplement与context不动。

**出口：** exit0，SG/JG/AG状态和fields按下方契约，ROOT独立读回实际pins。

**放行边界：** 只允许进入原helper角色初始化，不是运行放行。

### S4 — ROOT

使用本计划已读并固定的原root-create-and-reserve-roles.py initialize一次；保持两角色原路径/schema。保存真实初始化回执，初始HELD0/1。随后ROOT再次确认接任者仍为绑定Sol、所有静态pins/HEAD及原literal invocation不变，才执行reserve dual_rpc_timeout_evidence一次。

**出口：** initialize exit0/NEW_ROLES_HELD_ZERO_USED；reserve exit0/SELECTED_ROOT_RESERVED_NO_DISPATCH，ROOT1/0、AUTHOR仍0/1，fullbefore/base64/mode/CAS及reservation真实齐全。

**放行边界：** 仅随后明确literal dispatch；初始化/预留失败或部分写入STOP，不重试、不退款。

### S5 — ROOT then actual bound Sol

ROOT保存diagnostic-dispatch-release并向真实绑定Sol派发commands.diagnostic的原tool_arguments；Sol不增加prelaunch脚本/命令，按同一tool session≤60s轮询，原初始/轮询/终态回执先落盘再显示。原runner消费同一AUTHOR额度并finally结算；不得裸跑pytest或重复已接受wait。

**出口：** 保存真实child/wrapper、JUnit、case/resource、passive、DB/sidecars、hook恢复、源前后及清理结果。原诊断保留必要SQLite临时/保留DB；不新增独立SQL操作。

**放行边界：** 失败/不完整/超时均消耗一次并STOP，0 retry；PASS也仅诊断。

### S6 — ROOT then actual Astra

ROOT独立解释首因与完整性，按原满before/CAS结算ROOT为实际SPENT状态，保存step-report/root-diagnostic-assessment/role-settlement，旧35DB/90sidecar缺口独立保留。根据新真实证据立即交实际Astra下一轮限定产品/fixture修复及行为验证计划，持续用户已授权RPC/执行链闭合，不再逐步问用户确认。

**出口：** 本轮出口是真实诊断证据和可复核根因或UNKNOWN；当前RPC/执行链成功仍需后续原dual commit-loss/受影响T2/T3行为出口与独审，不宣称formal/native全验收。

**放行边界：** 本R300不预授权未知源码修复或新行为额度；后续实际Astra逐根因连续推进。

## 3. 两个有限元数据模式

允许ROOT准备一个普通stdlib脚本 `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round300-p6-t2-executor-and-baseline-continuation-20261022/root-continuation-metadata.py`；完整源/native/两个literal argv一次审阅后使用。每模式一次、≤120s、TERM后5s、stdout≤6000UTF8、同session轮询≤60s、0 retry。它不能import产品或调用原runner的函数。

### applicability

- R300 plan/observation与真实executor-binding pins，当前HEAD/branch/195路径非重叠及既有两个nested dirty边界。
- R296原30输入、8完整before（原件/归档/base64/mode）、原27当前源与211保护项，仅按原R289物理container和已声明context/role映射读取；accepted68仅完整容器hash，不递归重审。
- R298原11输入和before/candidate/actual08df/metadata脚本当前身份；五新输出均不存在，R297失败after/diff/proof/report仍不存在。
- 现runner1371、plugin08df、现c5dc supplement、R289 context c4b/0df与d308/4580旧roles不变；R289三槽spent，R296HELD0/1，三gate/两role/initialization/reservation/diagnostic目录均不存在。
- 已保存完整审阅字符串可重构runner1371与旧plugin bca，R297/R298为有限差异；旧source-index包含bca属原世代，不作为当前plugin pin。
- 精确源mode、原R235模块和原实际CLI参数可读；不import产品/observer、不AST/compile、不SQL或执行原gate。

exit0，status=R300_CONTINUATION_APPLICABLE_NO_RUNTIME_RELEASE；全项命名结果与实际pins落盘。异常或未知不是通过，输出失败原件后STOP。

### publish-gates

- 重新核当前HEAD、实际两个源、原plan/supplement/context/旧roles及applicability固定pins未变；不重复递归审计历史68。
- R298实际退出0/metadata_complete、四输出+caller actual真实存在，原R297 false/actual08df true与五字节差异完整；不能伪造actual{}数值退出。
- ROOT final-source-review已完整覆盖原runner/base plugin复用、R297四处及R298 EOF、原生参数和原诊断literal argv/env/resource/保护finally，准确记录所读位置与实际回执。
- 全部目标输出在纯检查阶段不存在；未来输出/新ledger/reservation不能纳入自身fixed_inputs或成为前置，避免循环。

全检查通过后依次exclusive写native_chain→SG→JG→AG并读回；exit0/status=R300_SOURCE_GATES_PUBLISHED_NO_DISPATCH。失败保留部分实际输出，STOP不重试。

旧R296准备gate要求new source absent，当前源已存在，不能重跑；旧失败e96552或R299准备门也不重放。适用性检查只有限核原30/27/211与完整before/显式世代映射，accepted68保留容器不递归重审。

## 4. 原R296三门的精确接口

不得重写现有prerequisite-supplement或runner常量；新身份和HEAD只通过R300独立容器及SG.fixed_inputs链接。

- `source-gate.json`：round=R296、status=VERIFIED_SOURCE_ONLY；原plan/observation/supplement、真实runner1371/plugin08df；input_check=R300/applicability；native=R300/native-source-chain；context_manifest=原R289/root-context-update。fixed_inputs仅不可变真实pins，排除新角色、SG/JG/AG、reservation及未来/自身文件。
- `script-gate.json`：round=R296、status=VERIFIED_BY_ROOT；SG真实pin；sources与SG相同；commands与原P296.commands逐字对象等同；role_files为原ROOT/AUTHOR两路径；reservation_directory仍原R296/root-reservations。
- `root-final-source-acceptance.json`：round=R296、status=FULL_SOURCE_NATIVE_INPUT_ARGV_ACCEPTED_NO_DISPATCH；固定已保存SG/JG和R300接续证据。
- 顺序必须native链→SG→JG→AG→initialize→reserve→实际派发；不要求未来角色或reservation先出现，不形成循环。
- 旧R296 source-index的bca世代保持历史；现plugin只能以08df＋R297/R298完整证据接受，不能路径级豁免。

## 5. 精确执行命令引用

R298命令逐字继承原 `plan.json/recovery_metadata/tool_arguments`；R296命令逐字继承原 `plan.json/commands/dual_rpc_timeout_evidence/tool_arguments`。本plan.json.commands保存完整对象；不得从本MD自行拼接或裸跑pytest。ROOT role helper两个模式的完整argv也已在JSON固定。

| 动作 | 执行者 | 次数/预期结果 |
|---|---|---|
| R300 applicability | ROOT | 1，exit0/当前接续适用；不释放runtime |
| R298原metadata | 真实绑定Sol | 1，exit0/metadata_complete；caller保存原实际回执 |
| R300 publish-gates | ROOT | 1，exit0/三个gate真实创建；无dispatch |
| 原helper initialize | ROOT | 1，exit0/NEW_ROLES_HELD_ZERO_USED |
| 原helper reserve | ROOT | 1，exit0/SELECTED_ROOT_RESERVED_NO_DISPATCH |
| 原R296 diagnostic | 真实绑定Sol | 原唯一1次、0重试；实际结果如实结算，不预言PASS |

原诊断child600s、cleanup15s/TERM5s、outer900s/KILL15s、faulthandler540s、raw各32MiB阈值及overshoot实报、console≤6000UTF8、被动总128KiB（record98304/metadata32768）全部不变。SQLite临时/保留DB属于原诊断必要资源；无新增独立SQL工作。两wait已接受不重跑，任何失败均spent并停止，不自动补次数。

## 6. 保持项、终止与后续

- 只延续用户当前RPC/执行链卡点；不启动P9/正式实验、模型付费、硬件、全仓宽测。
- 规划阶段仅本R300 plan.md/json/input-observation；未执行gate/产品/测试/角色修改。
- 现有branch/绝对路径保持，无新worktree，不清理两nested physics工作区。
- 旧R296/R297/R298/R299计划/失败/原source-index/native/角色/上下文字节不改。原c5dc supplement无需重建；新增身份/HEAD容器只链接。
- 不修改runner1371/plugin08df/测试193f/leasef71d、TTL/wait/权限/时钟/同步/原断言，不为诊断完整扩大caps。
- R300新增product/diagnostic额度0；使用原R298 metadata一次和R296唯一0/1。R300允许的两元数据模式、原helper initialize/reserve各一次为门禁完成，不是可重复测试槽。
- 当前actor重绑是人/agent责任延续，原R296唯一budget_identity和机器账本路径不变；旧R289三槽spent绝不退额或复制。
- 完整旧68容器保留不递归重审；27当前源/211保护项从指定物理container有限选择，不能泛化任意JSON遍历、目录递归或路径豁免。
- R298原{}native的数值退出/独立流未知保持null；只用真实工具结果，部分/缺失/unknown保持。
- 本轮期间不改R289 state/phase以免固定pins漂移；新进展写R300步骤报告，结算后如需阶段汇总按后续明确范围追加。
- ROOT用户授权的显式提交推送不受旧产品Git0误解限制；在本序列结算后交付本轮相关文件并核三SHA，不声称产品已验收。

- 任一新元数据/原角色helper/实际运行失败或不完整：保存真实退出/partial输出，停止对应动作、实际Astra新计划，禁止同命令自动重试。
- HEAD/身份/输入世代/输出存在性变化且无本计划映射：STOP，不改旧期待值或增加忽略规则。
- 任何新根因、scope扩展、需改runner/product/预算上限：下一轮实际Astra，不借本计划宽泛授权。

ROOT实际诊断结算后立即以真实首因或未解问题请求下一轮Astra，继续当前用户已授权修复，直到相关RPC/执行链行为和必要独审闭合。不得把本次diagnostic PASS、元数据成功或新数据库数量当T2/P6/native/formal完成。ROOT于序列结算后按显式路径提交推送并核三SHA；无需用户再次逐步批准。

## 7. 冻结输入

65项实际输入详见本 `plan.json.inputs` 与 `input-observation.json`（含SHA256、路径、字节数）。观察文件SHA256：`dda1f3364f05f1347cad62f38e274cdb6c53983782e0c307847670b32856bca4`。该观察是规划事实，不是已执行的ROOT gate。

| 当前关键输入 | SHA256 |
|---|---|
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/implementation/run-evidence.py` | `1371a63dc6faf3c784eea25a71a07b2a42320bdca0951f3bbb5ac7038fc19fe3` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/implementation/r296_session_evidence.py` | `08df0496445e5ea39575694e076735bc38c99561510d341f21370a8bae7a366f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/prerequisite-supplement.json` | `c5dc9272778f79247bf8d5fd2a2b324f68cebc4638e6b62af707de36fbf326b5` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round298-p6-t2-plugin-finalization-eof-byte-generation-20261017/implementation/complete-source-evidence.py` | `089206cc8c71f52e3f6f139e4d3c3fac5ae0e759b056244556a0f4895c3b5dab` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round298-p6-t2-plugin-finalization-eof-byte-generation-20261017/implementation/metadata-source-native-actual.json` | `8dc6c5165da8d01b4ad5e474bccf77212f0ed3f12f9c28f57f5b17b7a5b74e7f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round296-p6-t2-rpc-timeout-passive-evidence-completion-20261017/root-create-and-reserve-roles.py` | `471277abd5736460ca82d8af4cc8a4cce5e5b2fa7bc4e0b6b7d9d4351f67d87d` |
