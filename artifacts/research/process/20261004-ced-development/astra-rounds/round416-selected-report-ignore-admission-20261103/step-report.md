# R416 精选报告忽略准入准备

本轮只处理 `.gitignore:64:reports/` 对已授权报告的忽略规则，未修改 `.gitignore`。计划生成前实际只读命令 exit0 表示规则匹配，不冒称 git add 失败。未冻结的 prepare_delivery.py 已增加精确文件、祖先非 symlink、常规文件和排除类检查，并要求实际 NUL check-ignore 的全部忽略项只能来自三轮 reports/。

一次精确 `git add -f` 仅负责报告准入；不得 force-push。原一次 stage/commit/normal push/exact remote 核对额度不增加。最终一次 fresh Astra 审核心清单及确定性元数据追加政策，通过后才允许 Git。

准备时 `python` 命令 exit127，后继原许可 apply_patch 因编排未拦截而已执行；实际失败与补充计划见同级 R417。随后用绝对 .venv/bin/python 重新核对 pins 与最终报告，得到 exit0；这不是对旧失败时点的回填。

本步骤快照到此：准入 helper 尚未运行、coremanifest 尚未生成、fresh review 尚未执行、Git 未写。后续结果写独立回执，不修改已冻结步骤记录。所有35 Python FAIL、6 SKIP、1 INCOMPLETE、2真实外部数据 NOT_RUN 及 Phase12 REJECTED 原样保留。产品、测试与四份最终报告字节未改；完整 raw/DB/缓存等仍不纳入远端精选。
