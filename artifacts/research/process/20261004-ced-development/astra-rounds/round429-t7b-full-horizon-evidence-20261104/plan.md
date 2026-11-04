# R429 精确完整 S 时域与原件覆盖审计 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. 用户已授权继续研发；本计划不另要求许可。只实施下面两项，遇计划外失败交下一轮 Astra。

**Goal:** 交付精确有理数 horizon 与独立逐步执行/HOLD 原件审计，为真实 producer 提供可用验收门。
**Architecture:** 两个新模块；保留 integer v2 kernel、R427 observed-return reader、所有旧 UTC/e/v 语义。公开结构只有 SOFTWARE_ONLY/UNAVAILABLE/UNKNOWN，coverage 不是准入。
**Tech Stack:** Python stdlib Fraction/dataclasses/hashlib/json；复用 RawV3 类型及原操作账本格式，无新依赖。
**Spec:** R91 `design.md` §§3–5（路径见 plan.json pins）。

## 原始问题与边界

证据为本轮 `intake/observation.json`，HEAD aecf1fd836ff08819edb053a2e87b4b2a83235b0。整数 ns 不能表达 1/240S；execute_attempt 在实际返回关闭；独立 HOLD 尚无版本化绑定。补充源码事实：SimulatorConfig 默认是 **0.0041666667**，不等于 float(1/240)；backend observer 吞下异常并记失败，不能充当执行取消 hook。当前私有 operational recorder 没有 R91 每操作 deadline pre/post 执行闭包；其 COMMAND 分支还错误要求 physics_state，而 backend 返回 command_records，故不能 MARK 成功 COMMAND。旧 prefix verifier 明确只接受无动作的 step120，不是动作 full-H verifier。本轮不修改它，也不冒造 private owner。

输入 SHA256 见 plan.json；实施前逐一复核，并复核 intake 的全部 pins、HEAD/分支和受保护 dirty gitlinks。根因假设是时间表示与原件覆盖接口缺口，不是已有控制器失效。没有实测崩溃；仅下述单个 RED 为预期失败。

## Task 1：精确配方（新增 vision/native_completion_horizon.py）

- [ ] 新测试 `tests/test_native_completion_horizon_v1.py` 与 Task 2 测试先写。只在 RED 指定测试内部 import 新模块，使唯一预期错误是 ModuleNotFoundError。
- [ ] 提供 frozen `RationalCompletionHorizonV1`；入口 `completion_horizon_rational_v1(skill: str, *, dt_numerator: int, dt_denominator: int, registered_dt_s: float, original_timeout_ns: int, original_expected_ns: int, compiled_timeout_ns: int, compiled_expected_ns: int, effective_owner_required_ns: int, builtin_tail_included: bool=False, registered_wait_steps: int=0) -> RationalCompletionHorizonV1`。
- [ ] 所有整数严格拒 bool；时间及分母正，wait 非负，技能同八技能常量。ratio 约分；显式配方 ratio 转 float 的 `.hex()` 必须等于 registered_dt_s.hex()，同时存 registered float 的 as_integer_ratio/hex。禁止猜分母、limit_denominator、舍入 ns、把 decimal default 改成 1/240。ratio 是显式登记的数学时基，float 仅配置编码；无登记 ratio 时不推定意图。
- [ ] base=ceil(max(五个 ns)/1e9/dt)，LIFT tail=ceil((1/2)/dt)，RELEASE tail=ceil(1/dt)，其余 0；included 为真则 base≥tail 且 tail>0，added=0，否则 added=tail；total=base+added+wait；总时间保存约分 numerator/denominator 秒，绝不 float 累加。保留五个输入、base/tail/added/wait/total，schema `native.completion.horizon.rational.v1`。included 仅公开声明；审计要有原配方引用，不能以 bool 证明动作真实覆盖。

## Task 2：原始字节覆盖门（新增 research/native_completion_horizon_originals.py）

入口 `audit_completion_horizon_originals_v1(*, sidecar_bytes: bytes, originals: Mapping[str, bytes]) -> FullHorizonOriginalAuditV1`。结果 frozen，含 source/session/episode/span、重算 horizon、dispatch/return/terminal、逐步 execution/hold/wait 库存、所有原失败、structural_reasons、qualification_reasons、`coverage_status`（STRUCTURALLY_COMPLETE/INCOMPLETE）、`producer_status='UNAVAILABLE'`、`guard_status='NOT_PROVEN'`；固定 SOFTWARE_ONLY/UNAVAILABLE/UNKNOWN，无 certified/q/e/v 字段。

- [ ] 明确定义 sidecar schema `native.completion.full-horizon-sidecar.v1`：source_session_id、episode_id、domain_sha256、span_id、capture_acquisition_id、terminal_acquisition_id、recipe（Task1 全输入）、originals（仅两个 role `partial_attempts`/`preregistration` 的安全相对路径+bytes+sha256）、open_boundary（dispatch 前已有 operation_id）、close_boundary（终态 CAPTURE END operation_id）、hold_interval_ids、wait_interval_ids。无调用方 status/PASS。preregistration 原件 schema `native.completion.horizon-preregistration.v1`，包含同 session/episode/domain、同 recipe、span 对应 step_id/attempt、original_plan_sha256、executed_step_sha256、owner_requirements_sha256、controller_source_sha256、tail_inclusion_basis。SHA 绑定原始源文件及对应已有 payload 的 RawV3 canonical digest，不信任缓存 summary。
- [ ] partial_attempts 角色使用新增 `native.completion.full-horizon-originals.v1` 诊断原件格式；字段沿用现有 partial-attempts 布局（不同 schema，旧 prefix 原件不能改名获接纳）。从其 operational_ledger、backend_operation_ledger、legacy_actions/intervals/physics/commands/frames、source_hashes、reset metadata 重算。只读内存 bytes，不按 sidecar 任意读磁盘。拒绝重复 JSON key/非有限数、错误 schema/键/类型、坏大小/hash/路径/重复 role。语法或顶层缺原件 ValueError；可识别动作的证据缺失返回 INCOMPLETE 保留分母。
- [ ] 精确 join 唯一 span、原 plan/compiled payload/owner requirement/source digest；original/compiled timeout 与 expected 从已有 payload 重算，owner duration 从原 requirements 转 exact Fraction 校核 ns（不能四舍五入）；不支持的 owner 表示明确 INCOMPLETE。核对 dt 与实际 reset config。sidecar recipe 必须与预登记字节完全一致；本轮原件 coverage 只支持 MOVE_ABOVE/APPROACH，其他六技能保持分母并明确 unsupported。included-tail 的 kernel 算术覆盖八技能；reader 不以声明或 source hash 证明已包含尾段，未有实际配方证明即 INCOMPLETE，不重复加进已含完整 H 的 owner 时长。
- [ ] open_boundary 必须同 session/episode 且严格先于 dispatch 首操作；close 为本窗口终态采集 END。capture_step==dispatch_step，terminal=dispatch+total，实际返回≤terminal；capture/terminal 原 acquisition 唯一且有 D/物理状态引用。仅匹配串/预开 sidecar 不构成真实签发：结果始终列出 `same_session_private_producer_unavailable` 与 `execution_deadline_guards_unproven`，即使结构覆盖完整。
- [ ] 使用完整 backend BEGIN/END 分母与 D ledger 逐项一对一核对（顺序、ID、kind、episode、step、error）；检查 D 序列/域/bracket 同源有序、全部失败和 pending。先以实际库存计数核对总步数，再遍历现有行（不可按任意大声称 H 分配 range/list）；每个 dispatch+1…terminal 必须恰好一个 CONTROL 与 PHYSICS 对，control 先于 physics，前后 state hash 连续，control/physics payload 与原 operation END 一致。拒删/重/乱序/跳步/跨 episode/未知推进/重置/中途下一动作。
- [ ] dispatch…return 归原唯一 EXECUTOR_ATTEMPT；早成功后全部剩余步必须归显式绑定的连续 HOLD 或登记 WAIT，且 HOLD 原 command 是既有 `hold_current_joints`、已接受、控制目标与原 actuator/control 数据一致；不可仅检查目的字符串。登记 WAIT 严格总步数，无双算；尾步与总 horizon 已覆盖。晚返回、失败/异常/部分动作不强造终态成功，所有失败保留；物理步后终态 capture 必须实际存在。完整窗口内不允许额外动作或外来控制命令。读取原记录不 step/写 pose/执行 hold。

## 单轮验证与独立 oracle

- [ ] 一次 RED：`tests/test_native_completion_horizon_v1.py::test_registered_one_over_240_exact_horizon`，预期新模块不存在；一次 GREEN：两个新测试文件 + 原 `tests/test_native_completion_v2.py`、`tests/test_native_completion_originals_v2.py`（旧 59 项）。新矩阵控制在约 20–30 项，参数化不重复整个 fixture 生成。
- [ ] 数值 oracle 手算：1S/dt=1/240 得 240，LIFT 360，RELEASE 480，included 不重加，wait 独立；默认 decimal dt 单独登记并与 1/240 错配拒绝；非整步向上、非法/bool/NaN、输出不可变。
- [ ] 原件 oracle 使用独立手写、精确 RawV3/operation-ledger 布局的新版本诊断原件小例：settle 后 dispatch=120，return=121，terminal=123；四个 action 时长 10ms、owner 12.5ms，1 步动作+2 步 HOLD（全部 source/session/payload joins）；不调用被测审计器构建期望。逐一篡改 hash/recipe/预开顺序/控制 payload/每步分母/目标/hold 命令/WAIT 归属/终帧/失败/下一动作/跨域，保留失败和缺组。完整例仅 STRUCTURALLY_COMPLETE + UNKNOWN；synthetic COMMAND D 行不是现有 operational recorder 真实产物，测试必须明确标为手写 software fixture，不能称已签发。没有真实私有 producer，本轮不跑 MuJoCo/渲染/校准以冒充完整来源。
- [ ] 复用 R427 wrapper 的 R413 supervisor/R235 startup/event plugin，改成本轮新目录、basetemp、两次各固定 timeout_s=600、attempt=1，必须显式 --junitxml=<stage>/junit.xml。预检仍为已有 1317 baseline/409 src 环境；新模块/测试 pins 追加，旧源 pins 不替换。保存原 stdout/stderr/events/JUnit/spec/结果，RED 只接受指定缺模块，GREEN 全通过且无 drift/遗留进程。聚焦新增文件 ruff check/format --check、mypy 沿已有参数；静态工具不改原件。任何意外失败停止相关修改，交下一轮 Astra，不加时重试。

## 交付与验收界限

仅新增上述 4 个文件及本轮 implementation/validation/步骤报告/阶段总结；不改现有产品文件，不动 workspace-baseline/workspace-h3。计划在此目录。软件验收=数值与原件覆盖 gate 通过；实际 full-H producer、原 deadline/hard-stop pre/post 执行、真实 RGBD 与九组校准、formal native 仍 NOT_STARTED/UNKNOWN。下一阶段 producer 前置条件包括修复 COMMAND D 记录支持、另建动作 full-H 原件验证入口及在既有唯一执行入口落实真实 hold 与守卫；旧 step120 prefix receipt 不可授权动作，不能靠 observer 抛异常。按明确路径提交推送当前研发分支并核对 local/upstream/remote SHA；manifest 不等同完整 raw 远端复现包。
