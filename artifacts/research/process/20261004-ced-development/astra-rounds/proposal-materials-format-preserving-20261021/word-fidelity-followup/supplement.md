# Word原生FODT与日期缩进精确恢复补充

**Actual model: gpt-6-astra。** 本补充仅规划与记录；未更改输出材料、未渲染、未测试。已有冻结plan.md/json不变。

## 新证据

- 未改DOCX基线同为15页，确认初始DOC→DOCX路径已引入分页漂移。 来源：父任务只读回执823a77；对应original-docx-render PDF在本补充冻结。
- 原DOC→原生FODT→无编辑DOC渲染14页；页1–12及14逐字符文本/位置/字体/字号相同，页13字符数同114，但日期段左边界约+9.4pt。 来源：native-noedit-baseline-proof.json及父任务逐字符进一步定位；计划实际只读了该JSON。
- 源FODT P36 paragraph-properties含loext:margin-left=-1.71ic，text-properties含16pt（含Asian/Complex）；roundtrip P33仍-1.71ic而无段落text-properties。 来源：本次只读XML定位回执77ce74；实际读回确认。
- 按父任务定位，字符单位缩进由原16pt变为默认10.5pt求值：差为1.71×(16−10.5)=9.405pt，与观察9.4pt吻合。 来源：父任务font/position读回；计算为原因解释，不宣称尚未执行的恢复已通过。
- 同一27段内容映射已应用原生FODT；非文字styles/geometry/media canonical一致，native-change-proof候选SHA为00126149bb24612d5a86ec8fcad979cb90debf93d9a20cf5c5fb21a70b26c452；原生编辑后DOC据父任务已14页。 来源：native-change-proof.json及父任务渲染结果；本补充不编辑、不重新渲染或测试。

## 唯一精确恢复

原日期段P36的 `loext:margin-left="-1.71ic"` 以原16pt字高求值为 `−27.36pt`，即 `−0.9652cm`。在副本移除该loext左缩进属性，改写同一paragraph-properties的 `fo:margin-left="-0.9652cm"`。其他字体、文字和布局属性不变。目标原左坐标约62.75pt；以原PDF字符实测值为准，容差≤0.1pt。

该调整固定原DOC的实际缩进，防止DOC重存后段落font-size缺失导致字符单位按默认10.5pt重算。恢复后的验证尚未由本规划器执行。

## 限制

- 只增加本supplement.md/json；已有冻结plan.md/json不变。
- 这是原计划W4B的原生载体及精确原值恢复细化；不新增内容、字体或布局设计，不更改产品/环境。
- 原生FODT保持内嵌媒体和原样式；文字修改沿原批准27段映射。
- 精确修改只针对原日期段对应的P36左缩进；执行前枚举该style所有引用，确认没有其他被意外影响的段落。若影响面不同或新根因出现，暂停并再交Astra。
- 采用副本保留原FODT与失败DOC；替换loext:margin-left属性为fo:margin-left，不能保留两个相冲突的左缩进值，其他原属性不变。
- 不修改文字字体/字号、段距/行距、表格、页边距或图像；不得以14页替代完整视觉验收。

## 执行与验收

1. 核对本补充输入hash，保留原计划与原失败证据，确认P36属于评审第13页目标日期段及引用范围。
2. 在新副本将该段样式paragraph-properties的loext:margin-left="-1.71ic"等价替换为fo:margin-left="-0.9652cm"；保持其他属性、text-properties与已批准正文不变。
3. 转换回原.doc并独立渲染；记录实际工具、版本、参数、输出hash。检查日期左边界回原约62.75pt，原左边界90.1pt和显示数值存在小数舍入，坐标差以原PDF字符实测为准，容差≤0.1pt。
4. 在无编辑对照与最终稿分别核对14页、日期字体字号与其他文字位置/样式不发生新漂移；最终稿只允许批准文本变化导致的必要换行，所有图像字节及未修改区域保真。
5. 差异报告将此唯一属性变化列为等价原值恢复，不能再称所有非文字XML逐字一致；媒体/其他样式结构另行核对。若仍漂移，保留结果并停止相关交付，重新规划。

## 验收边界

- 最终原.doc保持14页，无新增页面、剪裁、重叠或错误分页。
- 日期段回原左坐标，字体字号不变；其余未修改页面区域与原版式一致。
- 批准27段内容和所有主要事实完整，媒体原样；唯一格式表达调整明确标注等价恢复，绝不声称原XML完全未变。
- 原始失败、无编辑对照、修改前后及验证证据保留；不提升产品或研究验收。

## 冻结输入

| 路径 | SHA256 |
|---|---|
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/word-fidelity-followup/plan.md` | `53d473aa9af273bd9b051bc4474de8d99fc60cf3ee77983e7400cebbe4869a46` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/word-fidelity-followup/plan.json` | `7f609dee27619b2765b96921d97ec9b61630a00a33c548304249331d84d6acba` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-noedit-baseline-proof.json` | `74db8b4abf37351b45f01e623a251163329ce0f99505c41807bfa6644f23adfe` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-change-proof.json` | `8604fd1009caf1810d1eb0446d2f13bee75eeff0c9e364d84b012f9d85c797d7` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native/开题报告-2501220176 宁业栋.fodt` | `3f2d53a8b25fdc879eebcb31abbf6daf1b9e4ed5b8c6836ef147fe282262ce0c` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native/开题报告-2501220176 宁业栋_修改版.fodt` | `00126149bb24612d5a86ec8fcad979cb90debf93d9a20cf5c5fb21a70b26c452` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-doc-roundtrip/开题报告-2501220176 宁业栋.fodt` | `d2573d8df28b84b09011dd7998c141e05b08f292b1c72cd8c5172fe44ff07bb8` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-baseline-doc-render/开题报告-2501220176 宁业栋.pdf` | `f69753e39405257d07fbed2f3d1350f50950c2ed457bac3d60c1f3cc7c0e5d5d` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-final/开题报告-2501220176 宁业栋_修改版.doc` | `435f67e27d30f7a842085065dc4a54b210486963c85928634a211ef6f1e07500` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-final-render/开题报告-2501220176 宁业栋_修改版.pdf` | `cb0714faa7a37c781779deb0243f6648972eccdfdf3396ace56a5c6311ae2132` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/original-docx-render/开题报告-2501220176 宁业栋.pdf` | `7e9cf967614a83acfb0121c626727bb174c1c35fe2e83e5a2512594f79e8c0f0` |
