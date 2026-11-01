# R381 T3 commit_close 线程归属修复计划

本次实际规划者 gpt-6-astra（/root/astra_r380_r381_plans）。这是 R380 完成后的串行计划，当前未实施、未运行测试。完整原始输入 bytes/SHA256、精确 argv/env、预算与验收见 plan.json。

## 原始证据和根因

R376 t3_green_05 stdout/JUnit 记录原 fault.fired=False 断言失败，229.07 秒；r376-poll-diagnostics.json 首个原始异常是 SQLite ProgrammingError：main thread 126621538414720 创建的 reads[job] 在 broker thread 126620733994688 被使用。调用链为真实 _commit_operational_proposal COMMIT→测试钩子 execute→reads[job].execute。job/attempt 为 INTERRUPTED，尚未完成期望的 terminal close 注入。现有完整 manifest 不是此次根因。

reads[job] 在 _b_t3_exercise 的主线程预先创建，而被拦截的 COMMIT 属于 broker。threadlocal current-connection identity 检查在 broker 确实成立，但读取主线程 observer 违规。该观察发生在更早的真实 commit，不能把这次 affinity error 当成预期的“成功 terminal commit 后关闭同连接”错误。

## 最小修复范围

仅改 _b_t3_terminal_fault 的 commit_close 分支中行观察：真实 real_execute(COMMIT) 成功之后，在当前 hook 线程创建独立 SQLite observer，连接 repo.database_path，用 Row 读取原 SQL，并在该线程保证关闭。使用 contextlib.closing 或 finally；普通 SQLite with context 不保证 close。保留 main reader 给原后续断言。

保持 exact COMMIT/current owner/not fired guard、terminal_reason==owned publication completed、原 evidence、对原 writer 的真实 close 和随后真实 SELECT 引发的 closed-connection ProgrammingError。不得 check_same_thread=False、全局改 connect、伪造 fired/终态、替换实际 committed row、修改产品事务或抑制异常。保留 R380 shared-owner 修复。

新增 tests/test_operational_t3_commit_close_contract.py：真实 sqlite 临时库、真实第二线程与 threading.local owner，直接调用实际 fault helper。main reader 由 main 创建；writer/observer 在 worker 线程创建使用关闭。检验非 terminal commit 不触发且 writer 可继续用、terminal 真 commit 后同 writer 被关且原异常为 closed-connection、main 独立读出已提交终态且仍能使用；foreign/noncurrent connection 不触发；observer 退出和 class execute identity 恢复。线程异常必须带回主线程断言并有限 join。短 repo/session 替身只表征 instrumentation 参数，不冒充真实租约授权。

## 串行前提与步骤

1. 必须先取得 R380 required GREEN、confirm_timeout 全断言、same-process restoration、审查和清理/源写入释放回执。期间不得并发改同源或运行测试。
2. 当前 pins 只固定规划时输入。实施前审核 R380 限定 diff，将 closure 和新增 diagnostic contract 的实际 post-R380 bytes/SHA、结果/审查和实际 HEAD 记入 R381/preflight/applicability.json。只允许这一明确前序差异；其他漂移/新根因重新找 Astra。不得伪造未来哈希。
3. 新线程合同一次 RED 60 秒，必须复现同一 affinity 根因；原长 RED 已存在，不复跑旧长节点。
4. 最小 observer 修改；新短合同一次 GREEN 60 秒；R380 diagnostic+原 manifest 合同一起一次 60 秒。
5. 原 test_b_terminal_publication_confirmation_fault[commit_close] 一次 600 秒，走完原全部断言。每阶段另 15 秒清理。新 R381 总墙钟 1200 秒、名义 840 秒，无普通 retry，不复用任何旧预算。
6. 保存原/新异常区别、SQL/thread/connection 证据、stdout/stderr/JUnit/diagnostics、源前后和清理；独立审查、步骤报告、阶段总结、精确交付路径。

环境沿用 JSON 显式 CPU 软件环境与冻结 R235 prerequisite/R373 tracker，独立新 basetemp/DB/artifact/resource，无 SIMULATION_RUNTIME_DB。可原样复用 pinned R377 bounded wrapper + 新 spec，外层另做 pins/前序/R235 gates。当前权限 workspace-write/network restricted/.git read-only，不能宣称 full-access；/proc 只当前 namespace，不冒充全主机审计。无安装/网络/硬件，受保护 temporal 文件及嵌套工作区不变，冻结 runner 不热修。

## 验收边界

必须证实真正 terminal COMMIT 后同 writer close，原 SQL job/attempt SUCCEEDED、lease released、公共 accepted=False、rejection/unconfirmed 文件存在且无最终 result.json，原断言全部通过。仅“fired=true”或异常类型相同不足。新异常必须是实际 closed-connection，而非 affinity。后续失败不得在本轮扩修；保留原始证据并新 Astra 计划。

本轮只证明 CPU 测试 instrumentation 恢复，不能声称全流程、真实硬件/MuJoCo/云端/正式研究通过。交付遵守 AGENTS 逐项验证后明确路径提交推送并核对 SHA；权限受限时保留证据如实说明，不绕过。
