# R432 Horizon 局部变量类型修复 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans inline；只实施此项受限重命名，独立评审中的其他问题不并入。

**Goal:** 清除 R431 三个 mypy 报错，保持已验证运行语义。
**Architecture:** 仅在 `_Audit.legacy_time` 的第二个内层循环将局部 `pair` 改名 `interval_pair`；用冻结 pre-GREEN 源码逐 AST 比较证明唯一差异。
**Tech Stack:** Python ast/hashlib，现有 .venv Ruff/mypy。
**Spec:** 本轮 intake/observation.json 和 R431 原验证证据，SHA256 见 plan.json。

## 原始问题与根因

R431 GREEN 91 项 setup/call/teardown 全 PASS，supervisor 无 source drift/live process；Ruff check、format --check PASS。原 static/3-stdout.log 三处错误：reader596 assignment 把 list[Any] 赋给先前推断的 ClockTupleV2；598/601 index 报 ClockTupleV2 不可下标。局部名字跨两个循环复用导致 mypy 推断冲突，不是此轮实测行为失败。

已只读核对：第一循环使用 ClockTupleV2 的 `pair`；第二循环 `for key in ("start", "end")` 的 `_legacy_pair(interval[key])` 返回 list。其子树恰有5个 `Name(id="pair")`：1 Store、4 Load；同一函数当前没有 interval_pair；子树外10个 pair Name 全在前面的第一循环，后续没有依赖第二循环变量值。所有16项输入 pins 匹配，reader 与 R431 implementation/pre-green-reader.py SHA 相同：2e9605ef5bc9fba5f0a61c9f69d1fe6900111dc74958cb32f4ac57dec0726b5e。

唯一可改产品文件 `src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py`。其余两个测试和 rational kernel 三文件 SHA 不变。实施前复核 pins、原91 PASS/JUnit/原失败日志及当前 HEAD/分支上下文；旧 plans、原件、snapshot、manifests 全保留，不动 dirty gitlinks。

## Task 1：精确 alpha-renaming 与聚焦静态检查

- [ ] 只在 `_Audit.legacy_time` 内的 `for key in ("start", "end")` 循环，将赋值目标与四个读取从 pair 改为 interval_pair。第一循环 ClockTupleV2 pair、方法名、其他变量、条件、消息、调用、返回与所有字段不改；不加 cast/Any/type-ignore，不改 mypy配置。允许仅该循环内 formatter 所需换行。
- [ ] 新建本轮 implementation/verify_alpha_equivalence.py，解析冻结 R431 implementation/pre-green-reader.py 与当前 reader。按结构定位唯一 ClassDef `_Audit`→FunctionDef `legacy_time`→For(target=`interval`, iter=`self.raw["legacy_intervals"]`)→For(target=`key`, iter=Tuple("start","end"))；不按漂移行号或全局字符串替换匹配。
- [ ] 验证旧目标子树恰5 pair Names（1 Store/4 Load），新子树恰5 interval_pair Names（相同ctx）且没有pair；旧整函数无interval_pair；两者子树外 pair Name AST 及全部语句不变，尤其第一循环10个pair Name仍原样。只把新选定子树的这5个 interval_pair Name.id 逆改回pair，再要求整个模块 `ast.dump(include_attributes=False)` 与旧 AST 完全相同。不得全局归一化同名变量、忽略常量/调用/条件/类型或换用新的 baseline。无其他命名捕获或第二循环后变量读取。
- [ ] 等价证据保存 old/new源SHA、冻结源SHA、节点结构路径、rename_count=5、Store/Load计数、子树外不变、normalized whole-AST equality与digest。其余三个文件逐 SHA 等于原pins。保留受限diff；若额外差异或数量不符，停止，不“放宽”等价条件。
- [ ] 在本轮 fresh validation/static 依次运行 plan.json 原三条静态命令，每条一次、timeout_s=60：Ruff check 四文件、Ruff format --check 四文件、mypy --follow-imports=silent 两源文件；全部returncode0。原 mypy配置的 unused-section note 可原样保留，不是新错误。保存命令/cwd/时间/stdout/stderr/result及post-source pins。若需 formatter，只限允许源文件且diff仍限目标循环，重命名前后完整AST证明必须覆盖最终版本。

## 验收、证据与边界

软件验收=五个Name受限等价证明、其余三文件hash不变、三项聚焦静态PASS。不重复跑91项：明确原91 PASS属于R431运行，R432通过局部变量无捕获的alpha-renaming证明行为保持，不声称本轮再跑91。独立 R431 闭环审查继续独立，不能因本轮静态通过将其标为已接受。

本轮只新增implementation/validation/步骤报告/阶段总结；历史三处mypy失败及旧计划原字节保留。延续R431纠正事实：COMMAND原result含physics_state和command_records；live COMMAND未在本轮运行，不能恢复此前错误“缺physics_state不能MARK”说法。实际完整H producer、原deadline/hard-stop守卫、独立校准与正式native仍NOT_STARTED/UNAVAILABLE/UNKNOWN。

任何pin漂移、AST超出限定差异、静态新失败/超时或新根因立即暂停，保留失败并交下一实际Astra；不得重试、加时、改type配置或扩修语义。现有.venv工具无需安装，禁止新增模型/网络/硬件/MuJoCo/全suite。父任务完成已授权明确路径commit/push/SHA核对；本planner只写计划，不改代码、不跑测试/Git。
