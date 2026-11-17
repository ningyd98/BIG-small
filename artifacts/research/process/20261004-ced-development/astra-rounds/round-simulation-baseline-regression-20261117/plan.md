# 仿真基线收尾与整库续测 Implementation Plan

> **For agentic workers:** 本轮按 `superpowers:executing-plans` 逐项执行。此子任务仅生成计划，未运行验证、修改产品/测试或推送。

**Goal:** 修正三个已确认基线测试契约问题，按原断言与原正式门继续整库回归，准确保留未完成和失败。

**Architecture:** 只修改三个测试文件。历史验证器和生产行为保持严格；续测使用原生 pytest CLI、独立目录及分组预算。LIFT 生产修复由另一轮负责，本计划不覆盖它。

**Tech Stack:** Python 3.12、pytest、Git 冻结对象、FastAPI/SQLite、MuJoCo/EGL、现有模型协议替身。

**Spec:** 父任务明确委托、用户当前 AGENTS 指令、`artifacts/research/process/20261117-grasp-place-repair/report.md` 与 `regression-summary.json`；精确输入及 SHA256 见同目录 `plan.json`。

## 冻结输入与原始失败

基准为 `4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`，不是未来 LIFT 改后源码。计划记录的 Git 输入可用 `git show COMMIT:PATH | sha256sum` 重算。外部诊断与原始三项失败的日志/XML已逐字节复制到 `input-evidence/`，JSON 同时记录原位置、保留位置、字节数和 SHA256；没有复制完整 raw 或改原件。

- finger 原失败：`original runtime source differs from current source: scripts/run_sol_molmo_single_episode.py`。固定原 pin 为 `52df1594ab888038adf7bd21586e691da671817c`；52df 作 current-side 又会报 `one new finger guard loop required`。兼容 current-side `5e68e2f9f1ed7d865f483f41534dec9404c83394` 与 57c4 能通过；当前 4ed5 正确拒绝。
- cloud43001 原失败：预期 0 actions、实际 8。冻结 before 与 post-cloud 两帧在 pre-57c4 tracker 报外圈深度未解决，在 4ed5 均接受。geom-ID 仅离线诊断，不能进入运行控制。此证据只支持该场景旧负例过期，不自动证明新执行物理成功。
- Phase11 原失败是 teardown 线程未停，批次断言本身通过。新诊断看到 MOCK active job，stop 花 1.485s 成功，说明旧竞态并非每次复现；不能据一次成功称生产 stop 已修复。
- closure 九项旧结果一项 -11、八项 120s 未完成。当前 watchdog=20 复现 SIGSEGV，关闭 watchdog 的同项在 120s 超时、约 99% CPU，无 PASS。七项历史约 238–254s；UTC 两项历史合计 4711.366s，**原 combined 600s 正式门未满足**。这些历史完成不属于当前源码 GREEN。

父进程已确认本任务成功以 `gpt-6-astra`、`reasoning_effort=high` 调用；子代理工具不独立暴露模型 ID。调用确认来源已记录于 `plan.json.planner`。

## 全局限制与实施前复核

- 实施前重算输入和审查 LIFT 并行差异。新根因、范围扩大或计划外失败暂停相关修复并另拟计划；不相关工作可继续。
- 不改生产 verifier、BASE_COMMIT、历史 pins、源实验/图像/数据库、dispatcher.stop、全局 teardown、几何/安全阈值、closure 原断言/inner wait/正式预算。
- 不以 xfail、skip、缓存判定、模拟回归结果或删日志关闭缺口。没有整库最终快照重新执行，不宣称最终整库通过。
- 实际运行前确认本地 Git 对象、.venv、绝对 PYTHONPATH、独立 temp/DB、EGL/MuJoCo、CPU 配额和完整时间预算。软件替身、零硬件、零付费模型继续有效。
- 图形任务串行；100ms-sensitive worker 执行期间不叠加饱和 CPU closure 作业。CPU-only 分组先按实际 affinity 限并发，限制 BLAS/OMP 线程，不用竞争负载制造期限失败。

## Review Focus

1. finger 负例可能被当前树另一处漂移提前拒绝，失去对具体 damage 的覆盖：任务1将正负合成例放到兼容 current-side。
2. 改 Cloud `completed=True` 可能掩盖 final admission 绑定缺失：任务2检查 owned fresh stage2 与物理结果。
3. 不启动 dispatcher 可能把批次测试变成内存假对象：任务3保留真实 API/SQLite，并检查精确 membership。
4. 分组续测可能漏节点或把历史结果并入最终树：任务4以最终 collection 和每节点来源核对。
5. 放宽诊断时间可能被误标正式验收：任务4单独记录 UTC combined 600s；诊断-only 无资格提升。

## Task 1: 历史 finger 验证器测试夹具

**Modify:** `tests/test_finger_limit_verification.py`。**Read-only:** `scripts/verify_finger_limit_fix.py`。

- [ ] 保留已有原失败；合成 episode 的 original pins 始终来自真实 Git 52df。
- [ ] 为正例与八个损坏负例构建独立 current-side fixture，字节来自固定 5e68 Git archive/show。只改变测试中 verifier 的 current source 根；原始 Git读取仍必须解析真实 52df，不能替换原 pin函数返回值、guard AST或成功返回值。临时 fixture 需具备可读取原 Git对象的本地 metadata（例如无网络 local shared clone 后导出冻结文件）；清理 cached source读取，避免 fixture 顺序污染。
- [ ] 正例验证 `verified`、`original_runtime_verified`、`EVIDENCE_ONLY_NO_RECORDED_ACTIONS`、`fresh_planning_test=False`。每个损坏负例检查其对应源 pin/清单拒绝，而不只匹配任意无关漂移；backend不得初始化，derived目录不得建立。
- [ ] 增加独立当前真实源码拒绝旧52df的负例。不得为了该负例改变旧 verifier。当前漂移仍须在物理初始化和输出前被拒绝。
- [ ] 原生运行整个 `tests/test_finger_limit_verification.py`，记录新日志/XML、源码哈希和结果；无需真实物理重放。

## Task 2: Cloud seed43001 更新为有证据的成功场景

**Modify:** `tests/test_sol_molmo_cloud_fallback.py`。**Unchanged controls:** `tests/test_cloud_vision_fallback.py`、`tests/test_molmo_grounded_planner.py`。

- [ ] 将唯一 `(43001, development, CANDIDATE)` 过期负例改为完成正例，保留42001 CANDIDATE和REOBSERVE。
- [ ] 实际运行现有 worker/SQLite/MuJoCo与协议替身；继续严格要求物理成功、8动作、单次 cloud 请求及 reservation、一次 native point请求、`UNKNOWN_NOT_GRANTED`，检查明确 hardware dispatch禁用。
- [ ] 检查阶段1只产生候选并要求 owned refresh；阶段2最终计划来自 worker提供的新帧，post-cloud revalidation PASSED，episode/calibration/observation绑定一致且不是复用请求帧。使用实际保存字段，不为迎合测试扩展生产 schema。
- [ ] 运行该文件与现有 cloud fallback/grounded planner独立遮挡、无效深度、过期/复用、episode/calibration漂移负例；REOBSERVE必须0动作。若这些控制不能继续拒绝，停止修改预期并另做根因计划。
- [ ] 保存实际物理结果及请求/阶段证据，只作固定场景软件替身开发验证。新正例失败不得用删assert或更宽deadline处理。

## Task 3: Phase11只测真实持久化批次隔离

**Modify only:** `test_repeated_identical_batches_do_not_merge_historical_runs`。

- [ ] 在该测试创建 client 之前，测试局部 monkeypatch `SimulationJobDispatcher.start` 为无后台线程操作；不改service.start、API、SQLite、批次UUID或公共client/helper。
- [ ] 保留两次相同payload的真实API提交、202、不同batch_id和total=3；增加两次manifest reproducibility hash相同。
- [ ] 两次runs GET均200，每组3个不同run_id，两组不相交；各组恰好等于对应batch响应的run_ids。第二次提交后第一组不改变，6个run的批次归属与真实SQLite/public repository一致。
- [ ] 运行单项和整个 `tests/test_phase11_1_simulation_runtime.py`。其它生命周期/停止相关测试及全局线程回收保持原样，不能把本项通过写成生产stop修复。

## Task 4: 最终源码整库续测与独立预算

**Create:** 新续测命令记录、分组清单、日志/XML和阶段报告；不改closure测试或生产codec。

- [ ] 等最终源码冻结，生成完整输入清单及新 collection；不要硬编码历史7088/7089数。各分组节点精确分区；所有执行均绑定同一最终源码清单。
- [ ] 使用 `.venv/bin/python -m pytest` 原生CLI，绝对 `PYTHONPATH=<repo>/src:<repo>`，每进程独立basetemp/JUnit/log，`-o faulthandler_timeout=0`。不复用发生spawn副作用的pytest.main包装观察器。用进程外timeout和returncode记录；若要采样只使用不改被测语义的安全方式。
- [ ] 七项 startup/terminal/public closure各给已有600s/node开发预算，可在独立CPU进程按实际资源分组；不改inner wait与断言。新超时/崩溃明确记为未完成。
- [ ] UTC保持原来两项合并600s正式裁定，不能通过拆成600s/node或并行抢跑重定义门。若已有授权及可用时间支持3600s/node诊断，单独执行并标 `DIAGNOSTIC_ONLY`；若没有足够运行前提，明确保留未完成/正式未满足，不能推断PASS。闭合正式门需要另外有测量支持的性能修复轮次，不在本计划内。
- [ ] 其它CPU用例分组、图形用例串行，逐节点保留所有失败/重跑历史。结束后检查collection每节点恰有可解释最终状态及来源，missing=0只是记账完整，不代表all_green。
- [ ] 写三层结论：开发软件回归、实际MuJoCo替身执行、正式研究/native/硬件。只有新执行且完整的结果可授予相应开发结论；分段结果始终标派生汇总，不冒充一次无中断native JUnit。

## 验证与交付边界

实施报告必须包含修改前后差异、每步骤命令、环境、墙钟、返回码、日志/XML SHA256和执行源码清单。预期assert RED可按本计划修，任何新生产根因需停该项另拟计划。最终提交/推送由父任务遵从当前授权处理；此规划子任务不提交、不推送。

本计划没有新运行PASS、没有修复完成结论，也没有UTC600s/native/硬件资格。输入摘要不是完整远端raw复现包。

计划生成工具记录：裸 `python` 命令不存在，返回127；随后使用现有 `.venv/bin/python` 成功生成并校验44项输入。此事件仅涉及文档生成，没有运行测试或修改产品。
