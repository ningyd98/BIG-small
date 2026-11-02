# R395 同参数保护门对账

实际 Astra 已用两条原生只读命令确认参数显示粒度差。显式 --untracked-files=all 当前 h3 回放精确等于原 2481192 字节/SHA3330c420…edf54；normal 精确等于被暂停报告的 2481167 字节/SHA025f68d1…acf1。唯一差项是单文件 tests/fixtures/t5_gripper_dev_cases.json 与目录 tests/fixtures/ 的折叠，差 25 字节，不需接受新保护值或改动嵌套工作区。

原 Important/非批准回执与当前原生回放均保留，当前回放不冒称旧原始 stdout，也不等于完整未跟踪载荷字节审计。local-only git_guard.py 仅补显式 all 和最终 v3 清单绑定，静态精确替换后预期 SHA c72d9d810a0b8be48129b47073b8a9a1ac0e5bda2ff9030d2541c59d4eb0c186；git_command.py 保持。阶段实现无新产品测试、SQLite、Git 写入或网络。

本轮六个小记录加入候选 v3；旧候选、完整 status、before helper 和行政脚本留本地。最终独审必须明确解除 R393-I1，再按 R393 原同参数保护门与原一次 commit/push/ls-remote 配额推进，管理时钟此前未启动。
