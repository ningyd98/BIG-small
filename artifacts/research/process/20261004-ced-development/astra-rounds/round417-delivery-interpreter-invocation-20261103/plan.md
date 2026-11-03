# R417 交付前置解释器与成功门补正

实际规划：**gpt-6-astra**。本轮仅补正行政调用，不重新测试、解析结果或生成报告，不增加Git次数。

真实失败为intake/failure.json中的chunk4aadc6：`python`不存在，shell exit127；输入复核及helper-before记录没有执行。随后apply_patch因编排未检查退出码而仍运行，只改了R416原已许可的未冻结helper。不能声称当时前置通过或存在旧备份。

静态复核确认：R416除helper外各pin仍相符；helper当前SHA为`4652d273ec85fbc1f3060eaaf39d420d594628deb57f7823f34c90d96b1b33e2`。旧SHA `e80279a71edd4a20efb3de3d4700c62b3de676d74eb40b4c34c425110b0a4e62`只按R416计划登记来源引用。可用解释器为明确绝对`.venv/bin/python`或`/usr/bin/python3`，无需安装或改PATH。

- [ ] 用明确解释器重新复核输入与输出未存在前置，保存真实exit_code/stdout/stderr。任一步非0或无终态立即停依赖动作，不能把tool返回当作shell成功。
- [ ] 如需修改未冻结helper，仅显式附加R417五文件：plan.md、plan.json、intake/failure.json、step-report.md、implementation-step.json。保持R416所有ignore/路径/祖先非symlink/排除类门，禁止递归扩大。
- [ ] 同时只修未生成README模板的一个链接：`../{r416}/step-report.md` → `../../{r416}/step-report.md`，从R413/delivery静态resolve到实际R416报告；无旧README可覆盖。
- [ ] 静态检查该窄差分并登记新hash；如需当前快照只称R417此刻快照，不能回填旧helper-before。
- [ ] 完成五个小记录后，原R416离线curation可由显式解释器执行；每个后继先检查上一步exit0。已经进入coremanifest的步骤记录不再原地更新，后续实际回执另存许可元数据或local-only。
- [ ] helper实际成功并冻结核心后，仍只做一次fresh actual Astra whole-evidence review；其后原精确NUL准入/普通commit/push/三SHA门不变。失败保留partial，不静默覆盖重跑。

不运行行为测试、产品、SQL、结果解析器或报告生成器；不改最终报告与旧失败，不提前生成coremanifest或标review通过。规划者本次只完成静态复核与写计划，未实施helper或Git操作。
