# OC1 scoped static correction Implementation Plan

> **For agentic workers:** Preserve root's current execution arrangement. Two bounded execution items; use the existing paused implementer. Only this new plan is written by the planning dispatch.

**Goal:** 修复 OC1 已定位的 I001、E501 和 __reduce_ex__ override 注解错误，保持运行拒绝语义及60用例原分母。

**Architecture:** 只修改原两个owned Python文件的导入顺序、长字符串布局及单个pickle方法的类型注解；先冻结当前源和原失败，再做限定验证。无需新设计确认或重复完整测试。

**Tech Stack:** 现有Python3.12、typing、Ruff、mypy、pytest；stdlib AST/文件SHA比对；不增加依赖。

**Spec:** 根AGENTS.md；round57-operational-oc1/plan.md/json；implementation/logs下原静态失败。完整输入、命令、stdout/stderr SHA与exit均固定在plan.json。

## Global Constraints / Review Focus

- owned仅src/cloud_edge_robot_arm/research/operational_time_v1.py及tests/test_operational_time_v1.py；不改真实clock、身份/因果、TTL/deadline、生产API/fixturecases、测试名字/参数/分母或原判定。
- 不改旧UTC、native、teacher/backend、消费者、配置或Git。不network/model/actual；不重跑60、真实factory或全仓测试，除非新行为变化经新Astra范围确认。
- copy/deepcopy/pickle原异常类型和消息保持；只注解变化不增加成功序列化路径。不得用Any/type:ignore/禁用规则掩盖override。
- 导入重排仅同一from-import的名字顺序，导入模块语句顺序保持；相邻字符串编译所得路径字节必须完全相同。原始source/RED/static日志保留，不覆盖为GREEN。
- 原60pass及真实LinuxCPU工厂证据继续按原发生版本引用；本轮两定向用例不是增加为62个不同用例。原来未测的真实suspend/restart/hostpause、worker/lease/native/研究准入继续未验收。

## 已定位失败、根因与冻结版本

源before SHA256：e7c9180d5245bc45ec17210b67ceae2db8d29bb54c019319dc5933918314185c。
测试before SHA256：66181f73db13ff0dd5bec00b72bf6fc42c26f1df60c86feb3c05aaa29c93b611。

原full-green命令returncode0，stdout“60 passed in 0.11s”；真实startup JSON为PASS_REAL_LINUX_STARTUP_CPU_ONLY。原ruff-format-check returncode0、“2 files already formatted”。原ruff-check returncode1，I001测试import block以及E501第562行132>100；原mypy returncode1，源第55行参数int窄于基类SupportsIndex，返回object宽于基类str|tuple[Any,...]。unused mypy配置提示不是本轮错误，不改pyproject消音。

根因分别为：①同模块导入名顺序不合I规则；②路径字面量布局超过100列，formatter不自动拆字符串；③无返回的拒绝方法被注解为一般object且协议参数过窄。已读本地mypy typeshed/builtins.pyi:134的object.__reduce_ex__(protocol: SupportsIndex,/)->str|tuple[Any,...]以及typing.pyi的SupportsIndex/NoReturn。方法body只抛OperationalTimeError，NoReturn准确描述不返回路径；此修正无需网络资料。

输入ledger/source-hashes及可能稍后出现的implementation报告是作者独立收尾快照；其继续完善不改变本轮根因。JSON将这些标为informational；实现前必须重验两源码、四组日志/命令、原计划、根规则和工具合同的required pins。已读报告如果尚未存在如实记录，不据缺报告推断实现失败。

## 执行项（仅两项）

- [ ] **1. 冻结失败源，做三个等价修正。** required pins一致后，在新目录astra-repair-execution/OC1/static-fix/before/按原仓库相对路径保存两源完整原字节，复制后SHA必须等于上述before；原implementation日志保持不变，freeze清单列原日志SHA而不重写原RED。只改source的typing导入为NoReturn、Protocol、SupportsIndex，并把_LiveHandle.__reduce_ex__(self, protocol:int)->object改为__reduce_ex__(self, protocol:SupportsIndex)->NoReturn；函数体、参数名/默认/调用方式不变，不新增位置专用斜杠，不动__copy__/__deepcopy__。测试按Ruff I001只重排同一from cloud_edge_robot_arm.research.operational_time_v1 import中的名字，不移其他import语句。第562行路径用括号内两个相邻字符串字面量分行，拼接值必须仍为artifacts/research/process/20261004-ced-development/astra-repair-execution/OC1/implementation/logs/real-startup-cpu.json。无新测试/断言/参数。仅在两文件应用所需格式，不扩展代码。
- [ ] **2. 等价核验、窄验证与独立交付。** 先对before/after做stdlib AST比较：测试只对同一ImportFrom.names排序规范化，其余AST包括所有测试参数、路径常量、函数body完全相等；source只允许该typing import新增两个名字及__reduce_ex__的指定参数/返回注解差异，去除这些精确差异后其余AST相等，异常类型/消息/body原样。不泛化为删除所有注解/所有imports。保存equalities与diff。再仅运行以下两个现有测试一次：PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-oc1-static-tests tests/test_operational_time_v1.py::test_foreign_equal_descriptor_and_copied_handles_rejected tests/test_operational_time_v1.py::test_deadline_requires_original_event_causal_link_and_exact_handle。预期2pass，包含owner/token/event/current/deadline的copy/deepcopy/pickle拒绝，不调用真实startup证据写入用例。然后运行两文件Ruff check --no-cache、两文件ruff format --check --no-cache、mypy --cache-dir=/tmp/bigsmall-oc1-static-mypy仅source；使用原环境PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MYPYPATH=src和require_escalated。每命令原样保存新command.json/stdout/stderr/exit至static-fix/logs，预期全部exit0；检查原源码档案/原失败日志/real-startup-cpu.json仍不变。新增static-fix/report.md/json及source-hashes.json，说明三个问题各自修正、AST等价、before/after、2定向通过与原60pass分开记账。交root独审该静止最小diff及日志，最高PASS_SCOPED_STATIC_REPAIR；不用重复运行同两测试或完整60作为形式要求。若AST不等价或任何新计划外失败，停相关修复、保全并交Astra下一轮。

## 实际运行前置与验收边界

本轮无actual允许项，也不补真实clock证据。OC2/3/4实际前置、外部UTC严格路由与原OC1软件独审要求仍按原计划；本轮静态通过只解除这三个静态阻塞，不自动授予原整轮最终PASS或native/full-future/SI/研究准入。

本次规划仅读源码/日志/本地typeshed及报告快照，新增本目录plan.md/json；没有运行pytest/Ruff/mypy、没有执行项目module、没有写两源码/历史原件/Stage/Git。Astra规划角色来自用户指定派单，运行时身份未独立探测。自查已覆盖三根因、两源上限、原失败/初始源码保存、精确行为等价、最小验证和验收分层。
