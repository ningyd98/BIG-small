# P5 后续软件派单准备

状态 PREPARED_NOT_DISPATCHED。不得在ROOT实际派单前写源码、运行测试或actual。继承原Astra总计划与Sol执行计划；目前P3/R92为单写者，P4/R93实际来源尚未通过，P5排队。P2合同已完成但native完整动作支持另由R91规划；本任务只做同机窗口软件，不因native缺界放宽窗口。

原P1/P2/P3已通过证据不重跑；旧UTC路由保持。原Task5给出named正负路径，实施前保存owned当前before/完整diff。新问题先真实Astra，预期RED才可按原计划继续；无Git/模型/渲染或真实运行授权。不同作者独审后ROOT交付。

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

## 窗口接口（原文）

1. `vision/operational_windows.py`（NEW）提供 `OperationalWindowOwner.from_worker(worker: SimulationWorker, *, job_id: str) -> OperationalWindowOwner`、`issue(kind: str, event: OperationalBracket, *, budget_ns: int, parent_ids: tuple[str, ...]) -> str`、`check(window_id: str, *, after: OperationalEventToken) -> EvidenceVerdict`。工厂仅在每个现行job/attempt的实际worker startup内签发，读取当前真实lease/唯一open attempt和私有启动能力，再创建独立OC1 clock；不能接受已结束P4 prefix的owner/lease，也不能用公开worker构造或job_id字符串自授权限。P4只验证来源生产机制，不提供后续任务可借用live权限；prefix适配只在该prefix自己的活生命周期内使用。owner内部持有实际OC1 clock，读取当前D并交叉检查真实worker/lease；ID只指向私有/持久注册窗口，不是调用方给定deadline。`check`不接受caller-now。`export_record(window_id: str) -> dict[str, Any]`为只读持久描述，不输出可复制live权限；恢复必须由同boot/epoch来源重新验证，否则终止原attempt且不重置预算。窗口schema记录domain/boot/source/原事件ID、lower/upper、deadline、parent IDs、job/lease/attempt/fencing和kind。

### Task 5: P5 — OC3时间生产者与窗口计算闭包

**唯一交付/入口：** 可先在P2合同明确后写CPU软件；实际运行必须P4真实来源通过。只迁移应用拥有的同机窗口。

**依赖：** P2, P4

**Files:**
- `NEW src/cloud_edge_robot_arm/vision/operational_windows.py`
- `MODIFY src/cloud_edge_robot_arm/vision/worker_runtime.py`
- `MODIFY src/cloud_edge_robot_arm/vision/supervision.py`
- `MODIFY src/cloud_edge_robot_arm/vision/marker_association.py`
- `MODIFY src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py`
- `MODIFY src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py`
- `MODIFY src/cloud_edge_robot_arm/edge/evidence/models.py`
- `MODIFY src/cloud_edge_robot_arm/edge/evidence/conditions.py`
- `NEW tests/test_operational_windows.py`

**Interfaces:** 生产上文OperationalWindowOwner，复用OperationalClockOwner的within_age/start_deadline/before_deadline，不另造counter；原UTC字段保留诊断与旧协议语义。

- [ ] **Step 1:** 写时间边界RED：5秒允许/5秒+1ns拒绝、deadline等值拒绝、缺pair/foreign domain/copied handle拒绝、合法重叠接受、未来/乱序先拒绝。
- [ ] **Step 2:** 写test_reply_reobserve_and_new_event_do_not_refresh_origin；签发bootstrap/plan/grounding/监督/marker/condition窗口统一clamp原task/verification/lease截止，晚回复不重新起TTL。
- [ ] **Step 3:** 实现schema分派及实际capture/发送/返回/当前事件ID到同域窗口注册；cached frame使用原acquisition而非读取缓存时刻。
- [ ] **Step 4:** 保留外部非空UTC deadline、第三方lease/证书/远端图片严格UTC；无桥接输出UNKNOWN。新增test_external_utc_deadline_cannot_be_relabelled_operational。
- [ ] **Step 5:** 新增test_utc_jump_is_diagnostic_only_for_supported_local_domain以及source/budget变化失效；最小实现后跑owned一次GREEN和静态。

**验证/实际命令：**
```bash
.venv/bin/python -m pytest -q tests/test_operational_windows.py tests/test_operational_time_v1.py
```
```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/operational_windows.py tests/test_operational_windows.py
```

**验收出口：** 生产者使用同一真实D权威；所有本地时间窗口来自原事件和原预算。外部UTC不被覆盖；仅SOFTWARE，实际闭包待P6。

**失败停点：** 发现未知新增窗口类别或源跨域超出列明范围，先保存定位并Astra扩范围；不悄悄给旧now换counter。

- [ ] **交付：** 保存本任务局部报告、原始命令/退出码/完整stdout-stderr、输入输出SHA与actual分母；按下述显式路径Git规程提交。
