# R436：守卫验证契约与既有观察器类型修正 Implementation Plan

> 实际规划者：gpt-6-astra。依已有用户授权，复核输入后直接限定实施。沿用R435执行流程，不另要求用户批准。

**Goal:** 修正两条测试的deadline异常预期，并对既有观察器构造参数做四处精确类型收窄；保持运行行为。

**Architecture:** 产品仍以TimeoutError报告deadline过期。既有 `_emit_operation_source` 的四参数加typing.cast，不新增控制流、不改变值或错误处理。

**Spec:** R435 plan.md；本轮只处理该计划验证时出现的两个测试契约失败和四个静态类型错误。

## 原始证据与根因

R435 GREEN自然结束：159节点，157 PASS/2 FAIL/1 deselected，pytest83.34秒；supervisor FINISHED、returncode1、84.576秒、reaped=true、remaining_live=[]、source_drift=[]。

失败节点均为 `tests/test_guarded_execution_v1.py::test_deadline_equality_identity_and_cancel_fail_closed` 的 `equality`、`later` 参数。原始trace明确执行 `raise TimeoutError("original execution deadline expired")`，测试却只捕获RuntimeError；TimeoutError不是RuntimeError子类。原测试断言因此未走到后续步数/estop检查，不能将157通过称为本轮通过。

mypy四个arg-type错误均在 `backend.py::_emit_operation_source` 构造BackendOperationBoundary：kind/phase是str、预期Literal；row[error_type]/row[error]被推断为object、预期str|None。该方法与R435 `implementation/backend-before.py` **完整方法AST相同**，证据见 `intake/ast-proof.json`。这是本次扩大到backend静态检查暴露的既有精确类型问题，不据此改guard逻辑。R435 Ruff/format通过保留，不覆盖失败日志。

18项输入SHA256在plan.json/input-pins.json；四份当前产品/测试文件及失败stdout/result/JUnit/events/mypy输出已冻结至 `intake/frozen/` 对应原路径。原失败保持原字节。

## 精确实施范围

只修改：

1. `tests/test_guarded_execution_v1.py::test_deadline_equality_identity_and_cancel_fail_closed`：令expected_error在equality/later分支为TimeoutError，其他分支保持RuntimeError。不要用BaseException/Exception大网捕获。两个期限分支进一步确认错误文本 `original execution deadline expired`；原 `total_physics_steps==1`、estop及context退出后拒绝断言必须保留。
2. `src/cloud_edge_robot_arm/simulation/mujoco/backend.py`：typing import增加cast；仅在 `_emit_operation_source` 的BackendOperationBoundary构造处收窄四实参：`cast(Literal["RESET","CONTROL","PHYSICS","COMMAND","CAPTURE"],kind)`、`cast(Literal["BEGIN","END"],phase)`、`cast(str | None,row["error_type"])`、`cast(str | None,row["error"])`。不修改函数签名向上扩散，不改row生成、传值、异常捕获、observer语义。不加type:ignore/Any压制。

研究源 `guarded_execution_v1.py` 与backend新guard行为、新backend测试全部保持字节不变。原4个mypy错误之外若有新错误先下一Astra，不扩大清理。

允许新增本轮implementation验证runner、validation/review/delivery和报告；R435已冻结输入、日志、计划、runner不得覆盖。两个gitlinks保护不变。

## 步骤与检查

- [ ] 实施前复核18项SHA及原159节点分母；当前未运行的R435真实diagnostic额度仍为1，不因本轮增加。
- [ ] 作以上两处限定修改。保存精确diff，并用AST将当前 `_emit_operation_source` 四处cast外壳剥除后与冻结R435方法比较，必须相同；仅新增typing import可在模块比较中例外。确认另两个文件SHA不变。
- [ ] 复用R413 supervisor和R435 runner框架，建立R436独占目录；运行一次focused两失败node，cap120秒，期望2 PASS且全部setup/call/teardown通过。原R435失败已作为RED，不再运行重复RED。
- [ ] 运行一次R435原完整GREEN argv（159节点、真实diagnostic被排除），cap600秒，期望159 PASS/1 deselected，无skip、漂移和残留进程。此重复有新测试/类型改动依据，不运行全库长测。
- [ ] 对两个源补一次mypy（cap60秒）；对实际改动的backend/test各补一次ruff check和format --check（各cap60秒），不复跑无改动另外两文件的格式检查。所有原输出/退出码保留。
- [ ] focused、GREEN及静态通过后，独立审查；真实diagnostic沿R435唯一未消耗额度运行一次。可用R436 runner建立 `validation/diagnostic` 执行原精确diagnostic argv，显式标记 `consumes=R435.diagnostic.1`；R435旧入口不得再执行。若主线程保留R435入口运行，同样新pins记录本轮受限变更，不能同时运行两处。

建议入口 `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round436-guard-validation-contract-20261105/implementation/run_validation.py {focused|green|diagnostic}`；plan.json提供准确argv。新runner使用当前baseline/pins并明确两处允许变化；不能把旧backend hash偷偷覆盖当原输入。R413 supervisor及event/startup插件不变。

## 修订运行额度与验收

- R435 GREEN已发生真实无渲染2步；R436 GREEN同一旧回归再2步；唯一R435诊断再2步：两轮**累计最多6步**，不再是旧计划累计4步。focused全软件0实际步。真实诊断仍只1会话、2步、原始10秒BOOTTIME预算、无渲染/模型/硬件，其他要求完全继承R435。
- 本轮规划不运行任何测试或物理。环境沿R435已有.venv，独占新目录、源pin、进程回收；无需安装、GPU、credentials或模型。
- 新FAIL、timeout、source drift、不可预期节点/类型错误或额外步数：保留原件、停止受影响修复、交下一实际Astra。不得因“只是测试”自行扩修。
- 完成后软件/实际诊断分开报告；不晋升native UNKNOWN、完整full-H producer UNAVAILABLE、完整native guard NOT_PROVEN。按明确路径提交推送并核对三方SHA，历史失败不删。
