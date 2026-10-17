# P6 具体 CPU 与文件拆分补充 v2

**NON_ACTIVATABLE_PENDING_P5**。实际 gpt-6-astra，只补充已接受设计的实施映射。原 PARTIAL 两文件保持不变；本补充不是新 Astra 激活计划，不授予产品、验证或 actual 额度。P5 最终十源与独立验收尚未绑定。

## 六个可审查实施单元

1. **真正租约 authority 与仓储协议。** 新 `simulation_runtime/operational_lease.py` 放 private broker、lease segment/proposal 与 LockedLeaseView registry。`simulation_runtime/repository.py` 声明具体入口；`sqlite_repository.py` 实现锁内 view 签发、acquire/heartbeat/release/expire/cancel/status/retry 所有新 schema 写者。`worker.py` 真实 run_once 在首次 acquire 前安装私有 broker，heartbeat 原线程仅 RPC，不读取 D_app；worker 最终 cleanup revoke/join。工厂与 owner 的最终私有 API 从 P5 freeze 绑定，不能靠字符串/source 描述自授权。新表可存 operation mode、epoch、lease generation、原预算 descriptor、proposal/commit digest；既有 UTC 列供 legacy/诊断，不能从它们恢复 live authority。
2. **事务内 publication 与 budget。** 原 event protocol/Memory/SQLite 和 `visual_owner.py`、`visual_verification.py`、`owner_registration.py`、`worker_owner.py`、`verification_router.py`、`worker_runtime.py` 接 versioned local branch。P5 `operational_windows.py` 只在最后 API 无法提供实际受限 txn check 时明确追加，不能绕过注册或同域父事件。新 `D_app receipt AND D_lease receipt` 包含各自 issuer/domain/original event/constraints/current read；不导出跨域 min deadline。纯 codec 接收 detached receipt 只作记录，真正仓储 consumer 必须验证私有当前 token、purpose、op digest、row CAS、实际 txn 生命周期。
3. **原 UTC 全新分支闭包。** 冻结 P5 worker_runtime:486/566 有 task/verification UTC veto，:938–943 有监督 frame UTC expiry；bootstrap:645/810/1024、supervision:556/684/704/761/791 也真拒绝。最终范围须包括两个 codec 的 versioned derivation 与调用适配，否则不能标完整新 D。原 Task6 visual_owner:462/534/693、visual_verification:785/derive_route、owner_registration.effective_deadline/bind、router:93 逐条区分本地 budget/age 与外部 UTC 证书。新本地 variant 由真 issuer 决策，原 timestamp 仍可保留诊断与历史字段关系；legacy 分支原字节/拒绝含义不改。不可简单删除 datetime 比较或给 caller `skip_utc`；未知/混用 schema 拒绝。显式版号对应严格字段集，旧历史解码不变。
4. **真正 mutation。** `vision/execution.py` 两前置点、`skill_executor.py` 参数/preconditions 后的 definition.handler 前接单次 intent；backend 只在有效 owner context 存在时走新门，legacy 无 context 原行为保留。apply_joint_targets clip 后入队/target 更新前门，apply_gripper_command 写 _gripper_open/ctrl 前门；_apply_control 到期 queue 实际应用前重核原 action/fence/window，不把 ACK 当 start。step 三循环每次 _apply_control+一个 mj_step 为短原子单元，不能整技能持锁；晚返回保留 partial，不宣称任意阻塞间隙已被消除。内部 e-stop/hold/清队列可达，无 caller skip flag。
5. **D/S 段与终止恢复。** `research/clock.py` 新版本 WAIT 用原 D_app 连续差推算应推进 S，保留旧行为；不得把实际渲染/请求耗时伪成模拟 timeout。`raw_recorder_v3.py` 在唯一 observer、purpose 和 execute_attempt 接同 owner 的 segment sink，sidecar 新版记录 request/wait/render/controller 原分配、D_BEGIN/END、S_BEGIN/END、kind、step、owner、lease references、disposition/missing reason；不改旧 raw schema/字节、不加第二 observer。`recovery.py` 启动先调用仓储终止无可重连 epoch 的 operational attempts；`sqlite_repository.retry_job/update_status_cas` 同样防旧任务重新授权，不能只封一个 API。service.start 已在 dispatcher 前执行 recovery，优先无需改 service；若真实生命周期不符，最终计划再列精确入口。
6. **CPU 验证与最终完整正链。** 新 `tests/test_operational_runtime_closure.py` 内有限 helpers 与 JSON manifest，不默认新增辅助源树。先测试实际两仓储、两个线程、真实锁/事务/handler/backend mutations。最后必需完整 PRE_SAFETY/PRE_SKILL native 正链依赖 R91/P7/P8 当前真实 producer：当前 `tests/test_native_references.py` 明示软件测试不授予 motion；不得通过 mock VALID、移除 native gate 或把全 UNKNOWN 变成完成。该最后两节点为待接续必需项，非可删验收项；P6 可先分阶段交付已验证单元，最终通过仍需完整正链真实执行。

## 锁、提交与生命周期的具体实现约束

job publication RLock/flock→job BEGIN IMMEDIATE→event SQLite BEGIN/Memory lock→短 registry 签发→broker RPC→主 owner fresh D→本次 CAS/短 mutation。broker 自己创建/read OC1，永不获取 repo/physics 锁；RPC 期间不得持 registry mutex。acquire 源现先 now 后 BEGIN，新 D 实现必须独立锁后 read；heartbeat/release/cancel/reassign/expire 新分支都服从统一 guard。

OPEN→DECIDED→CONSUMED→COMMITTED→CLOSED；rollback/CAS!=1/connection exception 强制 INVALIDATED。registry 记录 repo/DB identity、thread、txn nonce、generation、purpose、operation digest，公开构造/复制无 registry identity 即拒绝。broker proposal PENDING 在真实行 CAS+commit 私有确认后才 ACTIVE；确认丢失终止而非猜成功。publication event commit 在仍持 job guard/txn 的区间完成；不能声称两个 DB 原子提交。若同时要更新两 DB，以明确 durable phase+幂等 completion/终止记录实现，dispatch 只接受两份 exact committed receipts；不存在完整对偶时停止。每个短单元释放锁，heartbeat/cancel 才可推进。

heartbeat 可按原 TTL 产生合法新 segment，但不能改原 task/verification/recovery 的起点、deadline、spend 或 retry；晚 heartbeat/旧 epoch 不复活。restart 支持边界选终止旧 attempt，不重建原句柄；显式新任务需真实授权。actual suspend=NOT_RUN，需它的 scope 不晋升。两个 authority 各自原域 AND，绝不更改 P5 parent 同域规则。

## 真实 fixture 和远端有限交付

- `tests/test_visual_worker_runtime.py` 的 runtime_source 用实际 SQLite job repo 和 event Memory/SQLite，可复用 job/role/source 文件构造，不能复用它公开 source 构造作为 live authority。最终 CPU factory 必须从真实 worker 私有 startup 走完整原 origin/attempt；broker 用真实 Python 线程和 OC1 检查，raw counter 注入仅标 CPU 测试时钟，原 budget 不重置。
- `tests/test_ced_runtime_binding.py::role_binding` 与 `test_visual_owner_registration.py::values` 可作为明确 synthetic 输入配方；最终列全部小源码依赖与 SHA，不复制 SDK/权重。源 inventory 按实执行文件冻结，不能为了通过自动刷新任意漂移。
- 如使用 marker frame，引用最终 R107 三文件原件及 provenance（现在未读、未 pin 活动产物）；gzip 必须解出原 exact bytes，保持真实 source/asset 检查。CPU 像素来源不变成新 actual/native qualification。
- backend 单元可参照 `tests/test_visual_raw_recorder_v3.py::software_backend` 的真实方法+假 mj_step 软件夹具，但它明确无真实 MjData/physics；用于分支/队列/原子门负控，不可作为真实 S/动作效果证据。真实 backend CPU 冒烟另参考 `tests/test_phase9_mujoco_physics_step.py` 的 `MuJoCoPhysicsBackend.initialize/reset/step/shutdown` 与仓库 scene.xml，无网络/renderer/model调用；最终计划必须显式登记该 CPU 源、资产及预算，未授权前不运行。其结果只验证 native backend 路径，不替代 R91 完整动作实际试验。
- 所有自产 synthetic fixture 构造一次并保存 definition/content SHA；初始采集时刻合法产生，不能反复重贴旧帧去绕过过期。并发用真实锁和 barrier，不靠 sleep 猜顺序。lease broker/domain 负控必须断言实际 SQL/handler/queue/ctrl 未变化，不能仅断言 helper 返回 False。

## 节点与命令边界

`cpu-matrix.json` 是拟定节点/参数表，未 collect、未执行。最终 P5 freeze 后 Astra 可据此锁定精确分母和叶目录；当前额度全部 0。最后 full-runtime 两节点必须有 R91/P7/P8 producer 验收输入才能激活；不是 skip/xfail 计 PASS。

建议命令在最终计划绑定工作目录、exact owned list 与新证据目录后采用 argv 数组：RED 为新 closure 文件一次；GREEN 为 master 指定 closure + tests/test_visual_worker_runtime.py + tests/test_visual_worker_supervision_runtime.py 一次。将原两回归文件节点分母通过其实际参数定义/最终收集收据固定，不能猜数字；不要混入全 P5/OC1 重跑。若分阶段，RED/GREEN 分组在激活前拆定互斥节点，不能临时重复同一总分母。

静态：`python -m ruff check <explicit changed python>`；`python -m ruff format --check <explicit changed python>`；`python -m mypy <explicit changed production python>`。具体每条各一次建议额度，最终计划另批准；无 --fix/formatter 默认写入授权，无全仓/static扩大。CPU 用 PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.、pytest -p no:cacheprovider、独占 --basetemp 和 --junitxml，结果原 bytes/exit/UTC/nodeids 全保留。旧失败/旧测试原件不覆盖；unexpected 非零须新 Astra。

## 仍待最终激活输入

最终 P5 十源、真实私有 startup/check/cleanup 接口与独审；新 D codec 精确 schema 和每个旧 UTC 调用点的分支清单；broker RPC 有界等待的原 policy 来源（不得自增 wall 成功保证）；real native 正链输入；测试的精确集合/枚举/总分母、全部 static 命令与 source closure。新文件/增补路径清单在 JSON 是准备建议，不是写权限。没有任何软件/actual/formal PASS。
