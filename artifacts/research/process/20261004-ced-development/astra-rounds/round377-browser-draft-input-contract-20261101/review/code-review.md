# R377 独立代码审查（限定 partial 最终）

审查席 `/root/consistency_final_review`；HEAD `fdb2e94d3d7bc041e7d958f2514a08406fad4668`。只读文件/Git/stdlib核对，没有产品导入、测试、信号、网络或Git写。原待定报告按旧bytes保存在 `code-review.runtime-pending.md/json`。

## 优点与限定批准范围

console与HEAD相比恰好新增35字节、一个显式LEGACY_PIPELINE输入字段；override优先级、全部原断言、等待、skip与endpoint完整保留。55个未改计划pins全同；三个overlay仅有允许路径替换，20个research输入运行后仍与原件逐字相等，旧归档结果未冒充新运行。

`APPROVED_R377_PARTIAL_INPUT_SCOPE`：允许此字段与如实报告的partial交付。原18项中E2E-05完整通过Mock单任务SUCCEEDED页面断言，E2E-22通过QUEUED/job_id/queue_position原断言；其余16项未通过。不能称默认通过、40PASS、batch/取消/恢复/retry/replay完成或本次capture通过。

## 实际运行账与清理

| 阶段 | 原件结果 |
| --- | --- |
| 受限默认预检查 | socket.bind8000/5173被拒，launched=false；未开始行为，不计产品RED |
| 默认fresh-env替代 | exit1，40=20PASS/2failure/17error/1原skip，runner454.782秒 |
| console37 | 20PASS/16error/1原E2E-06 skip |
| RGBD3 | 0PASS/1error/2failure，单列新失败 |
| research首次行为 | exit0，3PASS/0failure/0error/0skip，runner22.440秒 |

两组各1058条source记录前后同，source_drift/errors/remaining_live为空且reaped=true；默认8000/5173、research8123/5199均释放。所属身份记录分别197和16条，结论只针对实际runner PID namespace。被reap子进程含终止状态，不能由signals空字段推断全部自然退出。原round_end未改，行为终态前总墙钟539.324秒，低于1200秒；没有行为重试。

research实际spec为 `browser_research_green_approved_context.json`，SHA与invocation b30a5…完全相符；原未执行restricted template仍保留。两者仅权限/升级来源/首次行为/不重置时钟元数据不同，argv/env/预算全同。审查初次错选template的比对已解决，不构成新spec漂移，也不需要源fix或重跑。

## Important：19个开放验收用例

JSON逐项列出16个旧目标未完成与3个新capture失败，共19个Important条目；不等于19个独立根因。源码字段本身未发现缺陷。R390只授权离线诊断；本次不准修queue、改timeout或重跑浏览器。

| 原18用例 | 旧XML | 本次XML | 验收停点 |
| --- | --- | --- | --- |
| E2E-05 creates Mock single experiment | FAILURE | PASS | 完整原断言通过 |
| E2E-07 creates mode comparison batch | FAILURE | ERROR | batch succeeded1/running1/queued1 |
| E2E-08 creates multi-seed batch | FAILURE | ERROR | batch queued3 |
| E2E-11 LiveRun status flow is visible | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-12 LiveRun fault timeline includes emergency stop | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-14 views metrics and chart route | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-15 exports CSV and JSON | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-22 Phase11.1 create run returns QUEUED immediately | FAILURE | PASS | 完整原断言通过 |
| E2E-23 Phase11.1 status advances to running then succeeded | ERROR | ERROR | VALIDATING, LEASED, STARTING, RUNNING, SUCCEEDED未到；末态QUEUED |
| E2E-24 Phase11.1 runtime events persist and grow | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-25 Phase11.1 metrics appear after worker completion | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-26 Phase11.1 cancels a running job cooperatively | ERROR | ERROR | STARTING, RUNNING未到；末态QUEUED |
| E2E-27 Phase11.1 records cancel progress events | ERROR | ERROR | STARTING, RUNNING未到；末态QUEUED |
| E2E-28 Phase11.1 marks constrained runs as TIMED_OUT | ERROR | ERROR | TIMED_OUT未到；末态QUEUED |
| E2E-29 Phase11.1 safe recovery keeps run history queryable | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |
| E2E-30 Phase11.1 batch progress is persisted | FAILURE | ERROR | batch queued3 |
| E2E-31 Phase11.1 retry failed run requeues safely | ERROR | ERROR | TIMED_OUT未到；末态QUEUED |
| E2E-33 Phase11.1 WebSocket replay is persisted without duplicates | ERROR | ERROR | SUCCEEDED未到；末态QUEUED |

三项原本PASS的RGBD新失败单列：

| 用例与断言位置 | 本次XML | 实际停点/未验证边界 |
| --- | --- | --- |
| real dataset capture stays available without a model / rgbd-datasets.spec.ts:13 | ERROR | 45秒总case截断内部60秒SUCCEEDED可见性等待，RGB/depth/frame断言未到 |
| real capture and unavailable visual planning retain distinct evidence / :31 | FAILURE | capture末态QUEUED而非SUCCEEDED，后续visual-planning提交未到 |
| cancelling real capture preserves already committed frames / :61 | FAILURE | published_groups仍0而非>0，cancel请求和保留帧断言未到 |

不能将这三项笼统写成HTTP请求超时，也未证明与console或彼此同根因。Critical无，Minor无。

## research边界

首次实际3项完整原断言通过；summary与真实导出均为SOFTWARE_ONLY、600组/4200分配、4200条BLOCKED、NOT_RUN、formal=false。导出等于页面payload的原断言已完成；missing/unknown source guards保留。模型请求0、物理动作0，不升级为正式研究、真实模型/硬件或效果验收。

## 暂不判断与交接

19个开放用例的根因/修复留给实际Astra R390离线计划，尚不推断单根因。R378/R379、完整checkpoint、受保护temporal/历史gitlinks、性能/硬件/云端/正式研究效果不在本次范围。

两suite已终态、源稳定、所属清理通过；R390明确允许最终独审后独立R378→R379继续，可释放source writer。各轮仍须通过自己的即时pins/前置门，旧browser升级权限不扩散。此交接不授权browser源码修复。协调席继续步骤/阶段汇总与精选partial Git交付；本席没有提交/推送声明。
