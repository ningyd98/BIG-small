# Astra 申请表表结构分页限定计划

模型 gpt-6-astra；2026-10-11；仅计划，未实施。

## 原始证据

已规划的段落分页候选A/B在表格内均不改变渲染，须最小拆分表结构使研究部分从新页开始。
- 父代理报告候选A/B renderer均exit0；但视觉QA仍不通过。
- diff-01、diff-02、diff-03的每一页PNG分别SHA相同；不是主观相似，而是三轮同页图像字节一致。
- 首轮已逐页查看：page1研究正文仅首行，研究开发方案栏名被切为page1研究开发与page2方案。
- <ns0:tblPr xmlns:ns0="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><ns0:tblW ns0:w="8763" ns0:type="dxa" /><ns0:jc ns0:val="start" /><ns0:tblInd ns0:w="0" ns0:type="dxa" /><ns0:tblLayout ns0:type="fixed" /><ns0:tblCellMar><ns0:top ns0:w="0" ns0:type="dxa" /><ns0:start ns0:w="108" ns0:type="dxa" /><ns0:bottom ns0:w="0" ns0:type="dxa" /><ns0:end ns0:w="108" ns0:type="dxa" /></ns0:tblCellMar></ns0:tblPr>
- 已读取参考body[19]主申请表tblPr，等同当前表；参考整个document.xml的tblpPr数量为0。

## 输入及 SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/AGENTS.md`：`8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application/开题申请表_集成电路工程_20261024.docx`：`0d4101781b09105eb4d55955e93b048045594f3f26eee4ca53fae243f40c6465`
- `/tmp/bigsmall-opening-application-20261011/build_application.py`：`82b80422b50b4ac0ffc2d71bff3ce5dbf7109b9cf6874f5350d7879dcbcfcdda`
- `/tmp/bigsmall-opening-application-20261011/artifact.md`：`89f2a9230eee0a627d8d63835ec7dff108d776707e13a3a097de9c01dd9f52c9`
- `/tmp/bigsmall-opening-application-20261011/开题报告-2101210559丁亚伟.docx`：`b322171190e2ef86b4a649c9bea16913e7b1cd1db1d55e4e6a43c3ce9a33f0d7`
- `/tmp/bigsmall-opening-application-20261011/iteration-01.docx`：`05434c7ef32c1a03995efef410186b6a89ce9c41cb16e1da4ca30a749fa6b13a`
- `/tmp/bigsmall-opening-application-20261011/iteration-02-candidate-A.docx`：`8d0cc0f8b305287ddb49e4f3d3fe20ab2c4e87be71ed282b307662ef10773df6`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/render_docx.py`：`876d5993324e2faaaa96a68a4f7504642e9a07e6df265b385b2baa03b231369e`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-01/b_render/page-1.png`：`0e3eac5209f66271de7ee6050a9c75a53c856c3516043657f7317b55a4140649`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-01/b_render/page-2.png`：`cc90311af414fc7da6dbaca6b80f8cabcafea15a4f4a7b63e0890ff187ee3fb1`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-01/b_render/page-3.png`：`3db7cae9a85e0cb17162391c72f6863c4e71cc5d44738a075cea8a67f39f2bc0`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-02/b_render/page-1.png`：`0e3eac5209f66271de7ee6050a9c75a53c856c3516043657f7317b55a4140649`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-02/b_render/page-2.png`：`cc90311af414fc7da6dbaca6b80f8cabcafea15a4f4a7b63e0890ff187ee3fb1`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-02/b_render/page-3.png`：`3db7cae9a85e0cb17162391c72f6863c4e71cc5d44738a075cea8a67f39f2bc0`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-03/b_render/page-1.png`：`0e3eac5209f66271de7ee6050a9c75a53c856c3516043657f7317b55a4140649`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-03/b_render/page-2.png`：`cc90311af414fc7da6dbaca6b80f8cabcafea15a4f4a7b63e0890ff187ee3fb1`
- `/tmp/bigsmall-opening-application-20261011/template-fidelity-diff-03/b_render/page-3.png`：`3db7cae9a85e0cb17162391c72f6863c4e71cc5d44738a075cea8a67f39f2bc0`

## 根因与待验证假设

- floating tblpPr假设被当前输入排除：源主表和当前表均无tblpPr，不应删除不存在的属性或归因为浮动表。
- 已验证该renderer对当前跨页表行的keepLines/pageBreakBefore组合没有可见效果；其内部原因未进一步确证。
- 最小结构解法是在表外放置显式分页段，使分页不再依赖单元格内段落规则。

## 限定范围

- 只改任务builder和派生DOCX的word/document.xml，必要同步任务artifact.md记载表结构有意偏离及验证规则。
- 表拆分只在原行边界或研究行三、论文架构标题段之前；保留原tblPr/tblGrid、所有行/单元格尺寸、边框、合并规则、字体字号、段落正文与唯一sectPr。
- 新的表外分页段仅为无可见文字的分页控制；不添加可见续页文字。
- 沿用已存在局部keepLines；候选B表内pageBreakBefore可撤回，避免与表外分页形成双分页。

## 排除范围

- 不改产品、原附件、参考原件、技能、runtime、研究事实、专业名称或宏观规划。
- 不缩字号、不改页尺寸/页边距、grid或单元格宽度、不清理失败证据。
- 输入无tblpPr，不实施浮动转inline备选；如新输入实际出现floating属性，先重新核实并更新计划，不猜测删除。

## C：两表加表外分页

- 第一表深拷贝主表tblPr/tblGrid并仅放行0至5（metadata与background）。
- 第二表保留研究行6和进度行7；两表之间放置独立body级分页段，段内只含w:r/w:br w:type=page，段前后0、最小行高、无keepNext、无额外pageBreakBefore。
- 原行对象及研究正文段落保持不变；不得让相邻表无分隔段而自动合并。
- 正文页自然后续分页；若全栏名完整且布局合格可直接验收。

## D：在论文架构前增加第三表

- 若C研究行仍使栏名跨页/定位异常，或目录标题页分配不自然，则在原研究行正文的三、论文架构段之前拆为两个研究行片段。
- 第二表仅含研究内容至验证方法末段；第三表含三、论文架构起的原有目录与成果段落，以及原进度行。两表之间采用同一body分页段。
- 第三表研究续行复制原研究行tcPr和网格结构；左标签保留空段以满足单元格结构，不重复研究开发方案正文标签；完整六字标签仅保留第二表首研究行。
- 删除续行不适用的vMerge continuation仅限确实存在且跨新表边界无restart时；当前研究行先检查是否存在，不能泛化修改元信息日期合并。
- 目标page1元信息背景、page2研究内容、page3目录成果进度；允许自然4页，保持所有文字顺序与事实。

## 预期迭代边界

- C与D及其属性撤回是同轮预期排版候选，每次独立冻结DOCX和render，不因正常分页预览重规划。
- 只允许上述位置拆表、空分页段控制、候选B无效强制属性撤回；不增加随意空行撑版或调节字号/宽度。
- D第三表若内容自然跨到第4页，接受3至4页并检查进度栏名完整；若新增栏名拆分、空白页或重叠且限定候选不能解决，记录并进入下一轮，不无限迭代。
- 运行时异常、正文变化、源输入变化或范围扩大仍触发新Astra计划。

## 实施和验证

- 先校验SHA并冻结当前候选B DOCX与当前builder（此前A/首轮与diff目录原样保留）。
- 按C生成独立候选，执行结构比较与bundled渲染；若合格即停止，否则按D生成独立候选。
- 逐页检查PNG并保存视觉结论；回读w:t列表与原候选B完全一致，分页段无可见文字。
- 结构验证须有意升级为允许2或3个表：每个tblGrid/tblPr等同原主表；每个原行或拆分片段可追溯，所有原段落恰好一次、有序出现。
- 验证唯一sectPr字节/规范结构不变；除document.xml外包parts字节不变（artifact.md是外部契约）；边框、尺寸、元信息日期合并及内容完整。
- 记录候选SHA、命令/退出码、渲染路径和失败保留清单，生成步骤报告并汇总；不以视觉成功替代研究验收。

## 验收边界

- 研究开发方案完整六字位于研究起始页，无page1研究正文残留单行。
- 标题与后续正文合理同页，全部页面无裁切、重叠、异常空页和栏名拆分。
- 尽量3页，最多4页；不压缩字体、改变专业名称、正文事实或页/表格尺寸。
- 原始失败与每候选证据完整保留；拆表为文档展示所需有意结构变化，不是产品研发或实验验证。

## 运行前置

- python：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- soffice：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice`
- renderer：`/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/render_docx.py`
- 输入SHA仍一致；bundled运行时为实际调用路径；可写任务输出目录独立于已冻结证据。
- 本代理仅计划，不改文档/builder，不渲染。

## 补充冻结证据

候选B冻结件SHA与当前输入一致。
- `/tmp/bigsmall-opening-application-20261011/candidate-A-B-render-comparison.json`：`eddfc8540ea2de6574360a9a46cf87f01f72d3af74926b47cdaf2dcbef660be9`
- `/tmp/bigsmall-opening-application-20261011/iteration-03-candidate-B.docx`：`0d4101781b09105eb4d55955e93b048045594f3f26eee4ca53fae243f40c6465`
- `/tmp/bigsmall-opening-application-20261011/build-candidate-B.py`：`82b80422b50b4ac0ffc2d71bff3ce5dbf7109b9cf6874f5350d7879dcbcfcdda`
