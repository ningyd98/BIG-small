# R412：ETEAC 修复的精选交付

实际 gpt-6-astra；UTC 2026-11-03T09:10:45.855304+00:00。基线 ac6351b / research/20261004-continuation，index空；main仍fdb2e94，两外层gitlink指针ddbeb92保持。仅计划/读取外层refs与证据，未进入嵌套工作区，未实施Git或源码修改。

先写合并阶段总结，明确真实旧时点native与严格格式AST桥接、R399超预算未交付、R407子code未知、R409原两writer自然PASS、R40620GREEN、browser43=42P1S/旧19恢复、R411报告补正、40既有lint未修、物理/正式未运行。新轮独立允许一次≤30s官方postformat source_tree_hash，旧native/browser hash原样保留。

现有文件精确候选见 candidate-allowlist.json；加本轮明示summary/provenance/plan/audit小文件。禁止目录gitadd、DB/raw/重复inputs/fixture/trace/截图/dirtylinks及无关旧dirty/untracked。源仅两产品和两新测试。先生成core-content-manifest，冻结所有实际路径/bytes/SHA。

调用一名fresh gpt-6-astra，fork无历史，审全部代码/真实证据/保护门/格式桥接/候选边界；零Critical/Important且ready_for_delivery=true才继续。审查报告注明core hash与仅追加审查元数据政策。final-selected-manifest只在core entries上追加coremanifest自身与两review文件；自身不自引，另单独hash并精确纳入staging。无需第二fresh reviewer或循环helper审查。

新额度：精确NUL路径stage一次≤60s，普通commit一次≤120s，研发分支非force push一次≤60s，exact branch ls-remote一次≤60s。每步内容/refs/指针门通过再下一步，Git写/网络走require_escalated工具审批，不另问用户。无amend/reset/rebase/clean/config/force/新分支/main写；远端变化或失败保存后下一计划。没有新全链30分钟总钟，也无新软件测试。

提交前比对index blob与清单，提交后比对parent/树/路径；push后本地、upstream、实时exactremote三SHA相同才完成。主分支和其余refs、两gitlink保护不变。postcommit最终回执local-only，不追加回执二次commit。精选证据不是完整远端raw复现包。
