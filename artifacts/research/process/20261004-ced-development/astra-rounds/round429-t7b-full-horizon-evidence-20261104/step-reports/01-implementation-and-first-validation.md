# R429 时域与原件覆盖审计：实现及首次验证

新增四个文件：精确有理数S时域模块、完整时段原件字节审计模块和两份聚焦测试。没有修改原整数kernel、R427终点重建器、生产端、控制器、UTC/e/v或硬件路线。

有理数配方以显式登记时基计算五项原持续时间最大值的向上整步、LIFT/RELEASE尾段和额外WAIT；实际float配置另保留hex及精确编码比例。1/240与默认0.0041666667不能混同。原件审计只读内存中两份固定角色原件，重算计划/编译/owner时长及source链接，并核对D账本、backend分母、逐步CONTROL/PHYSICS、命令重放、HOLD、终态采集。支持动作原件覆盖先限MOVE_ABOVE/APPROACH；其他技能不获完整覆盖资格。

一次预期RED：收集和setup/teardown通过，call阶段唯一ModuleNotFoundError。一次GREEN：25项新增、59项原回归，共84项setup/call/teardown通过；JUnit84/0/0，supervisor耗时42.539秒，source_drift和remaining_live均为空。原59项选择包含calibration10及四项旧负例，Astra在R430确认正文优先的执行前裁定。原件测试是手写SOFTWARE_ONLY样例，尤其COMMAND D行不是当前private recorder产物。

首次Ruff有七项长行和一个缺显式strict参数；format与mypy通过。按AGENTS暂停修正，交实际Astra生成R430计划。R430等价修正及三项静态检查已通过，未重跑84项。

验证生成的389个文件、13个符号链接、75,746,227字节已逐项校验并本地留存；/tmp原目录仍保留。该raw副本不进入Git，inventory不能冒充完整远端复现包。独立审查和交付尚待完成。

本阶段仅提供软件结构门。完整样例仍是SOFTWARE_ONLY、producer UNAVAILABLE、guard NOT_PROVEN、native UNKNOWN；没有MuJoCo/渲染/模型/硬件真实运行。下一阶段须完成真实同会话producer、COMMAND D支持和唯一执行入口的强制截止守卫，再采集覆盖完整时段的原件及独立校准。
