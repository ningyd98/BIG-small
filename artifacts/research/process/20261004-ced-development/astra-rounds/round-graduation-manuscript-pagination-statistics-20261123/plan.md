# 新版毕业论文文档属性页数补充计划

制定模型 gpt-6.2-astra，冻结提交 1af902872c5038ceb598237f17b55cd932f9fa86。

1. 原轮预检在冻结的26页文稿上正常发现数据源差异。旧 Word 模板属性为83词、475个非空白字符、583个含空白字符、1页。冷转 ODT 得到25115词、32246个非空白字符、34488个含空白字符，页数却为14。PDF 实际有26个物理页。

2. 根因假设为冷转换时 ODT 页统计与最终排版不同步。四字段不能全部取自同一 ODT。原回执和冻结 Word/PDF、前轮计划均按字节保留。

3. 限定后续修改范围为新版构建路径及对应验收脚本和报告。预检输入哈希、字体、LibreOffice、PDF 解析器和双次渲染条件须可核对。源回执留在私有验证路径，公开报告保留摘要及哈希。

4. 双次排版确认目录与分页稳定后，从最终发布用 PDF 的页面树直接计数；以 pdfinfo 或等价独立工具核验，并比对实际逐页渲染的页数。OOXML Pages 取该物理页数。Words、Characters、CharactersWithSpaces 分别取同稿临时 ODT 的 word-count、non-whitespace-character-count、character-count。ODT 的 page-count 仅记为诊断值。

5. 只更新新版 docProps/app.xml 的四项。解包比较其余条目内容和该 XML 其他字段；回读验证四值。以最终 DOCX 再导出 PDF，同稳定排版稿比较总页数、逐页提取的规范化文本及逐页栅格；最终交付 PDF 页数须与最终 Word 属性一致。维持原轮汉字计数、全文校验和历史原件验收。

6. 本计划仅记录预检和验收修订，不执行修复、新试次、硬件或模型调用。新失败保留原始证据并按流程另拟计划。

## 输入 SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-manuscript-length-20261123.jALJ1FAD/original-properties-red.json`　`ff6a0708ebf3feca318a23dbf7e1b6fb0e2f6cc588e15bd6bb683ebd2b321581`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-manuscript-length-20261123/plan.md`　`110698b2a257fa70ea7aa661149face377440c485cc460ab74060eec6e8da5a0`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-manuscript-length-20261123/plan.json`　`957d366442b98e4ca290ba0d931c6ecb7dd4006ba03d7c0aaddd4a8f7ff65a41`
- `artifacts/thesis_report/graduation-20261123/云边协同机械臂毕业设计.docx`　`b5281f7c1faa0e984ecd97fa6f031ea2649e0690eecc4ba161f6243dc74847b4`
- `artifacts/thesis_report/graduation-20261123/云边协同机械臂毕业设计.pdf`　`3d4cf90697bcfcb7275980a25eb05562cfffd37ae01ca7ef4b16c4489402d25c`
- `scripts/graduation/build_manuscript.py`　`0fb4ef7d22a3eb6f8c1257666717ac0e42b52c5cccb07072b6fd29ff068fed3c`
