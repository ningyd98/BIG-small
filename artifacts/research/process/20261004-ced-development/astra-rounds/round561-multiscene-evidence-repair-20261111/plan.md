# R561 Multiscene Evidence Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans；父流程一次内联修复，不开启第二次独立整体审查。

**Goal:** 关闭首次审查五项Important，使分类、异常成本及七案汇总只能依据完整可对账原件。

**Architecture:** 保持单研究脚本；统一持久化致命边界和有始有终的调用事件，case与summary复用同一只读证据验证器。原生产调用和返回对象不变。

**Tech Stack:** Python、现有原始provider/transport接口、文件SHA清单、pytest/Ruff。

**Spec:** R558首次review-report.md/json、reproduce.py/supplement.py及其完整结果；实际planner_model=gpt-6-astra。

## 问题与冻结依据

I1：实际零深度经原association拒绝，却被黑名单分类为负案PASS。I2：provider异常时组计数3/3、各案却0；原_post收到非JSON原文后有付费预留及response原件，却无终态且paid_responses=0。I3：首次provider持久化异常后仍委托后两案。I4：mkdir等账本失败未poison，后案继续且组COMPLETED。I5：未配对point start仍PASS；仅七条矛盾verdict、无raw/claims/group报告的目录，summary仍7/7。

已完整阅读报告、两份复现脚本/结果和三份受审源码快照；复核review清单、30项受审输入及R558原24项冻结输入。当前脚本d611aa6…与受审16c8e7…仅导入块排序不同，规范化AST相同；当前原件另存gzip。精确输入SHA与验证映射见plan.json/input-verification.json。保留所有首次失败，不改写审查证据。

## 范围

仅修改 scripts/probe_molmo_multiscene.py、tests/test_molmo_multiscene.py、指南及本轮研究报告。不拆新模块，不改生产/launcher/七案/门限/运行时/资产/模型/预算；R560正确asset七案十帧采集预检已PASS，新增证据只作为前置依据。当前247CPU/Ruff通过不覆盖这五项新缺口。

## 锁定接口与事件

在同脚本新增 `EvidenceCheck`（ok:bool, errors:list[str], counts:dict[str,Any], refusal_source:str|None），以及：

- `validate_case_evidence(case, *, root, registry, response, events) -> EvidenceCheck`：只读实际原件和既有case manifest。
- `validate_group_evidence(group_id, *, root, registry) -> EvidenceCheck`：验证group封存及逐案/组对账。
- `classify_case(case, response, events, *, root, registry) -> dict`：先调用上述case验证器；无裸事件列表PASS后门。
- `summarize(registry, results, *, root: Path) -> dict`：独立重验registry、group、case及raw；不能信传入verdict。
- `RunLedger.poison(reason: str) -> None`、`RunLedger._io(operation: str, action: Callable[[], T]) -> T`：首错锁定fatal；所有持久化/读验操作通过此边界。操作终态的best-effort写入只关闭已开始op，不准开启新委托。

事件schema固定`molmo.interface.event.v2`：root_id、registry_sha256、group_id、case_id（load可null）、request_id、连续seq、op_id、parent_op_id、kind、phase(start/end/notice)、UTC/monotonic、reservation_id（仅load/point/paid）、raw_refs。end额外含outcome(success/error/not_delegated)、error_type/message（本地）、native counters_before/after、started_delta/completed_delta。raw_ref为根内相对path/bytes/sha256；禁绝对/逃逸/symlink。kind包括load/capture/point/stage/paid/pipeline；通知如cloud_entry、fatal不能冒充闭合操作。每次真实委托唯一op；start及预留先持久化，finally记录唯一终态，原异常重新抛出；不可为崩溃补造终态。

## I1：正向识别合法视觉拒绝

删除visual_rejection黑名单。仅接受plan.json列出的**精确stage、异常类型和原始完整消息**白名单；未知默认ERROR_UNCLASSIFIED_REJECTION，绝不为提高通过率扩白名单。association要求真实PointAssociationError、其结构evidence schema/status/reason、frame/RGB/depth/helper SHA及原调用参数一致；tracker要求原ValueError和实际输入观测/grounding绑定一致。grounding异常和所有未解析depth/support-plane错误本轮不在白名单。真实N案因未知原因得到FAIL是可接受结果，不为预期成功扩大白名单。

还须验证原观测checksum/标定/时效、两native POINT绑定、stage顺序、因果异常与pipeline sentinel同一reason。association原像素及已报告component的有效深度必须由保存观测确认；任何零深度/缺失/非有限、上下文或TTL错误均不成功。ABSENT路径也必须有完整capture、对应原生raw解析ABSENT、一次实际started/completed增量及绑定；不能从伪造事件字段推断成功。允许的视觉拒绝只是开发接口分类，不证明特定遮挡/歧义物理根因。

## I2–I4：异常终态、停组、持久化

point代理在委托前读真实provider两个计数，finally再读并记录，即使原point抛错也保留增量和现存raw目录引用；禁止getattr缺失默认为0。返回值原样返回。异常目录从受控native根的唯一新增request目录关联，成功目录还须匹配BoundPoint evidence；无法唯一关联即证据缺口。provider异常先置本次组内存停止标志，禁止新委托；在账本尚健康时，finally先读取计数并持久化原调用终态，再poison并退出组。若终态或其他存证失败，立即poison，仅best-effort保留残件。计数倒退/异常增量或native存证错误也停止该组；正常返回INVALID仅该案失败，可继续独立案。

paid区分reserved、delegated_post、request_observed、response_observed、parsed_success、transmission_state。原raw observer在解析前记录收到字节，因此非JSON响应仍response_observed=1、parsed_success=0。finally保留终态，不把预留/REQUEST回调当已发出；无响应时默认transmission_state=UNKNOWN，明确委托前失败才NOT_DELEGATED。HTTP状态未暴露仍NOT_CAPTURED。不得改transport或加重试；保留原response/异常。

mkdir/open/lock/claim/exists/list/read/JSON及结构校验/write/flush/fsync/begin/end、原始文件和清单I/O全部纳入fatal边界，包括claim前和group.finally阶段。规则性额度/顺序拒绝与I/O损坏使用不同异常；均禁止违规委托，前者保持预算阻断分类。fatal先设内存，再best-effort落盘，写失败不能清除；后续load/point/paid/start一律拒绝。原生产捕获了observer异常也不能清掉ledger状态。最外层try/finally必须覆盖claim/group.mkdir及所有finalize；报告/清单失败仍释放group和ledger锁、恢复包装并关闭session。保留首错和后续终态写错，不把后者覆盖成成功。

组末报告reserved/actual-started/completed/unknown/delegated/received/parsed/unspent及stop_reason；各point增量之和与provider组末计数、原native标记、预留逐一核对。load构造失败且缺原始开始标记时actual记unknown，不从预留造1或0。额度剩余按cap减预留，不回收失败。fatal后其余固定案明确NOT_RUN，组INCOMPLETE；不是COMPLETED。持久化失败无法封存时只保留现有残件及stderr，summary不得补救为PASS。

## I5：封存与共享验证顺序

1. 每案原pipeline-return落盘、finally关闭调用和case claim后，写一次case-evidence.manifest.json（root/registry/case身份+原件引用）。记录必须包括task/scene、每capture完整request/RGB/depth/mask、所有开始/终态/预留、实际native目录、实际cloud字节与pipeline-return；按操作状态要求成功原件或错误原件，不只扫描现存文件。
2. 验证manifest及原件后才分类；结果文件单独写。保留原response对象不加字段或替换合同；派生结果仅引用其序列化文件SHA。case manifest不含自身或后写result，避免循环。
3. 组结束先独立对账，再写group-end、所有固定结果/NOT_RUN说明，再一次封存group raw-manifest.local.json，覆盖本组case/result/group-end、native、root下属于本组的claims/events/reservations及registry身份。清单不包含自身，允许排除runtime-cache及锁文件；必须列明必要文件，不能以遗漏字段绕过。
4. summarize只读已有manifest和原件，验证root/registry封印、固定七案身份/类别/顺序、group-end状态及计数、必要文件存在和大小/SHA、无未登记额外操作。逐case重算检查并比较result的passed/verdict/outcome/counts；矛盾即无效。路径逃逸、未知/重复、未配对/重复end、丢原件、hash变更、计数不符一律阻止PASS。不得调用_manifest补写“成功清单”。输出新的派生summary检查报告可以，但原manifest不可覆盖。三组缺失/失败仍七行，分母3/4/7，all_cases_pass=false。

query顺序须由静态task生成exact phrase/hash，初帧target→destination、P补帧同顺序；拒绝可停在合法前缀。验证原始token/raw/result三者绑定、parser状态（含reached_cap）、观测ID/episode/calibration/sim_time及cloud前后采集顺序。时效按记录的调用边界和原返回证据检查，离线summary不拿当前墙钟把历史有效结果变旧，也不重规划。

### Task 1：保留失败并写完整RED

- [ ] 将两份原复现按同一实际调用路径移入本轮测试，断言I1不PASS、I2失败增量保留且malformed收到1解析0、I3首次provider失败后0后续委托、I4任一持久化错误fatal/释放锁、I5残缺证据绝无PASS。保留原脚本/结果不改；新接口导致原探针不能直接调用时仅在新测试适配参数，不伪称原探针原样绿。
- [ ] 参数化故障：point调用前/生成后/完成后存证；paid非JSON/HTTP错误/REQUEST或RESPONSE存证失败；mkdir、锁open/flock、claim、enumerate/read/JSON、begin、end、fsync、group报告/manifest失败；终态写入也失败。证明fatal不可复活、每个已委托预算保留、锁均释放。
- [ ] 从完整CPU磁盘夹具删除/篡改一种证据：start/end/reservation、capture文件、native结果/文本/tokenIDs、云字节、pipeline-return、case/group清单、group-end、root封印；加未知/重复op、错query/同帧两查询、结果passed/verdict矛盾。验证case及真实summary CLI均拒绝。另有完整阳性/ABSENT/白名单几何证据通过，禁止测试特权绕过验证器。

### Task 2：按上述契约修复一次并GREEN

- [ ] 先运行并保存RED，确保是真行为缺口不是坏fixture；随后只改指定单脚本和测试。修复期间既有原对象身份、无真值泄露、同组resident/逐案session与预算测试仍成立。
- [ ] 新故障测试及原247组合回归GREEN；Ruff和git diff --check通过。分类/计数/summary检查复用生产原实现及CPU桩，实际模型/网络0。将五项逐条对应GREEN证据，关闭这次首次审查的发现，不启动第二整体审查。

### Task 3：运行门与交付

- [ ] 指南明确事件/manifest版本及unknown含义、组停机和严格汇总；更新source登记包含R561计划及最终脚本/测试SHA。旧受审raw保持旧schema，不升级/补造；真实运行使用修复后新独占注册根。
- [ ] 结合R560七案10帧正确资产预检、原R545 ABI/权重/profile/resources/共享锁通过后才恢复R558三个worker运行门。既有中文docstring失败仍披露。仅源码/元信息/派生报告按明确路径提交推送并核对三端SHA，完整raw仍local ignored。

## 前置和验收边界

原app绝对解释器、worktree cwd与PYTHONPATH=<worktree>/src；按需scoped写入。新根因或生产/预算扩大另交下一轮实际Astra。开发验收要求五项对应RED→GREEN、完整有效正例不退化成全拒绝、故障不继续消耗且summary不可从残片造PASS；CPU证据不是实际七案。规划0实际调用；历史4/10/2，本轮剩余+3/20/3，累计上限7/30/5；0重试/硬件/正式。没有待定接口。

## 补充前置证据（输入已核验）

R558/capture-preflight-r560-report.json记录七案十帧PASS_CAPTURE_ONLY、102本地raw文件清单、三个P双帧同session且物理状态不推进；本计划核对报告与assignments SHA，102原件核验由父流程完成。runtime-preflight.stdout记录IMPORT_AND_CPU_ABI_PASS、cuda_initialized=false、0load/0generation/0paid。二者及stderr/assignments已追加plan.json精确SHA。它们不替代修复后的CPU验收，也不证明实际七案模型或云端结果；运行前仍需复核当前源码身份、资源、锁和profile。
