# V3 离线验收工具完整性修复计划

实际规划模型：`gpt-6-astra`。**PLAN_ONLY_NOT_IMPLEMENTED**。仅计划，原计划与fault环境计划保持不变。正式27批次暂停；first-case-02是开发成功小样。

## 已核实问题

本轮只读探针原文及输出保存在 evidence/probe/。命令见 plan.json。其exit0表示成功打印反例，不是验收通过；探针没有创建socket、连接、发包或调用模型。

1. `ContextVar`守卫：主线程合成 `socket.connect` 审计事件被拦截，新thread同事件未拦截，attempts只有1。守卫状态没有传播至新线程。
2. 清单信任缺口：把source_mapping裁为8但保留archive SHA的snapshot仍验证7041原件、expected_sources=8、模块imports=8通过。snapshot字节未锚定，8个模块之外的源与asset可被静默移出验收。
3. 运行结束只比较8个模块。新增模块、CLI只有开始记录，测试文件未计入；其他冻结src/assets未于finally复核，可能在运行中变化而仍成功。
4. new_output缺批准根白名单，audit-child更直接写文件，未经过目录guard。此项为静态可达性证据，本轮没有向历史目录写入破坏性负例。

真实snapshot SHA：`4ee75e26c90dc6e6e503fea59cf04524f13ddd96238c90189480487d4bccaa8d`。归档SHA：`6fde448feedd3748a0943f28d01197dc66050bd65f4625767af8f3a97294061d`。本轮独立逐成员核对594项（591仓库source、3external），名字集合、长度及SHA均一致；当前仓库591项仅已批准pose_markers.py变化。完整对照见 source-set-audit.json。

## 允许范围

只修改已有本轮新增的3个文件：`src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py`、`scripts/run_v3_marker_offline_regression.py`、`tests/test_sol_molmo_offline_regression.py`。全部既有生产loop、安全、控制、物理、evaluator、相机与阈值不动；原始V3/raw、冻结计划不动。

## 实施与验证

**I1：锚定完整基线。** 解析snapshot及采信任何路径/mapping前，校验上述原始字节SHA。复用已验证数据或每次重读均重新校验。归档也验固定SHA、594个regular成员的精确集合、重复/缺失/多余/路径穿越/链接、长度及hash；591个仓库成员与3external不允许按src/assets过滤或只检查数量。当前唯一既有源码override为marker修复SHA `e6eb27d2b2c19481054c2b834d2ece29a53d747fff26c82d1dd6246ddf71ff40`。

RED在/tmp副本构造裁剪8、删1、重复、同数量换成员、改路径/sha/长度/归档字段；全部必须拒绝。真实snapshot及归档GREEN，保留成员级receipt。不可修改真snapshot来测试。

**I2：进程内跨线程拒绝网络。** 用线程共享活跃guard登记与锁替代ContextVar作为唯一启用条件；单audit hook对每个活跃guard记录一次并在系统调用前抛错。保持context manager接口，嵌套退出、异常、主/新/预先存在thread都不得绕过外层guard。

RED/GREEN覆盖socket.connect及connect_ex审计、UDP sendto/sendmsg（平台存在时）、DNS审计及urllib请求。根据当前CPython实际接口确认事件；send/sendall等无审计出口须用受同一登记控制的最小方法包装进行拒绝，或严格证明不存在预建连接并明确限制，不能自称OS级防火墙。优先覆盖预建socket发送路径。不能扩展为执行任意网络的验证任务。

先使用合成sys.audit和受控方法负例，证明旧线程缺口、嵌套清理与记录计数。真实socket测试仅精确命名节点向工具申请审批提升；guard先启用，connect/UDP发送/外部DNS在系统调用前抛 `OFFLINE_NETWORK_DENIED`。不得用真实无guard连接作对照。PermissionError发生在socket创建时不等于guard通过。最终区分合成审计证据与真实Python API调用证据；所有网络实际尝试均未到系统连接/发包。

**I3：完整运行前后校验。** pre receipt绑定591仓库成员、3外部原件与归档证据、全部3新入口路径/长度/SHA及关键已加载模块真实来源；finally重新读取完整集合和3新文件，比较固定expected与pre。新增3文件实际SHA由实施报告冻结，并与运行receipt一致。不要仅比较8个imports，也不要漏掉异常退出。任一变化使component_success=false、CLI非0、批次停止；同时保存原失败与完整性失败，不能互相覆盖。

RED使用/tmp独立源夹具改变shield、skill_robot或assets等非8模块成员，以及三个新文件分别改变/删除/symlink替换；必须被post发现。不得改真实生产文件跑负例。无变化GREEN，并验证finally在异常中仍执行。

**I4：所有输出入口统一校验。** 允许根仅新隔离树 `artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/` 下新子目录，或/tmp下新任务路径。在任何mkdir、JSON、日志、子进程产物写入前解析最终路径与已有symlink父目录；拒绝根自身、既有run/file、祖先/后代输入重叠。保护原主树、原Gemini树、V3、baseline/归档、astra-rounds、audit-source和其它显式冻结输入，即使输入在/tmp也优先保护。保护根不能单靠未可信snapshot字段派生。

共享路径检查用于new_output和_write；区分独占创建目录与在已批准父目录独占创建文件，避免audit-child重复mkdir。verify/audit/audit-child/case/batch及直接函数入口全部覆盖；外部subprocess日志同样先校验。

RED以无副作用的路径validator测试越界、..、symlink、输入祖先/子目录、已有路径，以及audit-child文件绕过；不要在受保护目录真正写入。GREEN仅批准根的新路径能创建，原字节不变。

## 前置与实施顺序

解释器使用共享venv，但启动前显式固定PYTHONPATH为新隔离树/src及新隔离树，设置PYTHONDONTWRITEBYTECODE=1，pytest禁缓存并用新/tmp basetemp。复核inputs.json；若父任务正实施fault测试导致新文件变化，先核对diff属于已批准范围并追加实施receipt，原本轮输入快照不可覆盖。

按I1/I3/I4/I2先纯软件RED/GREEN，运行新增单元、已有绑定/可选scene/配置负对照及Ruff。需要实际socket时仅请求精确节点审批。再执行上一轮fault三节点，严格4point/1cloud绑定、精确PRE/POST/HARD拒绝原因与真实calls。独立review后才能恢复原27逐例新进程闭环。其renderer/sourcepin环境条件、role version2与完整请求相等要求不变；不通过放松RGB/depth/请求、MSAA/noise/seed或阈值使检查通过。

任何新根因或计划外失败保留原件并暂停相关部分，再交Astra。全项目600s超时仍未完成，不由本轮软件通过代替。原40/589/27分母、0.1mm/39mm、无新增真实Sol/Molmo推理/付费/硬件/公开push边界保持。

输入绝对路径和SHA见 inputs.json；本轮读证据、生成计划，无生产实现或仿真执行。
