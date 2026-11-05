# R435–R437 执行守卫测试报告

日期：2026-11-06（Asia/Shanghai）。本报告对应限定执行守卫交付，并未重跑全库 4751 项或长测。所有结果来自保留的 stdout/JUnit/pytest phase events 与 bounded supervisor；没有用通过数覆盖历史失败。

| 阶段 | 实际结果 | 说明 |
|---|---|---|
| R435 API RED | 2 个预期断言失败 | setup/teardown 均通过，无 collection 错误 |
| R435 初始 GREEN | 157 PASS / 2 FAIL / 1 deselected | 两个测试预期 RuntimeError，实际契约为 TimeoutError；原始失败保留 |
| R435 初始静态 | ruff、format 通过；mypy 4 错误 | 既有边界字段需要明确的 Literal/可空字符串类型收窄 |
| R436 focused | 2 PASS | 精确修正到期异常测试；四处 cast 的行为不变证明保留 |
| R437 三个反例 RED | 3 个预期断言失败 | 分别证实 observer 失败、外线程停止窗口、遗漏 secondary |
| R437 合并 GREEN | **162 PASS / 1 deselected** | 162 项 setup/call/teardown 全通过，无 skip、源漂移或残留进程；耗时 84.08 秒（pytest） |
| R437 静态 | **三项通过** | ruff check、format --check 四文件，mypy 两源文件；mypy 的 unused-section 提示不是错误 |
| 唯一实际诊断 | **1 PASS** | 实际 MuJoCo 两步 + 真实 BOOTTIME 到期；pytest 10.97 秒，supervisor 12.012 秒，cap 60 秒 |

R437 合并 GREEN/静态替代了未执行的 R436 全批验证；实际诊断仅在 R437 运行一次，消耗 R435.diagnostic.1。GREEN 中排除的 1 个节点正是该实际诊断，之后独立执行，并非遗漏或 skip。

真实诊断使用 S01_NORMAL_STATIC、seed=0、dt=1/240、无渲染。原始 10 秒预算在 initialize/reset 前发放，未刷新。一次当前关节同位目标、一次开夹爪、两次 mj_step；24 个检查点允许，原 deadline 后的命令检查拒绝，随后 expired_step 与 closed_step 也拒绝。最终 sim time=0.008333333333333333 秒、physics_steps=2、estop=true，无 observer failure、primary 或 secondary error。另有两次 HOLD/STOP，是故障处理记录，不计为抓放动作。

两次历史/合并回归各有 2 步真实 MuJoCo，唯一实际诊断 2 步，本次研发链累计 6 步；新增反例使用软件 backend，不能冒充实测物理。真实到期拒绝的读数是原始起点后 10.001499563 秒，这只是一次测量；Python 同线程无法硬抢占阻塞中的 mj_step，不据此声称硬实时保证。

原始实际诊断位于 ../round437-guard-observer-closure-20261106/validation/diagnostic/actual-diagnostic/，本地保留。远端交付 trace-summary、local-raw-manifest 和验证日志，不包含该原始目录、完整批量 raw、运行 DB、缓存、凭据、权重或 SDK；清单不是完整远端复现包。

源核对以原始 772 个受控 src/tests/configs/assets 路径为基线：仅既有 backend 改动，另新增研究模块及两个测试；771 个旧路径不变。GREEN 和实际诊断使用同一源码世代。详细原始路径、SHA256、阶段分母、审查修复核对及验收边界见 test-report.json 和 R437 validation/source-audit.json。

验收仍分开：本轮软件与实际小步诊断通过；完整 native guard 为 NOT_PROVEN，full-H producer 为 UNAVAILABLE，native qualification 为 UNKNOWN，完整正常抓放和正式研究验收尚未完成。
