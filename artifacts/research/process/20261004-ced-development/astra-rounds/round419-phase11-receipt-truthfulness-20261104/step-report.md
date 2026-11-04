# R419 Phase11 回执真实性实施报告

实际实施依据为gpt-6-astra生成的R418 first_round Tasks1–3，R419的plan.md/json是逐字采用副本，采用前核对39项输入。新增根因分别由实际Astra R420/R421补充计划处理。实现前HEAD为62a9b91116a6b314fa071eb3f8a6408524cd3d4a；此前长测代码仍为ab18abd0f82a024b62f4423c946c6585f8d18c65。本报告是软件定向验证，不是全量长测或正式研究验收。

## 实现

仅改simulation_runtime adapter和新增test_phase11_adapter_receipt_truthfulness.py。生产_draft及_path_hash的AST与HEAD一致；全局RGBD默认、Worker、repository、recovery service和guard均未改。旧测试断言、旧run输入与原件不改。

每条main/recovery/duplicate probe联接当前SQL job/attempt/lease、真实任务返回事件及本run归档的身份/hash/一致性，并读取现有公开发布确认。空集合、缺件、错run/hash/attempt、未释放、未确认均不能取得完成声明。证据无效优先FAILED/FINALIZATION；否则阻断、超时和实际任务失败分别如实传播。完整执行与任务成功分别记录，任一必需probe可以否决成功。包装器runtime_executed或SQL SUCCEEDED不单独证明执行成功。

事件数加常量的伪毫秒已移出指标。任务完成率依据整个必要流程的真实成功，planner/contract等未经测量的字段保留0/false schema占位并逐项标NOT_AVAILABLE；这些占位不代表已测失败、耗时为零或安全事件实测为零。真实尝试/恢复/去重计数保留来源，receipt写明UNQUALIFIED_TIMING_AND_QUALITY_METRICS，authoritative_for_thesis固定false。真实runner消费边界确认，即使测试manifest声明clean且source hash有效，仍不提升资格；该manifest是单元边界fixture，不是本工作区clean声明。

## RED、发现与GREEN

| 阶段 | 原始结果 | 后续证据 |
| --- | --- | --- |
| Task1汇总边界 | 17项预期call FAIL；setup/teardown均通过 | green-projection 17 PASS |
| Task1原生默认阻断/损坏 | red-native 4项预期外层SUCCESS错误 | 初次green-native为3P1F，恢复租约归档真实不一致，另开R421；不得把3个仅断FAILED的PASS单独当特定损坏被识别 |
| R420连接生命周期 | 独立FD+4条close/hash路径共5个预期FAIL；2个观察器控制PASS | 7项GREEN；见R420报告 |
| R421恢复与观测器 | 新控制2项预期FAIL | 8pure+6native全部GREEN；4个损坏用例隔离为仅main无效并核对具体错误 |
| Task2指标资格 | 3项预期FAIL：固定1、固定true、缺解释 | 3 PASS，包括实际上层consumer |
| Task3真实软件正对照 | 只在测试_draft明确LEGACY_PIPELINE | 原生main/recovery/duplicate均SUCCEEDED且真实task_success；软件完成true，研究/硬件false |
| 最终两文件集成复验 | 指标和格式整理后新scope，无自动重试 | final-new-module 42/42 PASS，pytest27.48s；supervisor28.528s |

所有38个阶段的原始result/JUnit/events/stdout/stderr与source pins均本地保留，validation-summary.json逐项记录。上述次数是分步证据，不把重复case相加成独立覆盖数量。最终42项全部STARTED且setup/call/teardown通过，无skip或INCOMPLETE。没有重跑4751软件全suite、旧Phase12模块或5580矩阵。

## 资源、完整性与边界

R420采用显式close并保留事务上下文，close后再hash。R421仅在公开publication_guard内fresh核对本probe自建的模拟crashed owner/lease、INTERRUPTED及真实UTC expiry，精确release一次，再恢复/requeue。新归档生成时全部历史租约已释放；旧lease的release早于replacement acquire。它不证明通用生产恢复逻辑已修复。

必须撤回此前“lease已全部清空”的旧解读：旧SQL观察器只查NULL，而表以空串表示未释放；旧数值0没有证明力。旧audit不改。typed repository会把空串转None，原collector/main计数本来正确；R421只修SQL观察器。最终新scope用正确谓词，默认阻断与legacy正对照lease均0，observer前/后SQLite FD均0，heartbeat线程空，最终DB hash一致。FD证据独立于旧lease计数错误；原4FD未逐项归因到四个连接，不能宣称宿主进程泄漏。

final-integrity.json核对1309个原运行源文件，仅批准adapter变更，另新增一个测试；69项冻结输入出现项未变。原始失败、错误计数和归档均保留；不会清理日志或改原实验字节。main与两个受保护gitlink指针未改，未声明整个workspace干净。

本地完整raw、DB与/tmp测试归档不属于完整远端复现交付。选择性Git交付只含代码、计划、必要的小型原始测试终态及派生报告；清单/hash不能替代完整raw。最终fresh Astra review及Git三处SHA回执单独记录。
