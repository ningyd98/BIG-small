# R381 独立代码审查（最终）

审查席 `/root/consistency_final_review`；基线与当前 HEAD：`fdb2e94d3d7bc041e7d958f2514a08406fad4668`。按 `superpowers:requesting-code-review` 的标准审查 R381 当前窄改。未执行产品导入、测试、网络、信号或 Git 写；仅新建本审查报告。

## 优点与计划符合性

- closure 当前字节由 HEAD 唯一一次精确替换得到：只将跨线程 `reads["job"]` 查询改为当前 hook 线程内 `closing(sqlite3.connect(repo.database_path))`，不包含其他变化。Row/原 SQL/参数与 terminal predicate 保留。
- 真实 `real_execute(... COMMIT ...)` 仍在判定之前。`not fired`、精确 COMMIT 和 thread-local 当前 writer identity 门均保留；独立 observer 读取已提交实际行并在 writer close 前关闭。观察查询失败由 `closing` 负责收尾，错误原样传播。
- 关闭对象仍为原 writer，随后调用原 execute 产生实际 closed-database ProgrammingError；没有状态、flag、结果或 authority 伪造，也没有放宽 SQLite 线程检查。
- 新合同使用真实 OS 线程和 SQLite。foreign COMMIT 与非 terminal COMMIT 不触发；terminal 真提交、writer identity、主线程持久行及继续可读均有断言。query-error 分支验证真实缺表异常和 observer 清理。关闭探测在创建线程执行，避免 affinity error 被当作关闭。spy 只替换 `closure.sqlite3` 绑定，不修改全局模块；线程异常传回主线程，join 有 10 秒上界，class execute 与模块绑定有恢复断言。
- `_b_t3_exercise`、`_b_t3_public_readouts`、`_b_t3_terminal_patch_owner` 与原 terminal fault test 的源片段与 HEAD 完全一致。原 SQL job/attempt SUCCEEDED、lease released、public accepted=False、rejection/unconfirmed 文件及无最终 result.json 的完整断言均保留。

## 问题

Critical：无。Important：无。Minor：无。

## 已核对证据

| 阶段 | 记录结果 | 前置/源/清理 |
| --- | --- | --- |
| thread_contract_red | 2 个预期失败；两例原件均指向 main reader 的跨线程 ProgrammingError | accepted；1053 源记录前后同；无 drift/errors/live/ports |
| thread_contract_green | 2 pass，0 fail/error/skip | accepted；1053 源记录前后同；无 drift/errors/live/ports |
| shared_short_green | diagnostic + fixture 共 6 pass，0 fail/error/skip | accepted；1053 源记录前后同；无 drift/errors/live/ports |
| commit_close_green | 1 pass，0 fail/error/skip；runner 241.577 秒，pytest 240.745 秒 | accepted；1053 源记录前后同；无 drift/errors/live/ports；reaped |

JSON 保存原件 SHA256/bytes、当前源 SHA256、原断言精确保持证明与阶段原始记录摘要。这里的源稳定结论是对该次运行前后记录的独立比对，不扩大成对全部产品的另一次执行验证。

## 暂不判断的行为

- 完整 1125 路径 checkpoint：R389 已完成前序复核，本席任务明确不重审。
- R377 browser、R378 registration、R379 asset：属于后续各自计划，尚不纳入当前 R381 快照。
- 硬件、模型、云端、MuJoCo 效果、性能与正式研究验收：本轮只验证 CPU 测试 instrumentation。
- 已 checkpoint 的 temporal 源/两测试与两个历史 dirty gitlink：本轮保留范围，不属本轮修改。

## 结论

`APPROVED_R381_TEST_SCOPE`。Critical/Important/Minor 均无；R381 测试范围通过，可释放 source writer 并依 R377 原计划即时前置门串行移交。原静态待终态报告保存在 `code-review.static-pending.md/json`。

终态原件独立核对：真实事件 `TRUE_TERMINAL_COMMIT_THEN_SAME_CONNECTION_CLOSE`，实际 durable row 为 `TERMINAL / owned publication completed`、commit 后不在事务。关闭对象 resource id 与 SQLite 资源记录一致，hook 和关闭均在该连接创建线程；实际异常为 `ProgrammingError: Cannot operate on a closed database.`，与历史 affinity 根因明确不同。

job/attempt 都为 SUCCEEDED，lease 已释放；公共 summary 为 UNCONFIRMED/SUCCEEDED/accepted=False，confirmed paths 为空。实际 rejection 文件与记录一致且 accepted=False；23 个 unconfirmed 文件全部存在、逐项 SHA256 相符，最终 `terminal-test/result.json` 不存在。diagnostics 到达 `after_poll_assertions_completed`，poll=True、exit_exception=None。

678 个资源均有 cleanup_observed，close error/存活线程/SQLite 异线程 close 均为空；observers_restored=True、cleanup_errors=[]。四阶段 argv/env 与冻结 spec 相等且 spec pins 相符，long 节点 600 秒内完成；从本轮开始至终态约 303.388 秒，低于 1200 秒总上限。

步骤报告、阶段汇总、R377 即时前置与精确 Git 交付由协调席继续完成。本结论不表示任何新性能、真实运行、正式研究验收、提交或推送通过。
