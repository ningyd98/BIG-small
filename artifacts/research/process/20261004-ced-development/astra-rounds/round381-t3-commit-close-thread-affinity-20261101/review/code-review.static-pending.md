# R381 独立代码审查（长节点待终态）

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
| commit_close_green | 已启动；当前 result/JUnit/source-after 尚未生成 | prerequisite accepted；终态与清理未判定 |

JSON 保存原件 SHA256/bytes、当前源 SHA256、原断言精确保持证明与阶段原始记录摘要。这里的源稳定结论是对该次运行前后记录的独立比对，不扩大成对全部产品的另一次执行验证。

## 暂不判断的行为

- 完整 1125 路径 checkpoint：R389 已完成前序复核，本席任务明确不重审。
- R377 browser、R378 registration、R379 asset：属于后续各自计划，尚不纳入当前 R381 快照。
- 硬件、模型、云端、MuJoCo 效果、性能与正式研究验收：本轮只验证 CPU 测试 instrumentation。
- 已 checkpoint 的 temporal 源/两测试与两个历史 dirty gitlink：本轮保留范围，不属本轮修改。

## 结论

`STATIC_REVIEW_PASSED_RUNTIME_PENDING`。检查范围未发现需修复问题；当前不能确认 R381 完整交付通过。必须待原 commit_close 一次长节点完成，继续核对 terminal-confirmation/diagnostics、全部原断言、source-after 与清理，再发布最终审查结论。
