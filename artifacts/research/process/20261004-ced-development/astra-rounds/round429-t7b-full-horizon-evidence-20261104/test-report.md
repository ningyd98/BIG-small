# R429—R433 测试报告

本阶段最终限定回归为92项全部通过，JUnit耗时42.708秒，supervisor耗时43.542413秒。逐节点事件核对：92个唯一STARTED，每个恰有setup/call/teardown各一条PASS；failure/error/skip均为0，source_drift与remaining_live均为空，进程已回收。

| 轮次与阶段 | 实际运行结果 | 后续处理 |
|---|---|---|
| R429 RED | 1个预期ModuleNotFoundError；setup/teardown通过 | 实施两个新模块 |
| R429 GREEN | 84通过，全部三阶段通过 | 首次静态7 E501 + 1 B905保留 |
| R430静态 | 三项通过；受限AST等价 | 未重跑84项 |
| R431 RED | 7个预期失败、1完整正例通过 | 修复COMMAND/CAPTURE联接、时序及严格字段 |
| R431 GREEN | 91通过，全部三阶段通过 | 首次mypy变量类型3条错误保留 |
| R432静态 | 三项通过；精准5个Name的alpha等价 | 未重跑91项 |
| R433 RED | 1个预期缺后续失败原件断言失败、1正例通过 | 改为逐行保留失败并继续扫描 |
| R433 GREEN | 92通过，全部三阶段通过 | 三项静态通过、独立审查READY |

最终92项由7项时段算术、26项完整原件门测试、59项既有回归组成。既有回归为completion10、calibration10、originals35，以及4个native能力/引用/完整未来时域反例。每个运行阶段固定一次尝试、600秒上限，静态每项一次60秒上限，没有因失败延长预算或删减测试。R429初始JSON命令遗漏了59项中的14项，实施前ledger已按规范恢复；实际84项完整包含原59项，原计划和裁定均保留。

当前完整正例是人工构造的3步时段：dispatch=120、return=121、terminal=123，含1步执行和2步HOLD。它验证原件结构与对应关系，不能视为真实生产端采集或长时间运行证据。所有结果固定SOFTWARE_ONLY / UNKNOWN / UNAVAILABLE / NOT_PROVEN。真实全H生产端、执行守卫、独立真实校准及正式native仍未验收。

R429/R431的green临时原件分别保留389个文件、13个符号链接；R433 green保留393个文件、14个符号链接，red保留4个文件、1个符号链接。复制前、复制后及源目录再次清点的SHA全部一致；完整内容仅在本地implementation/post-run-fixture-originals，Git清单不是完整复现包。R433新反例同时保存输入原字节，测试确认审计前后输入编码不变。

所有原始stdout/stderr、pytest-events、JUnit、result、raw-exit、terminal及运行来源pins保留在各轮validation目录。原审查REQUEST_CHANGES不改写，由后续独立审查明确闭合。本次复用的实际Astra reviewer独立于实施，不称为新创建会话。

[最终运行证据](../round433-t7b-original-failure-retention-20261104/validation/green/evidence-summary.json) · [最终静态结果](../round433-t7b-original-failure-retention-20261104/validation/static/results.json) · [独立审查](../round433-t7b-original-failure-retention-20261104/review/final-astra-review.md)
