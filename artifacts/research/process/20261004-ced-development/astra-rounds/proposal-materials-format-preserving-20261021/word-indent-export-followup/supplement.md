# DOC导出段落基准字体：独立命名样式限定补充

**Actual model: gpt-6-astra。** 仅计划；未改输出、未渲染、未测试。原plan文件不变。

## 已定位证据

- diagnostic.json确认恢复FODT直接渲染14页，目标“日”x=62.75、y=147.32676377952805、字号16；故FODT读取与该绝对负缩进在直接PDF路径有效。
- 父任务已读回DOC目标P33：loext:margin-left=0ic，段落text-properties丢失；漂移限定DOC写出/读回。
- 源P36继承Standard，自动段落样式直接text-properties含16pt。命名段落样式能否保留该原字号基础仍是待验证假设。
- 父任务确认DOCX路径32项tcPr为tcW±1twip真实舍入，故已弃该路径，不对其批量修正。

## 条件授权

允许仅此段的等效格式移至独立命名段落样式，先无编辑对照；这是有界验证原字体基准能否跨DOC导出保留的假设，不是已验证修复。

1. 仅在未编辑原FODT副本中，新增一个仅目标日期段引用的独立命名段落style；继承原Standard，不改Standard。将原P36等效段落/文字属性（原-1.71ic、原16pt Western/Asian/Complex、粗体及其他原有效属性）保存在该命名样式，目标段引用映射保持唯一。其他style、段落/媒体不动。
2. 保存完整before/after及引用清单，证明唯一新增样式载体的有效格式与原P36相同。不得改字号/缩进数值作补偿；不得引入全局默认或影响其他日期/段落。
3. 先仅进行一次无正文编辑的原DOC/FODT→命名样式→DOC对照，导回FODT读取有效字体基准与缩进，渲染核对原14页及日期全串逐字符字体字号/位置≤0.1pt，其他13页无新漂移。首字对齐不足以通过。
4. 仅该对照通过后，将同一经验证的样式载体变更应用于已批准27段文字修改的原生候选，保持原-1.71ic与16pt；重新导出DOC并执行主计划V/S。
5. 对照失败即保留证据并停止此分支，不尝试更多字号/缩进倍数或全局样式；交下一轮Astra。

主计划其他边界保持；样式XML载体变化必须如实披露，不声称非文字XML未变。

## 输入SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/word-indent-export-followup/plan.json`：`05c3d4034e743b8c26d11e1748d30a82deab1df450e3cfb7e057b87f72958b05`
- `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-direct-render/diagnostic.json`：`4295b14037645a8af8b7c308ec179d792865a73a28bbcde68612946173c47731`
- `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-roundtrip/开题报告-2501220176 宁业栋_修改版.fodt`：`0785527793765182c8d7067831a732e490c1b062a3c0a43bb0e583db177f9e6f`
- `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-direct-render/开题报告-2501220176 宁业栋_修改版.pdf`：`06daae1bc4dfb447991a0dde55e7fae11486f73575e4e80b1c0a84eef68ec03e`
