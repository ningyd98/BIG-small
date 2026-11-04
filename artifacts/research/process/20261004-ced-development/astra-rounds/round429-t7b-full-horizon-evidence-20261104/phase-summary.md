# T7b 完整执行时段证据阶段：R429—R433

已从 R427 的原件重建推进到完整执行时段的离线结构门。本阶段软件实现和限定回归完成，独立 gpt-6-astra 审查结论为 READY_FOR_SCOPED_SOFTWARE_DELIVERY。真实完整动作生产端、执行守卫和正式研究资格仍未验收。研发分支交付后的三方 commit SHA 记录在 delivery/delivery-complete.json；该回执在提交之后生成，不伪称包含在它所核对的提交内。

新增 native_completion_horizon.py 以显式有理数时间网格计算需要覆盖的步数。它核对登记 dt 的 float 编码，综合原始计划、编译计划和有效 owner 的五项时长，明确处理 LIFT 0.5秒尾段、RELEASE 1秒尾段及登记等待，避免浮点累加和已含尾段的重复计算。仅有浮点配置不会自动推断为1/240。

新增 native_completion_horizon_originals.py 从原始字节核验 preregistration、来源哈希、操作边界、COMMAND/CAPTURE完整库存、控制回读、物理步状态、动作返回和后续HOLD。D域和legacy单调时钟按operation ID关联，不把BOOTTIME和MONOTONIC数值直接混比。对缺步、重复、乱序、额外命令、遗漏采集、区间越界、畸形动作、失败与pending保留分配分母及原始失败，不授予正式资格。

| 交付项 | 当前证据 | 验收边界 |
|---|---|---|
| 精确时段计算 | 八种技能算术覆盖、严格类型与时间登记反例 | SOFTWARE_ONLY |
| 完整原件结构门 | 合成完整正例及针对原件联接/时序/字段的反例 | STRUCTURALLY_COMPLETE仅指离线结构 |
| 失败原件保留 | 前条畸形、后条明确失败的组合反例RED/GREEN | 完整原件逐行保留，分母不缩减 |
| 当前限定回归 | 92项，setup/call/teardown全部PASS，无skip | 33项新增功能测试 + 59项既有回归 |
| 当前静态检查 | Ruff、格式、mypy各一次PASS | 仅四个新增源/测试路径对应范围 |
| 独立审查 | R429 F1—F3经R431闭合；F4经R433闭合，R432类型问题闭合 | 无本阶段剩余阻塞，不是全项目审计 |

原始失败均保留：R429首轮静态7项E501和1项B905由R430限定修复；R431首轮mypy3项错误由R432限定变量重命名修复。两次静态修复通过严格AST证明保持运行语义，没有重复运行或改属原84/91项证据。R431七反例RED和R433组合反例RED均达到预定断言位置，修复后才获得GREEN。

前期计划对COMMAND的源码判断曾有错误：backend._operation_result实际先包含physics_state，再添加command_records。已在新计划、fixture、reader和审查中纠正，旧计划原字节保留。当前真实full-H生产端尚缺来源绑定、完整动作验证入口及实际执行的deadline/hard-stop守卫；不能继续用“COMMAND缺physics_state”解释阻塞，也不能把观察回调当执行守卫。

下一开发工作仍沿研究主线：接入同一会话的实际动作生产端和原始时间约束，形成dispatch至完整H的运行证据，再接独立真实校准。当前positive样例是手写软件原件，未运行真实MuJoCo动作、模型或硬件；资格保持UNKNOWN，producer为UNAVAILABLE，guard为NOT_PROVEN。本轮92项不替代历史全量长测，也不解除正式native及S3/S4硬件门槛。云端既定方案、边缘模型后置、端侧OpenCV以及可见姿态标记/顶视相机/控制器方案未变。

1317项既有来源输入保持字节不变。完整批量临时原件和运行环境数据按现有边界仅本地保存；Git只交付明确清单中的源码、手写测试、冻结源码、计划、日志、哈希清单和报告。清单与派生报告不是完整远端复现包。

[测试报告](test-report.md) · [最终独立审查](../round433-t7b-original-failure-retention-20261104/review/final-astra-review.md) · [原始范围计划](plan.md)
