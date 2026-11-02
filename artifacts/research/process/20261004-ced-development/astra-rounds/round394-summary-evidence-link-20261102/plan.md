# R394 阶段总结证据链接修正

实际模型 gpt-6-astra；代理 /root/astra_r389_revalidate；2026-11-02T11:49:10.225970+00:00。

仅批准R393新phase-summary.md的一处链接目标替换：`../round376-t3-test-input-contract-20261101/phase-step-report.md` → `../round376-t3-test-input-contract-20261101/terminal-handoff.json`。标签、正文、结果与其他链接全部不改。

原局部链接检查报告目标不存在，intake保留原断言；当前摘要与inputs/phase-summary.before.md字节相同，SHA256为fc94e07bc616f454146ce6f9f0b81d35dc78b2fc5f38974684901abd35415704。R376实际terminal-handoff.json存在，记录五长节点终态、4PASS/1FAIL及后续修复门，适合作为原输入修复证据入口。不得创建伪phase-step-report、修改历史handoff或把旧FAIL升级为PASS。

精确替换后预期9066字节，SHA256 `69c81ce75c7065b7c41e1700c83bada833b3a845075b60ccc08bec9499702aaf`。先复核输入再改；本规划未实施。

修后允许一次≤30秒纯静态局部链接复验，覆盖纠正摘要与已选authoritative/continuation两总结，仅检查本地Markdown目标存在；不联网、不执行链接、不导入产品、不跑测试/SQLite。新错误仍停并交实际Astra，不能顺手扩大修复。

原R393计划保持原字节，本计划仅明示窄附加：evidence_rounds允许R394的plan.md、plan.json、original-failure.json、step-report.md、static-link-check.json五个小记录。重复before摘要snapshot仍只留本地，不纳交付；其他9主路径+2总结、38保护pins与所有raw/gitlink边界不变。

保留旧212files/10749045bytes候选清单及哈希；建立新版本candidate manifest/pathlist/audit，更新摘要hash并加入获准小记录，重算真实数量/字节，最终独审使用新清单。不得沿用旧候选批准、整目录stage或修改原R393计划。

R390最终独审已批准准确离线范围，SHAfe10ca2860c5b2c901367a1d6f346a9e874c10e23b63beaf4ebb2014ede5acf9；因果UNKNOWN和browser19开放保持。R393600秒管理clock尚未开始，继续原准备门；不重置clock、不增加commit/push/ls-remote次数或任何行为配额。本轮不执行Git写入/网络。

验收是单链接精确修正、静态检查通过、失败原件不变、候选重新冻结且最终独审接受；之后才能按R393原门交付。完整pins与窄继承条款见plan.json。
