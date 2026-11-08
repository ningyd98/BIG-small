# R461 Sol evidence reader 与毕业设计主线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:executing-plans，由 ROOT 在当前研发分支逐项实施。步骤以 checkbox 记录；本次用户只要求计划，发布计划不等于执行授权。

**Goal:** 用最小修复让独立 reader 按实际 Sol 请求重建证据，并给出下一阶段真实贯通的明确顺序。

**Architecture:** 复用现有 `compatible_chat_generation`，在原 reader 内统一有效字段重建和离线 adapter 身份。云端 nominal 证据与零云调用的教师 full-H 采集是两条独立资格链；P0 收口后分别冻结来源，GPU 实际阶段串行。

**Tech Stack:** Python、现有 RGBDPlannerAdapter/RawV3/CostLedger、pytest、R413 bounded_stage；不新增依赖。

**Spec:** 用户 2026-11-08“继续制定下一步的工作计划”；`AGENTS.md`；`docs/superpowers/plans/2026-10-22-post-opening-development-plan.md` Tasks 2/3；R91 `design.md`、R439 及后续已实施限定修复；R457 指定精确 `gpt-6.1-sol` 的实际生成策略。旧总计划中的 Qwen 云模型文字由用户最新 Sol 选择覆盖，其余既定方案保留。

## 当前事实与原始问题

实际规划模型 **gpt-6-astra**，基线 `03d076b48f5470ebc3ffeb8c99f7e1e4eae25cf1`。31 项必要输入的 SHA256/字节数见 `intake/input-pins.json`；必要源码及小型结果按原字节复制，逐行静态证据见 `intake/static-evidence.txt`。本轮没有运行失败日志：这是源码静态确认的问题，未执行测试或真实调用。

R460 已完成官方 Sol 历史 v1 图像 4/4 回放，3032 tokens，独立复核 PASS；只证明该旧图范围的传输、解析与定位。fresh role、当前 v2、full-H、独立校准仍未运行。用户最新“GPU 无关进程都关闭”已实际执行：Qwen 服务停止一次、保持停止，无重启；验证时 530 MiB 已用、15413 MiB 空闲、compute 列表空。旧 R450 pending 已被该明确指令覆盖，不再作为授权阻塞；此快照不是未来独占预约。

同一根因：reader 自行重建旧 Qwen 请求及虚拟离线身份，未跟随生产端不可变有效设置。

- `verify_role_probe_evidence` 和 `_b0_expected_request_body` 硬取 `temperature/num_predict`；`_audit_ced_case` 再次硬取相同字段。Sol 实际为 `reasoning_effort/max_completion_tokens`。
- nominal reader 的 grounding adapter 写死 localhost；精确 Sol 的官方路由校核会拒绝它。
- B0 SUPERVISOR 的无网络编译同时写死 localhost snapshot、默认 Ollama adapter；因此仅替换三处参数仍无法通过。
- `_join_b0_cost_wire`、原字节长度/hash、frame/snapshot/source、typed context、physical audit 与成本核算是已有独立门槛，保留原语义。

## Global Constraints

- 本轮只产计划及 intake；产品、测试、API、MuJoCo、render、dispatch、服务操作均为 0。不读取密钥、运行数据库或环境内容。
- 未来 P0 只准改 `src/cloud_edge_robot_arm/research/freeze_evidence.py`，新建 `tests/test_sol_evidence_reader.py`。不改 model_resolver/planner、旧 fixtures、旧 schema、角色准入或 native 规则。
- 保留 Qwen 历史身份及证据；不得把全部测试模型换为 Sol。原件、历史失败、旧 source generation 不覆盖。
- 可见标记、顶视相机、OpenCV、当前控制器保留；边缘模型后置。truth 只供离线复算。
- 一次预期 RED、一次 GREEN、一次相邻回归、各一次有限静态检查。非预期失败停止相关实施，再交实际 Astra；不先连跑后补计划。

## Review Focus

1. Sol 完整 nominal reader 必须有正向原件路径，不能仅证明 helper 或所有返回 unavailable：见节点 1。
2. SUPERVISOR typed context 必须真实编译且不联网，不能复制 body 当 expected：见节点 3。
3. 改参数并同步重算外围 hash 仍应因有效字段不符被拒；不能只依赖文件 hash：见节点 4。
4. 官方两种 base/path 组合须绑定原 endpoint_hash，不用合法占位 URL 掩盖错误原身份：见节点 5。
5. Qwen think、缺原始文件、成本/长度/角色连接与 source 变化仍保持拒绝：见节点 6 和原 `test_ced_initial_freeze.py` 相邻回归。

## Task 1：最小 reader 修复（P0，未来软件实施）

**Files:** 修改 `src/cloud_edge_robot_arm/research/freeze_evidence.py`；新建 `tests/test_sol_evidence_reader.py`。`model_resolver.py`、`planner.py`、`role_models.py`、probe/pilot 是只读契约来源。

**Interfaces:** 外部函数签名及 reader 返回结构保持不变。仅增加两个私有帮助函数：

- `_recorded_chat_fields(settings: Mapping[str, Any]) -> dict[str, Any]`：返回不含 messages 的完整 wire 顶层字段，即 model、response_format 和 `compatible_chat_generation` 的结果。Sol generation 必须恰含两项，先严格验证，不用 helper 的空字典默认值填补缺证据；旧非 Sol 路径继续要求原 `temperature`、`num_predict` 存在，保留 `think` 对应 `enable_thinking`，其余由既有合法 snapshot 约束。冻结 response_format 若存在必须等于 JSON object；不随意丢掉实际请求多出的字段。
- `_offline_reader_adapter_kwargs(settings: Mapping[str, Any]) -> dict[str, Any]`：只为纯编译/grounding 返回明确 model/provider/base_url/chat_path，`api_key=""`、`allow_paid=False`。Sol 仅在两个既有官方组合中选择其 base SHA256 与 recorded endpoint_hash、path 同时一致的一项；无匹配即拒绝。不得查服务、DNS、profile、secret 或执行 HTTP。历史 Qwen 保留原非网络 localhost 编译用途；不得把该占位 endpoint 作为原证据输出。旧无 chat_path 的直接 Qwen B0 fixture 保留兼容默认。

- [ ] **Step 1 — 添加六个 CPU 行为节点。** 必须拦住真实网络/renderer/engine；仅用内存 MockTransport（或现有 urllib boundary fake）和 tmp_path 文件。fixture 外层写明 `SOFTWARE_ONLY_READER_TEST`；内部 schema 字段只是待解析测试数据，不能发布为真实 probe/roles-frozen。禁止拿 R460 旧图换标签伪装 fresh。

| 精确节点（均在新测试文件） | 必须执行与断言 |
|---|---|
| `test_sol_nominal_reader_reconstructs_original_wire` | 用真实 `_attempt`、save_captured_frame、production parser/grounder 与 mock wire 生成四次 first/warm 的完整 CPU 原件；使用满足既有 top-grasp 几何的 320×240 合成图、完整实例/三 pass、当前有效 settings/role/source hash，构建临时报告。真正调用 `verify_role_probe_evidence`，断言 available=True、4 次原件复算、scope=NOMINAL_PROBE_ONLY、physical/edge=False。不得 monkeypatch reader、can_accept、frame reader、grounder、成本或 acceptance 为 True。随后单独副本损坏 request/raw、response raw、frame/pass 或费用连接，须 unavailable。 |
| `test_sol_b0_planner_reconstructs_original_wire` | 用生产 messages 与合法 Sol settings 得到完整 PLANNER body；原 `_verify_b0_request_body` 正向通过，替换 task/image/model/extra field 逐项拒绝。 |
| `test_sol_b0_supervisor_compiles_without_transport` | 用真实 typed SupervisionContext 和生产 `supervise` 捕获请求作为输入；原 reader 再独立编译成功，两种官方组合均验证；context frame/episode/instruction/role 变更拒绝，transport 调用数为 0。 |
| `test_recorded_generation_gate_rejects_effective_field_drift` | 覆盖 `_recorded_chat_fields` 所服务的 nominal、B0 planner/supervisor 与 CED wire gate；Sol low/4096 原值通过，至少再用一对合法非默认冻结参数（如 medium/8192）按原值重建并通过。reasoning/token 拒绝仅指 wire 相对冻结 settings 漂移；reader 不得将 low/4096 硬编码为唯一合法配置，其他由 compatible_chat_generation 接受的 effort/预算保持原值。缺项、bool token、旧 temperature/max_tokens/enable_thinking 或多余字段拒绝。坏例重算外围 hash 仍拒绝。不得凭 subset 匹配。 |
| `test_offline_sol_identity_binds_official_route` | 两官方 base/path 的 hash 分别通过；错误 endpoint_hash、交叉 path、provider、非官方映射拒绝；没有真实 HTTP。nominal grounding 与 supervisor 都消费此帮助函数。 |
| `test_qwen_reader_retains_think_and_raw_cost_checks` | 历史 Qwen temp/num_predict、think=False/省略两种 wire 均按生产语义通过；完整 nominal 原件复算至少一条通过。缺必需旧参数、错误 enable_thinking、成本 identity/长度/原响应遗漏分别拒绝；不更改现有 Qwen fixture。 |

fixture 应优先复用现有测试中的合成 observation/transport 工具，但不能把 `_nominal_gate_fixture_for_rejection_only` 的 summary 直接当完整正例。合成图必须经真实 PNG/depth/instances 保存和真实 top-grasp/两 mask 检查，无法构成正例时报告 fixture 问题，不伪造 grounding 字段。

- [ ] **Step 2 — 唯一 RED。** 使用 `spec-templates/reader-red.json` 六节点，预期 6 FAIL：旧 generation KeyError/对应 unavailable 断言、Sol route ValueError、新 helper 缺失、Qwen think 完整 body 不符。fixture setup/import/网络/engine 错误不属于预期 RED。保存 stdout/stderr/JUnit/events/result/source pins；不得用新失败覆盖原件。
- [ ] **Step 3 — 最小实现。** 三处旧字段重建统一调用 `_recorded_chat_fields`。nominal 与 B0 expected 均拼完整 messages；CED 原 wire 循环用 `{k:v for k,v in body.items() if k != "messages"}` 与完整 fields 精确比较，保留后面的 role-specific 全 body 核验、image matching、raw/cost join 与 physical audit。仅替换旧字段部分，不搬移整段审计器。
- [ ] **Step 4 — 修正两个纯离线身份。** nominal 用明确 kwargs 构造 adapter，继续原 `_ground_response` 与原 evidence 对比；不加虚假 snapshot 元数据。SUPERVISOR 用同一 kwargs 的合法 endpoint 构造原 ModelConfigSnapshot，并明确给 `_MessageCompiler` provider/base/path/model/snapshot。其 `_request_visual` 仍只捕获一次然后抛 `_Compiled`，不调用父 transport。Sol 验证产生的 snapshot evidence 必须等于原 `_model_evidence(settings)`；Qwen 的离线 placeholder 不改变原 evidence/hash 计算。
- [ ] **Step 5 — 唯一 GREEN 与相邻回归。** 先 reader-green 六节点全部通过，再 adjacent-green：`tests/test_ced_initial_freeze.py tests/test_rgbd_role_models.py tests/test_openai_sol_visual_migration.py`。这是完整 caller/raw-cost/legacy 邻接回归，不运行物理或全仓套件。P0 是软件证据，尚不能声称真实 fresh role 通过。
- [ ] **Step 6 — 收口与交付。** 两个允许路径各一次 import sorting/ruff format 后，依次运行 ruff、format --check、mypy（只检查产品 reader、follow-imports=silent）。不得新增 blanket Any/ignore、修改旧 source inventory 验证绕过问题。ROOT 做一次范围复核，保存 step-report/phase-summary，按显式路径交付；不在本规划 agent 中提交。

### 精确验证与监督

`plan.json.verification_specs` 与 `spec-templates/{reader-red,reader-green,adjacent-green,ruff,format,mypy}.json` 是冻结命令/路径/环境。解释器为 `.venv/bin/python`，pytest 用 R413 events 与 R235 prerequisite，独立 basetemp；不继承真实秘密环境。从已冻结 R458 runner 创建本轮 `implementation/run_stage.py`，保留 R413 supervisor，仅将原“全部前置 rc0”规则精确改为 reader-red 必须命中上述预期后才放行 green；其余全部 rc0/reaped/no drift/no remaining。记录启动时最终 spec 和运行源码 pins，禁止覆盖旧轮次结果。

未来 ROOT 执行命令统一为 `.venv/bin/python <本轮目录>/implementation/run_stage.py <stage>`，stage 只允许上述六项、各一次且串行。reader-green/adjacent-green child 上限 180s，其余 120s，outer 额外 30s；RSS≤4GiB、每 stage 文件≤2GiB、无端口、无实际模型/渲染/物理。新增预期测试后 source pins 仅允许两个产品路径差异；先复核其余输入。一次格式整理可以在 GREEN 前完成；GREEN 后只允许不改变语义的格式整理，若语义又变必须先解释适用性。

## 后续主线（条件路线图，不是本轮执行清单）

| 阶段 | 具体产物与边界 | 依赖/停止条件 |
|---|---|---|
| P0 | 本计划的软件 reader 修复及正向原件复算 | 未来沿既有授权实施，先复核计划与输入；本次只规划。 |
| P1 | 当前 v2 的 fresh Sol nominal probe + 原始 request/response/RGB-D/instances + 独立 reader | P0 稳定并冻结新 source；重新只读核验 GPU/磁盘，使用已存在 profile/session secret 边界，不读取或写密钥。另行冻结实际命令和额度才运行。 |
| P2 | `native-r439-0001` 首个 full-H 教师原组与独立 byte reader/calibration 复算 | P0 稳定后可与 P1 的 CPU 准备并行；实际 GPU 阶段串行。**不以 P1 PASS 为教师业务前置**；同样不以教师通过代替云角色资格。 |
| P3 | 其余独立校准 → 正常抓放与 native consumer/Memory/SQLite → 离线可恢复资格与 B0 selection → foundation/INITIAL → T12 → T13 → METHOD → 独立功效 → FINAL | 按下述既定先后及各自原证据推进；本轮不放行新增批次、正式研究或硬件。 |

### P1：最小当前云链，场景标签必须准确

现成 `probe_rgbd_roles.run_probe` 使用 `SimulatorConfig` 默认 **`assets/robots/franka_panda/scene.xml`**，320×240、S01 seed0、grasp v2、red→green 原指令。它不是 marker outboard 场景。可先用它完成基础场景的最小 cloud nominal 贯通；报告必须明确 base scene，不能说已验证 marker full-H。若下一次要求直接在带标记场景做 Sol probe，则先另轮限定 asset/config-source 登记计划；不在 P0 顺带改 probe，也不将主线的可见标记改回无标记。

建议下一真实额度上限为 **1 first+3 warm=4 次串行 API**，精确 Sol、low、4096 completion tokens/次（含推理；合计上限16384，不是费用报价）、180s/次、retries0。当前 capture session 只有 initialize/reset 与四次显式三 pass，未调用 step；按当前源码拟 0 physics steps、4 explicit、1 reset implicit、≤14 render passes，必须由实际计划重新冻结计数后才能使用。拟 outer≤900s、RSS≤4GiB、raw≤1GiB，无 dispatch。

每次保留真实原始字节/成本账/usage；授权前先核对本地 raw 交付边界、profile route/model/generation、配置与 source。同步/geometry/parse/refusal/transport/source/resource 任一失败停止余下调用、保留未执行分母，不自动重试。现 `run_probe` 只对 BLOCKED 立即停，不能直接宣称它对 geometry FAIL 也早停；下一实际计划可采用短 round-local 顺序 wrapper 调既有 `_attempt`，每次核验事实后再发下一次，最终用现 reader 验证完整四次报告。wrapper 需独立记录来源，不新增通用框架。

验收同时读 VisualDecision/parse/几何与两 mask；`observed_scene != None` 不能独自证明可执行。P1 只授予该场景/源码的 NOMINAL_PROBE_ONLY，不认证 remote weights、物理抓放或 native。

### P2：首个教师完整组，沿原额度重新生成来源

`native_calibration_collection.build_protocol` 明确 provider/model=None、model_requests=0；`native_collection_application` 拒绝 planner_factory/visual_role_binding。教师采集走本地像素、同 grounder/controller/Shield 与受限 TEACHER_COLLECTION 权限，并保留 UNKNOWN，不能借 Sol role 资格进入 native VALID。

`source_inventory()` 纳入全部 `src/**/*.py`，所以即使 P0 只改 reader，也必须在稳定后使用现 prepare 从真实当前字节生成新 source_generation、protocol、role/geometry/lease 绑定。不得复制旧协议后改 hash；旧 R439/R449 原件与 failed/NOT_RUN 状态保留。未运行阶段使用新 runner/commands/overlay，包括本轮唯一允许变化；不改旧 stage specs。

保持 **`scene_pose_marker_outboard_v3.xml`**、注册 grasp v2、marker7、顶视相机、原控制器/采样/OC1/TTL5s/hard-stop 等条件。沿原已分配 9 组但仅释放 **1 组、seed439001、native-r439-0001**。既有上限：12960 physics steps、12976 explicit captures、implicit≤12962、render≤64852、wall1800s/outer1920s、RSS8GiB、raw16GiB、disk free≥32GiB、cloud0、retry0。这些是预算，不是实测；新 prepare 必须派生并冻结本代精确计划/实际计数口径，camera 失败的未知 render 不得写成精确0。首次完整组和独立 reader 完成前不释放其余八组。

先只读预检输入/资产/模型路径/几何/owner/worker/时钟/资源并保存，再唯一 full，进程退出且回收后独立 read；Qwen 继续保持停止，不自动 start。失败即 partial/infinity/UNKNOWN，原件保留，新根因另轮；不得补跑、裁掉失败帧、让 truth 反馈控制或用自己的 trial 自授在线资格。

一个完整原组也不等于独立校准完成：R91 对每组完整动作/帧/终态取 G/U/L/M/C 联合最大，coverage=.9，9 独立组件，缺失/失败/UNKNOWN→infinity，q_joint≤0.01m 且所有其他原条件成立才可能获得注册范围内资格。先看首组能否真正完整，再决定后八组额度；正式研究仍 NOT_ACCEPTED。

### P3：回到开题主线

严格沿已冻结总计划的条件顺序：首组通过独立读取后，经独立计划释放其余独立校准组 → 正常抓放正链与三处 native consumer 集成 → 固定机会及 200 组离线可恢复资格（不依赖 T13）和 120 个独立 selection 组 × 4 个周期 = 480 个分配 episode 的 B0 selection → 胜出后另一 120 组 foundation 与 INITIAL → T12 协同 32 episode → T13 有限在线恢复 → METHOD → 另一 120 组独立功效 → FINAL → 正式实验。此处只列既定后续依赖与分母，没有新增实际额度；不能把有限在线恢复前移为 B0/INITIAL 的前置，也不能把独立功效后置到 FINAL 之后。

首组之后另需独立实施计划打通 PRE_SAFETY / PRE_SKILL / POST_EFFECT 三处 native consumer，以及 Memory/SQLite 的当前来源能力；教师原件与离线校准结果不能直接当作在线证书。每个阶段必须区分开发、真实和正式验收，固定机会、组隔离和失败分母保持。不要现在换边缘模型、重做控制器或直接跑大批量；真实硬件不在本轮。

## 路径权衡与 self-review

**推荐：P0 收口 + 两条最小真实证据链。** 工作直接落在读出/真实贯通；P1 与 P2 有明确独立性和共同 source barrier。**立即全量实验**会把尚未取得的当前 v2/完整组证据当成前置已满足，增加失败成本；不推荐。**先换边缘模型或扩展框架**不会解决现有 reader 和首组实际证据缺口，并违背边缘选型后置；不推荐。

自查完成：五个静态缺口属于同一有效请求重建根因；限定两文件，无全局 adapter/schema 放宽；六节点包含完整正向 nominal reader、真实 supervisor 编译和拒绝路径；三处 caller 使用同一精确字段比较，原 raw/cost/physical 门槛保留；输入与最新服务授权一致；P1 基础资产和 P2 标记资产分清；P2 零云与 source generation 依赖分清；预算均为未执行条件，没有新增实际额度或提前资格结论。执行中若发现上述范围外问题，记录下一轮，不借此重构。

本次交付仅计划和静态 intake；测试/API/physics/render/service 全部 0，full NOT_RUN、native UNKNOWN、formal NOT_ACCEPTED。
