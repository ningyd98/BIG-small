# R07 单组真实恢复 Producer Implementation Plan

> 执行方式：沿父任务已授权的 AstraR7 设计，以 executing-plans 在当前分工内执行，不重复审批；不改rootdocs或Git。

**Goal:** 提供可审查、明确 execute-once 的锁定新组TARGET_MOTION恢复生产器，default纯CPU。
**Architecture:** 新模块只负责来源库存/锁定完整3260池、持久分配日志/预算与现T5+backendhooks接线。原protocol_evidence接受合同保持不变。新的CLI显式prepare/preflight/execute-once；本slice不实现固定机会生产。
**Spec:** 原20261004cloud-edge-device设计§5/8、20261005AstraR7、R07/audit/report.json。

## 约束及裁定

- 仅三个新ownedPython文件及R07/producer新产物；当前禁止backendinitialize/physics/renderer/network/provider。
- 原raw320×240、当前顶视camera/controller/资产，dt.0041666667、120settle，故障.02m/s1s、direction_y±，教师9动作/原结果，reset0全步/commandseq1/PREactuator。
- 总恢复从faultstart起≤60s；首批wall1800s、retained2GiB、diskreserve10GiB；每组最多5记录，首actual只attempt1无隐式重试；失败/排除/partial均保存。
- 新源库存包含datasetmanifest/samples、两旧pilot分配、T5manifest、已有development/header/lineage/注册。按group+scenehash+physicalgeometry+component关系合并，缺身份登记具体unresolved，未知历史不能宣称闭合。
- prepare以新seed2026100507生成全部3260完整v2，避开group/scene/physicalidentity；不重命名旧dry池、不复制旧actual。库存不闭合则生产preflight阻断但保留gap及收集入口。
- 设计取舍：复用现T5和被动write_recovery_source；不修改旧collector，不增动作引擎，不生成fixture成功。不把零云请求的offline恢复冒称G4。

## Review Focus

1. 失败在第一actuator之前以及teacher/observer/serializer异常后，allocated仍有原件/失败日志。
2. 独立场景重命名、不同asset/camera但同物理geometry、componentalias和来源变化拒绝。
3. 负向direction_y及真实FINISHED检查，不用固定241成功假定；teacher只在故障完成后。
4. wall/disk/byte和faultstart+Rcap触发必须终止并保全；callback不调用网络/flush或step。
5. execute-once拒绝重复或并发attempt，源码/recipe/history锁变拒绝，defaultCLI不创建backend。

## Task1: 库存、锁定和纯CPU入口

Files: new research/protocol_generation.py, scripts/generate_rgbd_protocol_evidence.py, tests/test_protocol_generation_sources.py.
Interfaces: inventory_history(paths)->dict; prepare_generation(history_sources,output,seed=2026100507)->dict; preflight_generation(protocol_directory,assignment_id,attempt=1)->dict.
- [x] 先缺module RED，再历史alias/缺scene/不可闭合/漂移/完整池3260、正式200及正确±日程契约RED。
- [x] 最小实现读取显式实际metadata文件、connected provenance及不可覆写锁包/defaultCPUCLI。
- [x] 仅新CPUtests GREEN；新ownedstatic检查。保存全部RED/GREEN。

## Task2: 单组实际接线、保全与预算

Interfaces: execute_recovery_once(protocol_directory,assignment_id,attempt=1,output)->dict；lazy _run_physical负责现MuJoCoCaptureSession/T5接口，CPU测试通过注入软件collector执行反例但绝不冒称actual。
- [x] 无fault/反向key错误/partial动作/预算/attempt重入及分配分母 RED。
- [x] 新源先分配journal和绑定plan/source后lazy进入actual；reset/settle/fault/T5原hooks，stream原件临时journal保持失败；结束被动adapter+独立验收，不隐式retry。
- [x] observer只收detached原件且抛预算终止；可审查deadline由现有每步检查。失败前缀不删，不伪造TERMINAL成功。
- [x] 对新scopeCPU收集器测试及static GREEN，真实运行0；保存ownedSHA/旧四core未变及report。

## Task3: 已定位实际库存和可审查首批

- [x] 定向读取已定位实际metadata，生成history-source-catalog.json并调用prepare_generation产生新完整池和预冻结预算。
- [x] unresolved逐项输出，不把调用者bool当历史完备证明；明确补哪些原件或scope登记。
- [x] 首actual命令输出在report，root独审后串行execute-once；本slice不运行它。机会接口仅登记NOT_IMPLEMENTED，目标仍2400/200。

Verification: PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_protocol_generation_sources.py；ownedRuff/format/mypy。历史已通过完整batch不重复，无commit。

Software slice complete: 20 CPU cases and owned static checks verified. Root independent review and first actual execute-once remain pending; no physical proof has been generated. Fixed-opportunity producer remains NOT_IMPLEMENTED.
