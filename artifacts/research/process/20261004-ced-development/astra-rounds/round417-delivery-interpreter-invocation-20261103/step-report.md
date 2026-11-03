# R417 交付解释器与退出码门

保留 intake/failure.json 的真实 shell exit127：默认 PATH 无 python。原编排未检查该退出码，后继 R416 已授权 apply_patch 仍改变未冻结 helper；未运行测试、报告生成器、curation helper 或 Git。不存在失败时点的 helper-before 备份。

本轮使用绝对 .venv/bin/python 进行现在的新核验，实际 exit0。R417 所有 pins、R416 其余 pins 与四份最终报告 SHA 均相符；旧 helper SHA 仅注明来自 R416 计划。当前修改前快照 local-only，不当成旧备份。

后继 helper 差分严格匹配五个 R417 明确小文件的准入和一个未生成 README 的相对路径修正；AST 语法检查通过，链接静态 resolve 指向 R416/step-report.md。原 R416 的忽略准入、敏感排除、祖先非 symlink、冻结与 review 政策不变。

此记录冻结时 helper 仍 NOT_RUN，Git 未写。本轮新增行为运行0，新增 Git 额度0。下一步仅按原计划运行一次离线准入 helper，明确 exit0 才交一次 fresh Astra 审核；结果另存交付回执，不覆盖此历史快照。
