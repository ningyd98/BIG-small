# Astra Round81：原样证据与当前文件质量的精确分类

规划模型 gpt-6-astra；实施者 GPT-6.1-sol。状态 PLAN_ONLY，本轮没有 Git mutation、测试或真实运行。本计划补充 Round77 的原件空白处理，不扩大发布范围，不改变其分支隔离、祖先、载荷审阅、受众及三端 SHA 要求。

## 问题、原始观察与输入

ROOT报告：RW1 Round76已由不同作者独审PASS；独立worktree位于 `/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall`，base `4d40a65059ab75292fa1842bacf62653829808e6`，尚未创建候选branch/stage/commit/push。此状态是ROOT报告，本代理未重新操作Git核验。

本代理只读重算Round76 delivery-paths.txt的63个明确文件，共1285123 bytes。恰有四文件存在字面行尾ASCII空格/tab：producer-before-format.diff 11行、protocol_generation.py.diff 11行、red.junit.xml 56行、red.stdout.txt 56行，共134行。两个diff含统一差异格式的空白context行；RED输出/XML保存原失败文本。逐文件SHA/bytes、全部命中行号与行字节SHA记录在 original-observation.json；该文件不记录行内容。有限9项输入（AGENTS、R77两计划、63项路径表、四原件、本轮观察）及SHA在 input-pins.json 和 plan.json。两计划内容必须对应，实施前复核pins。

尚未执行 git diff --cached --check；134行字面观察不等于Git诊断条数或已发生Git失败。本轮预先规划潜在的预期空白结果，真实命令结果须实施时取得。原始观察按LF拆分并检查可选CR前ASCII空格/tab，不能替代Git的其他空白诊断。

## 根因与有限分类规则

当前源码/新文档的风格要求，与审计证据的逐字节保真是不同验收对象。原样diff中的context空行可含一个格式前缀空格；pytest失败报告也可带空格。删除它们会破坏冻结SHA和失败证据，而它们不是当前运行代码的质量豁免理由。

对最终精确候选清单逐条登记semantic_role，不按扩展名或整个目录自动放行：

- `CURRENT_EXECUTABLE`：当前产品源码、测试、会被执行/复用的工具脚本；必须通过限定质量检查。包括当前producer/test，且command-runner若作为可运行工具交付，不能因位于证据目录改称原件以避检。
- `NEW_PROSE_OR_METADATA`：本次新写/编辑计划、总结、清单和元数据；须通过Git空白与必要UTF-8/JSON等结构检查。
- `VERBATIM_EVIDENCE`：已确定来源且必须保留的原始stdout/stderr/XML/diff/失败收据，以及仅用于来源审计、不会作为当前实现执行的冻结source-before/source-after等。须逐条以source pin核验SHA/bytes和角色理由；它们仍接受内容发布审阅。某文件兼具当前可执行用途时按CURRENT_EXECUTABLE处理，不能重贴标签绕过质量要求。

历史证据候选尚在R77精确pins清单内整理，可按同一规则在执行前逐文件列出真实路径、来源、角色和pins，附逐行可复算例外，不必每遇到一个同根因旧diff再开Astra轮。此许可不是递归纳入历史目录或扩展交付；新增角色/未证实来源、原件hash漂移、非空白故障、新根因或范围变化仍暂停并回Astra。

## 实施与验证

1. 复核本计划、9项pins、R76已独审冻结清单与R77前置。只在已隔离worktree和新输出目录准备最终候选；用户1007及主树不动。对每条候选登记类别、源路径/版本、SHA/bytes、纳入理由；全体路径集合及stage blob必须与候选manifest一致。没有分类的条目不得交付。
2. 在暂存完成后，对**完整候选**真实执行 `git diff --cached --check`，原样分别保存argv/cwd、stdout、stderr、returncode和索引身份（HEAD及staged tree或等价完整blob pins）。不得以后的stat退出码替代；不得用shell管道吞掉失败。若产生空白诊断，保留真实非零值（通常2），不得称“完整diff检查exit0”。完整输出收据也作为证据按hash保存；若将该收据本身加入候选并再次产生同类原样诊断，可依本规则逐项登记，在索引最终改变后重验受影响集合并保存最终完整检查，不能让自引用报告无限更新。
3. 建立 `verbatim-whitespace-exceptions.json`：每一Git诊断逐项映射到明确VERBATIM_EVIDENCE文件，记录诊断类型、1-based行/位置、staged blob SHA/bytes、原件SHA/bytes、对应字节/行hash、批准该原件角色的理由、原始检查输出位置。对new blank line at EOF等非单行诊断记录对应末尾字节范围/hash。解析不了/路径歧义/无法匹配必须人工复核，不能丢弃；不得在报告中复制秘密内容。先核来源与staged字节完全一致，再允许仅字面格式空白的例外；校验每个诊断均被解释，例外不多不少，未分类诊断=0。134行只作已知观察基线，不硬编码未来全部候选Git诊断总数。
4. 对明确CURRENT_EXECUTABLE与NEW_PROSE_OR_METADATA路径子集单独执行 `git diff --cached --check -- <精确路径>`，必须真实exit0。路径参数不得以空子集意外退化成全范围；需要时批次运行并完整汇总。源码现有ruff/type/独审证据若仍绑定相同字节按R77保留并检查适用性，R77要求的候选依赖闭包验证仍完成；本轮不额外重复产品pytest或重跑真实采集。新元数据做必要解析与引用一致性检查；原始证据不经format、strip、换行重写、XML重序列化或重编码。
5. 验收同时要求：完整检查真实状态已保存、其非零确实仅由逐项已审的原样空白诊断解释、严格子集exit0、所有source/staged pins匹配、未分类诊断0、候选内容/范围审阅通过。结果可写 `PASS_WITH_VERBATIM_EVIDENCE_WHITESPACE_EXCEPTIONS`；字段必须同时呈现whole_diff_check_exit、strict_subset_exit、exception_count和unclassified_count。这是交付审阅结论，不把底层非零改成成功。命令失败、配置/IO错误、当前源码或新文档诊断不在例外内；保留真实失败，回Astra。若外部必需检查仍要求整包exit0且阻止交付，记录不兼容并回Astra，不能改规则绕过。
6. 将步骤报告汇入阶段总结，保留所有原件、失败和新证据。按R77核查源码依赖闭包、完整allowlist/对象范围、base是祖先、1007不是祖先、无多余父提交、目的地/受众和内容审阅，随后依已有限定研发交付授权完成明确refspec非force推送并核验交付branch本地/upstream/live远端三SHA。新增检查收据/例外表/报告按明确路径纳入相应审核提交或后续文档提交；每次新提交单独核验，不递归改写已冻结报告。原主branch与脏嵌套工作树继续保留。

## 禁止项、前置与验收边界

只允许本轮计划目录新增计划和有限观察；规划者不stage/commit/push、不改产品/原件、不跑测试。未来实施仅增加分类/检查/报告，不修改.gitattributes、Git whitespace config、全局忽略或CI规则；不strip/改原始raw或日志来过检查；不上传秘密、不扩充完整raw/DB/weights/SDK交付，不把清单当完整远端复现包。

真实运行actual=0；独审PASS为ROOT转述既有软件结论。本轮文档/Git分类验证不新增实验事实，真实运行仍须既有ROOT串行授权、Gate C/D和全部源/环境/原始分母前置；formal继续NOT_ACCEPTED。OC2独立修复不受本轮阻塞。
