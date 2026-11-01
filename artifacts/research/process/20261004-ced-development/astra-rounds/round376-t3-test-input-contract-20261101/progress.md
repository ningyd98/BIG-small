# 执行账本 — plan: /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round376-t3-test-input-contract-20261101/plan.md

- 用户范围：测试输入和版本登记一致性；本轮仅T3工厂合同。
- Pre-flight: no shared implementation interfaces; long tests depend on short GREEN and smoke.
- 使用用户指定artifact目录保存账本与原件；沿用现有研发checkout。
- 已核对61输入pins、1050起始源；源头fixture及closure原字节已复制，legacy golden原样复制。
- Task 1: RED contract pending; no implementation yet.

- fixture_contract_red: FINISHED, exit=1, 3.252s; reaped=True.

- fixture_contract_green: FINISHED, exit=0, 3.044s; reaped=True.

- Task 1: RED正确复现3个空manifest/6字段缺失；GREEN3 passed（2.20秒pytest/3.044秒外层），真实service.get_run读回一致，前置accepted、无源漂移、无残留。
- Task 2: 源头fixture在create_job前生成独立manifest快照；closure仅增加invalidate原异常和触达诊断，保留原断言。共享smoke进行中；产品与登记/浏览器未改。

- shared_fixture_smoke: FINISHED, exit=0, 3.045s; reaped=True.

- t3_green_01: FINISHED, exit=0, 238.221s; reaped=True.

- t3_green_02: FINISHED, exit=0, 253.500s; reaped=True.

- t3_green_03: FINISHED, exit=0, 246.574s; reaped=True.

- t3_green_04: FINISHED, exit=0, 246.463s; reaped=True.

- t3_green_05: FINISHED, exit=1, 229.955s; reaped=True.

- Resume terminal audit: all 5 original long cases ended (4 PASS, commit_close FAIL); all 8 stages reaped, no residual/source drift per original receipts. Broker COMMIT hook reused main-thread SQLite reader before intended fault. Important invalidate lifecycle requires R380; thread affinity requires R381. R376 budget expired, no relaunch. Detailed proof and namespace limits: terminal-handoff.json.
