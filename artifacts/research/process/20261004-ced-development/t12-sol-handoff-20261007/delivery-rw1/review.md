# RW1 隔离交付候选阶段快照

状态：STAGE_PREPARATION_VERIFIED；ROOT 最终 commit/push 待执行。只包含已独审 RW1 软件及明确必要小证据，OC2/P2/活动阶段总表不导入。

候选分支 codex/research-20261007-p1-delivery，固定 base 4d40a65059ab75292fa1842bacf62653829808e6。用户主 branch/1007 34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e 保留；候选没有1007祖先。隔离树 /home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall，commit/push 均0。

119份固定候选载荷共2,110,247 bytes，63项R76池逐项选择，历史runner因不作为当前工具复用且缺绑定质量证明明确排除，不按证据目录豁免。190项静态import/package/SOURCE_PATHS/recipe依赖已核；只有完整最终producer/test需要源码改变，其他运行依赖base同字节。AGENTS在base缺失，按实际Astra R83的唯一冻结用户政策例外新增，接受strict质量检查，其他前置没有放宽。platform-evidence/report.json为必要硬编码历史小来源；它不证明当前环境可执行actual。

已在候选树用主树绝对.venv/bin/python、PYTHONPATH=src:.单进程运行确切66个唯一case（R76新39+受影响旧27，去重），全部通过，exit0；stdout证实导入candidate producer冻结hash。该运行是导出基线闭包验证，不把历史R76命令改称重复。其他82/19/actual重跑0。新的253项CPU原件只在/tmp保留，清单不冒充完整远端raw/DB包。

初始审阅索引 1d00ba32eae86fac9747fdcc176edf40003e5b34：完整 git diff --cached --check 真实exit2，strict current源码/新文档子集真实exit0。134条诊断均映射4份冻结VERBATIM_EVIDENCE原件及1-based行、行hash、文件SHA/bytes，未分类0。未strip/重编码原件，未改Git whitespace配置。例外表保留初始原blob/检查身份；追加本metadata后，最终whole/strict检查真实收据与最终stage tree由ROOT可读的本地final-stage.json及final-review.md另外记录，不递归把最终收据再stage以追逐自引用。

候选范围内容审阅已完成；origin是既有同一GitHub公开项目（脱敏identity在preflight.json），没有发现需停止的凭据内容。本结论仅覆盖精确候选，不声称全仓无秘密。旧原件引用可能指向未发布的/tmp/raw/local-copy/旧工具，引用不证明远端已具备原件。候选manifest固定payload；published-metadata-paths.json单列元数据，自身pin由最后本地stage blob清单记录。

原prepare assertion保留preparation-failure-1.json，R83恢复命令exit0；RW1原REQUEST_CHANGES与R76不同作者PASS、ROOT核JUnit/接受边界分别保留。源码验证、Git范围审阅不提升RW2/RW3/actual/G4/formal验收。最终ROOT按显式commit-paths清单独立核对后正常commit/non-force push并做三端SHA核验。
