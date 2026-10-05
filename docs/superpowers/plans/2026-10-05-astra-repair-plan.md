# 云边端真实证据闭环修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已授权全部研发与当前并行执行；沿用已有执行安排，不重新请求确认或选择方法。

**Goal:** 尽快完成一次完整动作逐步采集及离线解码，随后打通真实 RESET/UTC、应用所有权、独立校准和实际消费者，最终完成原云边端研究各冻结与验收门。

**Architecture:** 先沿已经修补的 V3 开发诊断路径取得完整原件，独立推进 native RESET/UTC 来源及 Max 角色配置。native 准入始终由实际应用工厂、同一 recorder/owner 和独立原件重建，端侧证据、既有控制器、规则边缘与 Max 共用原研究边界；基础证书不等待 INITIAL 后的风险训练。

**Tech Stack:** 当前 Python/MuJoCo/OpenCV、应用 repository/lease、RawV3 与既有控制器；官方固定 Go Roughtime 协议实现加小型本地 wrapper；真实 Max API；现有统计及前端工具链。工具链/服务可用性均以实际验证为准。

**Spec:** `docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md`、继承的 `2026-10-03-rgbd-evidence-research-design.md`；总体任务映射见 `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md`。RESET/UTC v2 设计以其独审的三项修正为准。

## Global Constraints

- G0：已发生感知/模型/动作阶段100%真实；泄露、伪装成功、跨组重复0；不可用BLOCKED，未发生NOT_EXECUTED。SOFTWARE、REAL_CAPTURE、REAL_VLM、PHYSICS分别报告；正式验收仍为false。
- 最大模拟采样gap `0.005s`、几何阈值 `0.01m`、校准coverage `.9` 不改。模拟采样gap不是UTC精度；签名有效、UTC区间有限、消费者实际期限可满足是三个不同结论。
- G1：正确识别且有效深度目标定位P90≤10mm，另报覆盖；独立静态抓放成功≥90%。完整物体、抬升≥50mm并保持≥0.5秒、释放后稳定≥1秒；在线完成与独立物理成功合取。
- G2/C1：对B0云请求均值减少≥30%；成功差单侧95%下界>−3百分点、安全差单侧95%上界≤+1百分点。G2a字节减少≥25%、失败惩罚耗时P95减少≥15%，分开判定。
- G3/C2：对B3误放行减少≥50%且绝对≤2%；有效安全机会错误拒绝≤5%；UNKNOWN单列。G4：200故障恢复成功≥80%、失败惩罚恢复耗时中位数减少≥30%、已完成不可重复动作重提交0。
- B0四周期0.5/1/2/5秒；selection静态≥90%、整体≥80%、安全违规≤1%。无合格者为NO_FEASIBLE_BASELINE，不能用低成功率证明节省。
- 数据100/1000/10000组与80/5/5/10来源组划分；selection、基础120、功效另120、正式候选2400、恢复200、域外300及其全部派生帧隔离。正式N∈{600,1200,1800,2400}，12层均衡、层内固定前N/12。
- 原三任务层×RTT0/100/300/600ms、丢包0/0/1/5%、RTT±20%、10Mbit/s及3/10秒中断保留；速度0/20/40mm/s、深度噪声0/2/5mm、无效0/10/30%、遮挡0/20/40%按原规则分层。
- 顶视默认320×240、RGB uint8、optical-z float32米、同backend/episode、完整时刻/标定/hash；已授权开发640×480/960×720须独立登记，不自动成为默认域。等待期间物理继续；通过actuator/step动作，不写物体位姿。
- Tcap为合格B0成功P99×2向上10秒取整并夹[120,600]；Rcap=60秒。α=.05、power=.8、Holm、分层场景聚类配对bootstrap≥10000次、95%区间及零事件单侧界保留。N>2400/区间不足为INSUFFICIENT_EVIDENCE，不追加至显著。
- 云模型保持qwen3.8-max，边缘型号后置；每provider在途≤1，最新观测有界合并。规则不冒称模型，云/边角色与实际位置分列；未知权重/服务版本/费用/纯推理时间为null。
- 已分配、失败、UNKNOWN、排除、超时和未完成记录不删。旧11/10/1、诊断末copy失败和旧teacher10个动作边界观测均不得升级。新目录/名字不创造独立组。
- 本文仅计划；不修改旧冻结原件、core/tests、阶段文件或Git，不执行renderer、physics、decoder、provider、UDP、下载。后续执行每步局部报告→root阶段汇总→显式路径提交推送并核验远端SHA；不整体暂存活动代码。
- 单GPU/renderer实测串行。真实硬件NOT_STARTED，S3/S4 LOCKED；G5、Isaac、腕部相机、缓存为资源允许的独立扩展，不挤占核心。

## Review Focus

1. 原journal存在额外失败或悬挂BEGIN而summary仍成功：R1用原六反例和4 allocated/3 saved控制确保拒绝、全分母保留。
2. prefix提前创建planner或伪造adopted owner：R3覆盖planner_factory调用数0、真实lease失效和unbound导出，无模型调用。
3. 签名通过但量化/整段slab过宽、重启换domain：R2/R3/R5分别验证条件区间、期限可行性和三个消费者保持UNKNOWN，不能以finite替代valid。
4. 重命名/共享来源组或漏配失败让九组统计虚假有限：R4按connected components计数，9组任一不可用不得给有限分位数。
5. 错目标/遮挡/晚到回复与恢复ACK被误当成功：R5/R6/R9测试第一动作拒绝、完整范围UNKNOWN、旧版本0提交、ACK不等于实际启动及完成不重放。

---

## 已查事实与先后取舍

**已修复且限定软件通过：** 第53步状态保护dtype P2、UTC恶格式 P2，root分别62/61项CPU通过；不重新实现这两处，也不累计重叠测试数量。**正在修复：** V3作者报告90项通过、原六反例GREEN、120/9/2 coverage及首model前来源验证；最新已收到FINAL QUIET、root已派独立scoped review，尚不登记为独审通过或实测；32来源440598字节/21环境pins。Python时钟只有partial schema/slab和14 missing-module RED，子集exit0尚未复读/static；RESET模块未写。Go只有固定commit `75645289794cfbd71a08f0e7ecf9bc4f3f87d133` 的最小官方源，无wrapper/fixture/build。

**待真实验证：** 完整V3 actual与decoder、真实RESET和外部时钟、app-owned有限正分支、至少9个独立支持组、三消费者、G1、机会/200faults/B0和INITIAL/METHOD/FINAL。**外部配置缺口：** 已查默认app DB 0 profiles，dashboard只有10个E2E profiles；三个指定secret env当时presence=false，无定位到的运行app。未扫描外部账户或内存，不能宣称用户全局没有key。不重复已问的配置问题，不伪造profile或偷偷换模型。

反复审核的已知原因是原fixture未覆盖完整操作身份/全journal分母、真实MuJoCo owning getter与view混同、RESET没有原时钟、native工厂缺真实catalog/owner，以及Max无当前可启动配置。用这些具体缺口作有限任务，不以再造通用守卫结束工作。

原研究要求的是来源真实、组隔离、原阈值与统计；32/33源归档数量、固定类门、UTC sidecar/签名slab、附加state guard是后来为当前实现提供证据的工程手段。已约定守卫不得直接删除；可以删掉重复的全仓hash/全套复跑/重复审同一字节流程：每个静止提交一次定向检查与独审，修改只回归受影响路径，actual独立重算。V3完整诊断无需等待UTC、Max或九组证书；native UTC无需逐物理步发UDP；边缘模型/第三套执行器不作为前置。

尤其，partial时钟实现 `QUANTIZATION_NS=1_000_000_000`，整段causal slab还包含实际采集时长。它能提供条件有限区间，不保证满足现有TTL/deadline；在首prefix就量化此差距，不能先花九组采集成本再发现不适用，也不能用RTT/2、NTP同步标志或caller accuracy补精度。其他UTC来源只有在其独立原件、转换及source policy成立时才可另立版本；不可静默混用不同草案/issuer。

## 文件与执行责任

所有执行命令均从仓库根 `/home/ningyd/文档/ChatGPT/BIGsmall` 运行，统一设置 `PYTHONPATH=src:.`、`PYTHONDONTWRITEBYTECODE=1`；使用仓库 `.venv/bin/python`，避免误用已安装旧包或生成Python缓存。Go命令仅切换到明确的tools子目录，沿已验证绝对工具链路径和独立临时build/cache目录。实际渲染命令另显式 `MUJOCO_GL=egl`。

下文源码简写 `S/` 严格指 `src/cloud_edge_robot_arm/`，产物简写 `A/` 严格指 `artifacts/research/process/20261004-ced-development/`，V3简写 `V/` 指 `A/t7b-continuous-visibility-v3/`。这不是新的目录。命令中使用完整真实路径。新任务产物固定在 `A/astra-repair-execution/R01` 至 `R10`，每项含 `report.md`、`report.json`、命令/exit/stdout/stderr、输入/输出SHA及实际调用全分母。必须新增的CLI明确标“待实现”，现存CLI也不被视为已验收可运行。

主依赖：`R1(actual+decoder)`优先；`R2→R3→R4→R5`与`R6(Max)`并行准备；`R7`离线证据准备可并行，实际队列串行；`R5+R6+R7→R8→R9→R10`。R9已有T12/T13作者可继续其独立软件工作，真实验收等待R8；不得反向阻塞R7的离线教师或R8基础B0。主线仍T12/18、T13并行，不以本文编号改写旧任务状态。

V3 quiet handoff pins：runner `0f7c5d31f21bd35a5d7085e57376436b6bf33f043c47fe227542d6d94d654340`；reader `35ae741fa995715749133485eab4ef6ec70e28a9854de440e8489bd68f65314e`；tests `f1b47d4af307b286ab34782db6874233227e8103448d40d5d8b7069183badf7c`；fixheader `5b9378778ae38188cfea824a004ef432375cd33fe85955f05e877605c3066de9`。本计划输入表另记录本地读取SHA。准备已经完成，不重跑prepare。

### R1：封口本轮V3，然后立即完整actual与decoder

**Files:** 复核现存 `V/run_once.py`、`V/verify_offline.py`、`V/test_cpu.py`；只读 `V/independent-reader-probe.py`及首版冻结源；新协议/报告使用现有 `V/fix-round-1/`，实际输出 `V/fix-round-1/attempt-1/`、解码输出 `A/astra-repair-execution/R01/offline/`。不把脚本误放到fix-round-1。

**Interfaces:** `execute_once(protocol_directory=None)` 使用既有单attempt guard；`verify_attempt(input_directory: Path, *, output_directory: Path, decode=False)` 从原journal重算。消费作者quiet源/pins，输出完整或明确失败的120 settling/9 actions/2 dwells原件和逐帧decoder结果；不输出native认证。

- [ ] 收取作者quiet SHA和本轮精确变更；核对原六反例未改、raw ACTUATOR upcoming=n而CONTROL/PHYSICS BEGIN=n−1；作者已经实现的join/分母/recipe/首操作前runtime来源检查只验收，不重复开发。若发现新增真实缺陷，先保存反例再最小修改。
- [ ] 在静止版本运行 `.venv/bin/python -m pytest -q artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/test_cpu.py` 和 `.venv/bin/python artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/independent-reader-probe.py`；baseline通过、六反例拒绝、4/3/1保留。Ruff只查三份owned Python，独审一次源/pin/真实操作前顺序和完整recipe控制；仅软件静态问题不变成无限全仓审核。
- [ ] 确认actual目录尚不存在且32来源/21环境pins与当前真实imports一致后，运行 `MUJOCO_GL=egl .venv/bin/python artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/run_once.py --protocol-directory artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/fix-round-1 --execute-once`。不人为强迫失败teacher继续，不补帧，不重入attempt。
- [ ] 无论退出码都先保全并重算原件。运行 `.venv/bin/python artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/verify_offline.py --input artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3/fix-round-1/attempt-1 --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/offline --decode`；完整性不通过则decoder保持拒绝，并明确本次实际decoder调用为0。通过才逐帧解码，报告OBSERVED/UNKNOWN、完整gap/动作/dwell/独立物理结果与资源实测。
- [ ] 局部报告独审后交root显式提交本轮owned源/协议/报告及原件存储清单，核验远端SHA。成功仅为完整开发诊断；失败先一次定位→一次针对修复→新协议与新attempt，旧失败不删，不盲重跑。R2–R10不作为R1的前置。

### R2：完成最小Go wire verifier与Python causal slab，先证明可计算性

**Files:** 完成现存 `S/research/native_clock_source_v2.py`、`tests/test_native_clock_source_v2.py`；新增 `tools/research/native-clock-v2/{go.mod,main.go,main_test.go,testdata/software-only-exchange.json}`，只读 `upstream-source.json`及`upstream/`；沿partial tests实际路径输出 `A/t7b-native-calibration-source/reset-utc-v2-design/fix-round-1/go/build-metadata.json`（含binary_path/binary_sha256/source_hashes），R02引用其SHA，避免再造不兼容build清单。

**Interfaces:** 保持partial `GoWireVerifierV2.verify(request_b64: str, response_b64: str, public_key_b64: str) -> SignatureDiagnosticsV2`，wrapper stdin JSON `op=verify`及上述三字段，stdout严格只有 `protocol,midpoint_unix_s,radius_s`；`verify_causal_slab(pairs, before, after, verifier, *, acquisition_sha256) -> CausalSlabDiagnosticsV2`只产条件诊断，`native_authority=UNAVAILABLE`。新增wrapper `op=request` 输入 `previous_reply_b64,blind_b64,public_key_b64`，通过官方CreateRequest的唯一draft08选项构造请求，输出 `nonce_b64,request_b64`；draft08 nonce/blind均32字节，blind必须由有记录的新随机量及slab commitment构成，使用官方CalculateChainNonce重算。JSON协议和tests同时冻结，签名不自行实现。

- [ ] 复读14项RED及partial子集日志，记录哪些缺wrapper而非算法错误。利用已固定官方源/已核验本地Go包完成离线build；不重复下载最新版，不把“go version成功”写成wrapper已构建。
- [ ] 新增有意义反例：strict frame长度/重复tag/剩余INDX、错误nonce/key/context/delegation/version/单位、重放、源/二进制变化、超时；本地签名fixture明确SOFTWARE_ONLY。运行 `go test ./...`（工作目录 `tools/research/native-clock-v2`，使用已记录Go绝对路径、禁自动下载）先RED，再最小wrapper，重跑GREEN；保存工具链、依赖、build与binary SHA。
- [ ] Python同范围RED→GREEN：遗漏/重复pair、alias、domain重启、A未verify、B过早、B不绑定A及全journal digest均拒绝；合法条件 `[L_A,U_B]`含radius/量化/转换误差。运行 `.venv/bin/python -m pytest -q tests/test_native_clock_source_v2.py`；再owned Ruff/format及mypy，保存原失败日志。禁止软件控制升格app source。
- [ ] 在R02报告列出理论区间宽度组成和现有consumer deadline的比较方法，不凭签名判精度。独审这次固定wrapper/Python接口后交root提交；不必等完整publisher或九组实现才交付。

### R3：同一recorder的RESET tee、真实owner发布与唯一prefix pilot

**Files:** 新增 `S/research/native_reset_capture_v2.py`、`S/research/native_clock_publication_v2.py`、`tests/test_native_reset_capture_v2.py`、`tests/test_native_clock_publication_v2.py`、`configs/research/native_clock_authority_v2.json`；精确修改 `S/simulation_runtime/worker.py::_run_visual_closed_loop`、`S/vision/execution.py` recorder类型门；新增薄入口 `scripts/run_native_clock_prefix_v2.py`。复用现有 `vision/{raw_recorder_v3,worker_runtime,worker_owner,runtime_binding}.py` 的实际factory/lease，不另造owner体系。

**Interfaces:** `ApplicationClockSourceV2.from_application(role_binding: RoleRuntimeBinding)`；`VisualResetClockRecorderV2.from_worker_owner(worker_source, backend, capture, executor, *, clock_source, directory)`；`publish_reset_clock_capture_v2(recorder, *, worker_runtime) -> dict`只从live handle导出；`verify_reset_clock_originals_v2(root: Path, capture_catalog_entry: dict) -> dict`为只读诊断。新增CLI `--config PATH --output PATH --execute-once`调用真实应用job/lease工厂，默认只检查输入，不能public JSON构造authority。

- [ ] 写RED：真实RESET BEGIN可无/旧episode、END必须新episode；重复/失败RESET、earlier动作、pair遗漏、可变payload、lease过期、复制catalog拒绝；未adopted不得绑定RawV3 owner。tee使用原 `_clock_pair()` tuple，新增RESET clock seq不消耗raw record_seq；不得增第二observer或在callback网络/flush/step。
- [ ] prefix分支必须在现存 `planner_factory`（取证时worker:691）前，source-only角色验证允许无Max的排除prefix，但不能假装已验收角色。使用fresh backend、借用capture、sole executor与原120 SETTLE；通过实际repo/lease/live handle导出unbound reset/settle/control/physics/pair/failure原件。测试planner/model构造次数0、观察者只1个。
- [ ] 运行 `.venv/bin/python -m pytest -q tests/test_native_reset_capture_v2.py tests/test_native_clock_publication_v2.py tests/test_visual_worker_owner.py tests/test_visual_worker_runtime.py`；只选CPU工厂控制，不把带真实backend测试混入0actual。owned静态通过后独审三项设计修正及source/config/noise/asset范围。
- [ ] 在应用source-owned issuer policy明确成立后，运行待实现的 `MUJOCO_GL=egl .venv/bin/python scripts/run_native_clock_prefix_v2.py --config configs/research/native_clock_authority_v2.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R03/prefix-1 --execute-once`。严格顺序：verify A→真实RESET→原120 SETTLE→freeze完整slab→发送B→verify B→发布。预注册/nonce/有界exchange次数与无隐式重试须先冻结。policy不能合理成立则不造有限源，记录外部source缺口，其他任务继续。
- [ ] 从实际包/单调括号重算每pair区间及最大宽度，逐一比较既有age/TTL/deadline；prefix只证明原件路径，0教师、0模型，未adopted不伪造owner。宽度不适用时保留条件结果，先确定另一受支持原件来源或合法低频分slab方案的可行性再R4；不修改阈值或声称已校准UTC。报告列各消费者原ordinary_ttl_s（当前模型默认5.0秒，但以冻结配置为准）、valid_until/任务deadline、实测interval-width和保守最晚端点，给出可用/不可用判定。替代source选择顺序：先用已冻结协议的量化下限排除不可能的分slab方案；只有量化下限与网络实测余量允许才设计有界低频小slab；否则登记独立校准GNSS/PPS或另一明确支持版本/UTC语义/issuer精度的外部来源需求，先核验原始校准/时间转换/客户端互通，再一次新prefix。没有上述证据时source继续UNAVAILABLE，R4真实批量暂停、R1/R6/R7独立工作继续。不得把仅签名的Cloudflare结果或不兼容草案当fallback。报告/root提交边界限定新增模块和明确worker seam。

### R4：真实app-owned有限source正分支与至少九个独立支持组

**Files:** 扩展 `S/vision/native_calibration.py`、`S/research/native_geometry_calibration.py`、`tests/test_native_calibration_source.py`，新增 `tests/test_native_calibration_v2.py`、`scripts/collect_native_calibration_v2.py`、`configs/research/native_calibration_v2.json`；index/catalog/registry及所有原件写R04的新版本目录，应用index路径固定 `configs/research/native_calibration_sources.json`，沿现有factory入口增加显式v2。v1原件/报告不改。

**Interfaces:** 延续 `NativeCalibrationSource.from_application(role_binding: RoleRuntimeBinding) -> NativeCalibrationSource` 和 `.revalidate(role_binding)`；新增显式v2 schema分支消费R3 owned catalog、签名预注册与独立UTC sidecar，原RawV3 `utc_uncertainty_ns=None`仍如实保留。新CLI `--config PATH --output PATH --group-id ID --execute-once`由真实应用factory采一个已预分配组，不能调用DIRECT_OFFLINE_SCENE_ADAPTER冒充RESET。

- [ ] 先RED测试v1仍缺RESET而INCOMPLETE、public登记/局部数值/mock verifier不能构造source；v2修改后的原pair/source/owner/horizon/compiled-model/asset/TCP/contact/ref/policy必须全部重算。运行 `.venv/bin/python -m pytest -q tests/test_native_calibration_source.py tests/test_native_calibration_v2.py`，最小实现后GREEN及静态。
- [ ] 预注册完整来源组库存、固定reference/recipe/full horizons、范围和独立性图，不将R1或prefix改名充组。开发资产/640×480/实际noise与默认域差异需明确作用域；不能用零噪声离线场景证明默认0.001m native噪声支持。
- [ ] 首先执行一个新预注册完整组（待实现CLI）：`MUJOCO_GL=egl .venv/bin/python scripts/collect_native_calibration_v2.py --config configs/research/native_calibration_v2.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R04/group-001 --group-id group-001 --execute-once`。验证实际owned图与全部原件可重放；一组只证明source链，不声称n=9统计有限。
- [ ] 首组链路及clock期限可行后，按预登记顺序逐组采集至少9个独立且支持的组，所有分配/失败组件进分母。`ceil((9+1)*.9)=9`，9组有一个UNKNOWN即不能给finite；更多组只能按预登记有界规则，不能删除失败/重命名共享component或为显著性不断追加。
- [ ] 从完整顶点/接触/TCP/原resolved owner全horizon独立重建geometry/action经验界及范围，构造真实 `from_application` 正分支；finite或准入失败均报告。端点误差不能冒充连续supremum/未来稳定性，短窗口不能借完整horizon终态界。独审原件/分组/source链后root单独提交producer/registry，消费者仍待R5。

### R5：三消费者真实接入与端侧G1闭环

**Files:** 精确修改 `S/vision/execution.py` 两处native evidence调用（取证:1485、1561）和 `S/repositories/event_autonomy/visual_verification.py` 一处（取证:870）；测试 `tests/test_native_action_submit.py`、`tests/test_visual_verification_repository.py`、`tests/test_external_rgbd_native.py`、`tests/test_opencv_target_evidence.py`、`tests/test_visual_effect_evidence.py`。必要视觉修复只落 `S/vision/tracking.py`、`S/edge/evidence/conditions.py`，不增加第二判据。

**Interfaces:** 三调用均消费R4真正的 `NativeCalibrationSource` 与当前source/owner/reference/policy/full horizon；沿用唯一 `evaluate_conditions` 和原提交/完成入口，不接受caller有限数值。输出分别记录pre-submit、online effect、repository final的bounds/status/reasons。

- [ ] 添加三入口参数化RED：source/owner变化、missing/wide UTC、旧帧、wrong full horizon均拒绝；geometry>0.01m拒绝。新增错颜色/缺目标0第一动作、遮挡完整范围UNKNOWN、TCP抬升不证明物体抬升、部分像素在区内不证明完整放置。
- [ ] 复用当前已完成的T12/T13接线只补缺口；运行上述五项相关CPU测试文件（真实测试必须独立命令及计数），owned静态通过后审一次三入口同一source路径。
- [ ] 在隔离新开发组执行真实三入口闭环并逐条关联raw/owner/时间证据，保留“源有限但过期/几何过大”的负分支。若相机/标记scope不同于默认域则先验证对应登记，不能静默泛化。
- [ ] 按原G1方案独立评估定位顶部几何中心P90、有效覆盖、静态抓放、抬升/保持/释放稳定的在线与物理合取；不足预定样本或门失败如实记录，不以一次成功关闭G1。写R05报告与root显式提交，真实门通过才允许R8基础路径。

### R6：恢复可启动的Max角色配置并取得真实四请求证据（可与R1–R5并行准备）

**Files:** 复用 `configs/research/ced_roles.yaml`、`scripts/probe_rgbd_roles.py`、`S/vision/{role_models,runtime_binding,planner,model_resolver,frozen_model}.py`、`tests/test_rgbd_role_models.py`。真实profile/secret留应用受控存储，禁止入Git；新公开配置和四attempt原件写R06。

**Interfaces:** 现存 `RoleRuntimeBinding`、`RoleModelBundle.digest()`；`RGBDPlannerAdapter.plan(InitialPlanningRequest) -> PlannerDraft`及`.supervise(RGBDObservation, SupervisionContext) -> SupervisionDecision`。消费实际enabled compatible Max profile及明确secret来源，输出当前角色/source/request/response/usage/cost记录。

- [ ] 在已授权明确应用位置恢复/选择真实profile，保留qwen3.8-max与真实endpoint；只验证secret presence，不读取输出值。外部配置仍不可获得则记录WAITING_EXTERNAL_CONFIGURATION，停止依赖此secret的calls但继续R1–R5/R7的软件工作；不重复询问之前已问问题，不把假profile补入DB。
- [ ] 运行 `.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py`；新增必要缺目标/干扰物、角色交换、过期回复0dispatch及未知weight/version=null断言，已有通过项不重新开发。
- [ ] 已有profile标识存于shell变量 `MAX_PROFILE_ID` 后，执行 `MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_roles.py --config configs/research/ced_roles.yaml --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R06/probe-1 --profile-id "$MAX_PROFILE_ID" --model-control-db data/model_control.db --secret-env BIGSMALL_VLM_API_KEY --execute --allow-paid`。cold+3warm共4 nominal attempts，无dispatch；renderer排入共同actual队列。先冻结实际profile token/timeout/预算，不能套用旧35calls或旧20例预算。
- [ ] 重算双图320×240 transport、严格解析/坐标/拒绝、角色/source/hash、所有失败/超时/usage/实际字节；账单不可得为null，不用官网价格冒称实付。再用独立缺目标/干扰物开发观测检验拒绝，额外请求先登记。四请求通过仅关闭当前角色probe范围，不自动关闭监督可靠性或G1。
- [ ] R06报告独审/root提交仅公共角色配置/source修复/脱敏原件；secret、运行DB和用户配置值不提交。

### R7：固定机会与200实际故障离线教师证据，不等在线T13

**Files:** 复用/补齐 `S/research/protocol_evidence.py`、`scripts/prepare_rgbd_protocol_evidence.py`、`configs/research/recovery_faults.yaml`、`tests/test_protocol_evidence_generation.py`、`tests/test_fixed_opportunity_replay.py`；池清单及教师原件写 `A/astra-repair-execution/R07/pools.json`、`evidence/`，沿原T5教师入口，不增在线恢复器。

**Interfaces:** `prepare_protocol_evidence(pools: dict, output: Path) -> dict`、`verify_protocol_evidence(directory: Path) -> dict`；输入先锁定机会候选/观测/故障日程/eligibility/有界生成规则，输出原件可重算的标签和实际故障教师证明。正式标签只能offline_evaluation读。

- [ ] CPU反例先RED再最小补齐：无故障成功不能算可恢复、summary标签篡改被原件重算拒绝、旧使用组排除、正式标签不可供开发、所有失败分配保留。运行 `.venv/bin/python -m pytest -q tests/test_protocol_evidence_generation.py tests/test_fixed_opportunity_replay.py`。
- [ ] 复用T5实际教师/独立评价生产固定机会与200故障proof；每个fault含真实注入、起止、教师动作、安全及成功原件，失败/排除/未完成不删。新完整采集资源成本参考R1，不用旧早期失败均值承诺预算；记录每批有界库存与renderer独占。
- [ ] 原件/池齐备后运行 `.venv/bin/python scripts/prepare_rgbd_protocol_evidence.py --pools artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/pools.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/evidence`，再同入口 `--verify --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/evidence`。prepare汇编不等同实际教师已执行，缺原件不能靠它生成成功。
- [ ] 独立重算完整标签/故障证据与组图；200不足INCOMPLETE，不能降分母。R07可验收仅离线证据，不称在线G4；root提交来源清单/报告/owned修复，不暴露正式标签给在线代码。

### R8：四周期B0、另120基础先导、资源与INITIAL

**Files:** `configs/research/{ced_selection,ced_foundation,protocol}.yaml`、`S/research/{pilot,pilot_worker,freeze_evidence,protocol,budget,cost_ledger}.py`、`scripts/{run_rgbd_pilot,freeze_rgbd_protocol}.py`、`tests/{test_ced_pilot_stages,test_ced_initial_freeze,test_research_cost_ledger}.py`；R08下selection/foundation/initial新目录。

**Interfaces:** selection/foundation现存CLI；`initial_spec_from_evidence(Path) -> ProtocolSpec`；`freeze_protocol(..., stage='INITIAL', evidence_directory=...)`。消费R5真实端侧资格、R6角色原件、R7池与证据；填补当前selection的 `pools_path/role_probe/protocol_evidence=null`，不能跳过三项绑定。

- [ ] 先运行 `.venv/bin/python -m pytest -q tests/test_ced_pilot_stages.py tests/test_ced_initial_freeze.py tests/test_research_cost_ledger.py`；只为新缺陷补RED/实现。断言新角色不能借旧foundation、所有重试/超时入成本、没有机会/fault原件拒绝INITIAL。
- [ ] 用R6同一实际profile执行 `MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_pilot.py --stage selection --config configs/research/ced_selection.yaml --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/selection --profile-id "$MAX_PROFILE_ID" --model-control-db data/model_control.db --secret-env BIGSMALL_VLM_API_KEY --execute --allow-paid`。120互斥selection组×4周期，12层各10；按原质量门筛选合格者中请求最少、平局延迟较低者。不等待T11完整适配或T13。
- [ ] 若合格，使用同CLI `--stage foundation --config configs/research/ced_foundation.yaml --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/foundation`及同profile/secret/execute flags，采另120未用组；独立重算物理、帧、成本、角色/源、同backend/episode/墙钟映射。
- [ ] 计算Tcap和完整成功路径资源预算（初始化、原件、功效、正式/消融/恢复、回放预留），然后运行 `.venv/bin/python scripts/freeze_rgbd_protocol.py --stage initial --expected-protocol-version ced.research.v2 --config configs/research/protocol.yaml --pilot artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/foundation --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/initial`。N仍留空；拒绝原因保存，不手改JSON成INITIAL。
- [ ] 无合格B0则NO_FEASIBLE_BASELINE，回到具体共同基础缺陷一次定位修复、新selection代次；预算不足INCOMPLETE。通过才root登记T8限定完成，显式提交配置/证据/报告，不改旧v1/v2。

### R9：风险、共同运行路径与恢复的实际闭环，冻结METHOD

**Files:** 现存 `S/vision/risk/{models,features,fit,calibration}.py`、`S/edge/evidence/{models,validator,opportunities}.py`、`S/auto_mode/{joint_policy,candidates,judgment,transition_service}.py`、`S/cloud/replanning/visual_repair.py`、`S/edge/recovery/lifecycle.py`、`scripts/calibrate_rgbd_risk.py`、`configs/research/{risk,joint_policy,recovery_faults}.yaml`；测试 `tests/{test_rgbd_risk_calibration,test_visual_evidence_contract,test_runtime_auto_baselines,test_joint_visual_policy,test_verified_recovery_lifecycle,test_replan_activation}.py`。METHOD manifest写R09。

**Interfaces:** T9 `RiskFeatures/RiskEstimate`仅可观测；既有 `DecisionJudge.choose(context, candidates, estimates) -> JudgmentResult`；模式CAS与ReplanApplyService实际启动回执沿用现成接口。METHOD manifest绑定INITIAL、模型/provider/端侧/候选/门控/预算/恢复与全部source hashes，冻结后不调参。

- [ ] 对已有T12/T13交付作缺口核对，不因本文重写模块。CPU新增只覆盖原真值不得进边缘、UNKNOWN拒绝、STOP必有、过期候选不提交、重启预算不清零、ACK非启动、completed动作不重放；运行本任务六份测试，失败保留、最小修复再GREEN。
- [ ] 用隔离现行域数据按train/calibration/selection拟合/校准/选参；预算核准后才扩10000组。运行 `.venv/bin/python scripts/calibrate_rgbd_risk.py --dataset datasets/rgbd-ced-calibration-v2 --config configs/research/risk.yaml --initial-protocol artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/initial --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R09/risk`（该dataset由原T6工厂按登记库存生成，不允许临时复制旧组）。报告覆盖/校准/域外边界，不把规则分数当概率。
- [ ] 共同冻结Max/边缘规则/端侧/控制/候选/预算下真实验证B0/B1/B2及主方法，B3只去校准不确定性与动作相关有效期，B4只改重规划范围，B5按原采样机制。使用开发机会与故障，正式R07标签不用于选参数；LOCAL_RECOVER仅在DETECTED→AUTHORIZED→EXECUTED→VERIFIED_RESOLVED实际能力通过后开放。
- [ ] 核对owner模式、active contract、checkpoint与prepared提交/abort/重启幂等；真实恢复与B4配对、完成不重放、硬停止独立、周期非仅技能边界触发。保留所有失败与实际等待推进/成本/响应延迟，不能用软件Mock关闭本步。
- [ ] 独审实际门通过后写 `A/astra-repair-execution/R09/methods.json` 冻结完整方法及provider，交root提交。边缘模型影子/selection是后置可选支线；选新模型才有受影响的selection/冻结新代次，不要求先选模型才能继续。

### R10：功效120→FINAL→正式研究、统计与复现交付

**Files:** 完成现存 `S/research/{assignments,runner,ablations,power,statistics,metrics,acceptance,reproducibility}.py`、`scripts/{freeze_rgbd_protocol,run_rgbd_pilot,run_rgbd_research,run_rgbd_gate_replay,analyze_rgbd_research,reproduce_rgbd_research}.py`、`configs/research/{pilot_power,formal,ablations}.yaml`；测试 `tests/test_research_{assignments,runner,power,statistics,acceptance,reproducibility}.py`。结果页复用 `dashboard/src/simulation/pages/ResearchEvidencePage.tsx` 与 `S/cloud/api/research_results.py`；文档 `docs/research/{reproduction,results_and_limits}.md`。

**Interfaces:** 功效CLI消费R8 INITIAL及R9 methods manifest；FINAL输出固定N/方法/源/协议hash；formal runner消费FINAL和已隔离pool，原始EpisodeRecord进入现存统计/接受判定。当前 `freeze_rgbd_protocol.py --stage final` 明确exit3硬拒绝：必须实现按真实方法/功效原件校验的分支，不能只删除拒绝行或称命令当前已可用。

- [ ] 在上述六份研究测试中补缺失RED：FINAL缺METHOD/120原件拒绝、变更阈值/池拒绝、N>2400不足、formal非FINAL拒绝、失败BLOCKED保留、零事件上界/非劣/Holm/固定seed bootstrap手算控制。最小实现后运行 `.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py tests/test_research_statistics.py tests/test_research_acceptance.py tests/test_research_reproducibility.py`，owned静态和独审通过。
- [ ] 使用 `scripts/run_rgbd_pilot.py --stage power --config configs/research/pilot_power.yaml --initial artifacts/research/process/20261004-ced-development/astra-repair-execution/R08/initial --methods artifacts/research/process/20261004-ced-development/astra-repair-execution/R09/methods.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/power` 加R8同一真实profile/secret/execute flags运行另120。仅估功效锁N，行为修复使此批失效并登记，不复用调参。
- [ ] 新实现验证通过后运行 `.venv/bin/python scripts/freeze_rgbd_protocol.py --stage final --pilot artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/power --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/final`；N/预算/来源不足仍拒绝。
- [ ] FINAL与真实G0/G1前提通过后，运行 `MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_research.py --config configs/research/formal.yaml --protocol artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/final --pools artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/pools.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/formal`；主方法/B0–B5按原机制及冻结N共同分母，固定机会G3及200故障G4/B4单独保存。formal runner未接真实app时先实现/验收，不允许软件fixture生成研究结果。
- [ ] `run_rgbd_gate_replay.py --protocol .../R10/final --opportunities <R07已冻结机会文件> --method JOINT或B3 --output <各自新目录>`分别运行原件回放；这里两个具名占位必须由R07 manifest的真实文件绑定写入运行清单，不能猜文件。运行 `analyze_rgbd_research.py --runs .../R10/formal --protocol .../R10/final --output .../R10/analysis`；`...`严格展开为本计划A/astra-repair-execution，完整执行命令保存。点估计/区间/UNKNOWN/误完成/无进展/费用与本地资源分列；G0/G1未过不验收C1/C2，负结果照常交付。
- [ ] 用原件包运行 `.venv/bin/python scripts/reproduce_rgbd_research.py --bundle artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/release --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R10/reproduced`，核对hash、固定统计seed、失败分母及报告一致。结果页测试/API和受影响前端构建通过后，root汇总T15–18/G0–G4实际状态、提交推送并核验远端。真实硬件/可选扩展未做NOT_STARTED/NOT_RUN，不以文档齐备宣布研究成功。

## 自审与执行边界

已自审五项：原设计各节覆盖R1–R10；保留全部量化/预算/统计门；新接口生产者与消费者一致；五项Review Focus各有owner测试；实际依赖为有向流程，R7不依赖T13、T7b基础证书不依赖INITIAL/T9。新source的A/B区间可用性在R3提前决策，避免无效九组开销；R1不等待它。

本次计划没有接受任何未完成软件或actual。后续每项只有精确输入SHA静止、该项检查/真实证据满足时才更新对应范围状态；来源改变只使受影响证据需重新验证，不自动重跑全部任务。任何新阻塞报告具体缺件及可继续工作；一次失败先定位修复再新尝试，旧失败原件和全分母始终保留。
