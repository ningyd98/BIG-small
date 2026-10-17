# 分页属性试验步骤报告

日期：2026-10-11。依据本目录实际 gpt-6-astra 计划实施，全部10项输入 SHA256 一致，见 execution-precheck.json。初始DOCX、builder与三页PNG已冻结在 evidence-before。

候选A在研究栏名和第一正文段增加 keepLines=1。生成 exit 0，DOCX SHA256为8d0cc0f8b305287ddb49e4f3d3fe20ab2c4e87be71ed282b307662ef10773df6；renderer exit 0（session 73755 / chunk 657b2a）。候选B另对两单元格首段设置pageBreakBefore=1。生成 exit 0，DOCX SHA256为0d4101781b09105eb4d55955e93b048045594f3f26eee4ca53fae243f40c6465；renderer exit 0（session 68096 / chunk 24e27a）。

A/B均为计划中预期的局部排版试验。实际三页PNG与初版逐字节相同，研究栏名及首段仍被拆页，视觉验收未通过。保留两个候选DOCX和builder；像素等同的原始三页图保留在evidence-before，比较SHA见candidate-evidence/candidate-A-B-render-comparison.json。未隐藏或替换失败记录。

只读检查表属性不存在tblpPr，排除浮动表假设。转交Astra编制独立表分页结构修复计划，未在本轮扩大范围。

附带cwd错误a89749按计划恢复：用主workspace绝对路径读到计划和证据；交付worktree仍保持原有文件状态，后续复制须核实目标不被占用。

未改正文事实、字体字号、页面和grid；未运行产品测试、真实机器人实验或正式研究验收。
