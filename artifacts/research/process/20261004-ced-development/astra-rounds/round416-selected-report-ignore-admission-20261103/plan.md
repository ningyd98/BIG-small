# R416 精选报告的忽略规则准入计划

实际规划：**gpt-6-astra**。本轮仅解决用户请求报告的Git登记前置，不运行测试、不修产品，也不修改`.gitignore`或旧计划。

真实证据为intake/ignore-evidence.json：`git check-ignore -v`返回0，匹配`.gitignore:64:reports/`。尚未尝试stage，不能记成已发生git add失败。允许下述**一次精确文件清单的git add -f**；其含义仅是纳入明确忽略文件，不是force-push。

- [ ] 保留输入hash，窄改尚未冻结的curation helper：只附加R416本计划/intake/必要小记录与准入审计说明，保持原排除与脱敏边界。
- [ ] 冻结最终报告和core manifest：每项精确path/bytes/SHA，常规文件、无symlink祖先、不越出授权round；不得递归纳入整个目录。
- [ ] 用只读`git check-ignore -v -z --stdin`审计候选及最终追加文件。被ignore者只允许已授权R413/R414/R415的reports路径且匹配原reports/规则；其它忽略项停止准入，不改规则、不用-f顺带纳入。DB/WAL/SHM/tmp/cache/resources/权重SDK/完整raw/凭据/两gitlink等继续禁止。
- [ ] 一次fresh actual Astra whole-evidence review通过后，按已审元数据政策生成最终manifest及精确NUL路径清单；review/manifest自身追加也必须经过范围、hash和ignore检查，避免自指或审核后内容漂移。
- [ ] 再查HEAD=`ab18abd0f82a024b62f4423c946c6585f8d18c65`、研发分支、空index、source/两gitlink保护与所有hash；工具审批后执行唯一stage：

```text
git --literal-pathspecs add -f --pathspec-from-file=<absolute-final-selected-paths.nul> --pathspec-file-nul
```

- [ ] stage后只读核对cached路径/status及blob字节/SHA严格等于清单；偏差即停，不reset或补stage。随后原额度一次普通commit、一次normal push、一次exact远端分支核验，local/upstream/remote三SHA一致。失败不强推或重试。

报告必须诚实保留全测失败、skip、INCOMPLETE、外部NOT_RUN、Mypy未形成有效源码检查及Phase12 REJECTED。控制器结束/报告交付不等于全绿。大raw/DB继续本地保存，精选报告不能冒充完整远端复现包。

本计划仅窄澄清R413“禁force”对精确忽略文件登记的例外，**仍禁止force-push/amend/reset/rebase/clean/目录宽选**；无新增测试或Git额度。原一轮fresh review与精选交付路线不变。当前未实施helper修改或Git操作。
