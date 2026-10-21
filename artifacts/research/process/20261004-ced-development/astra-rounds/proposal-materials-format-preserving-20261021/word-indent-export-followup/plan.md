# Word负缩进导出失败：限定诊断与恢复计划

**Actual model: gpt-6-astra。** 仅计划；未编辑输出、渲染或测试。

## 新失败及前轮假设状态

- 唯一P36左缩进由loext:-1.71ic替换fo:-0.9652cm后，原DOC导出仍14页，父任务核对151段目标文字与3媒体hash正确；这些不证明日期布局正确。
- final-native-layout-proof.json实测第13页“日”x从62.75变为90.1、字号16及y147.33不变；“期”“：”同向偏移；数字“2”从107.2变136.1，其差不与首字完全相等，因此验收必须逐字符核对，不能仅看首字。
- 封面1、说明2、签字14页字符位置字体字号同原稿。
- native-indent-restoration.json中的basis所称“restores original 62.75pt”仅原拟恢复依据，已被实际结果否定；原JSON保留不改，后续报告须注明未实现。

根因待验证。绝对负缩进数值数学等价，不等于DOC导出器实际保留；本轮不再假定该路径有效。

## 约束

- 仅编计划；本规划器未编辑输出、未渲染、未测试。
- 原计划及supplement冻结；本轮明确取消“绝对负缩进等价值必可通过DOC导出保留”的假设。
- 先诊断再实施；R1与R2择一按真实前提执行，非同时穷举；没有证据的表达不试。
- 保留实际几何、字体、正文；不能以改变字号/默认样式/缩进倍数伪造原位置。
- 正常权限不足走审批，拒绝不绕过；不安装或修改依赖库。

## 顺序与门

### D1

冻结本表输入与失败回执。只读按第13页日期正文及上下文定位源/恢复FODT和DOC再读FODT中的实际paragraph style、父样式、span/字符样式及引用范围；不假定后者仍名P33或P36。提取margin-left/text-indent、字高Western/Asian/Complex、直接格式及继承默认值。

门：保留完整原节点与解析后的有效属性证据，解释绝对负缩进是否在源中存在、加载后接受或DOC写出后丢失。

### D2

以同一LO和字体环境，对恢复FODT直接导出PDF（源只读、产物新路径），与已保存DOC→PDF和原PDF的日期逐字符坐标/字体/字号比较；如直接PDF也不对，限于定位FODT读取/布局；如直接PDF正确而DOC不对，限于DOC写出/重读。必要时仅做一次FODT加载另存FODT读出以区分读取归一化与DOC出口。

门：先完成此因果分流，再选择恢复；不得继续假设fo负缩进有效。保存argv/退出码与原件/产物SHA。

### R1

前提：直接证据表明字符缩进-1.71ic被保留但段落基准16pt在DOC出口丢失或错误按10.5pt解析。

仅在新副本恢复原-1.71ic，并按已读出的原始字体属性，让该日期段的段落标记/原段落基准保留原16pt及原Western/Asian/Complex值。允许用当前安装工具所支持的等价原生表达显式保留原属性；不改变显示字符、正文、真实字号或其他段落。先证明候选表达对应段落基准而非仅span字号。

门：仅一次有证据支撑的候选。不得改默认Standard样式以影响全稿，不得改-1.71为补偿倍数，不得改边距/字符间距/制表符/空白压位置。若工具无法承载原基准则停止此分支。

### R2

前提：R1的原属性保持无法由现有导出器表达，且现有本地工具可精确保留原DOC日期段二进制属性及其引用。

可采用原DOC未编辑日期段的原生/二进制属性保留路径，但先只读证明段落、样式、字符位置与引用表边界，不安装库、不全局字节搜索替换、不对复合文件或长度/索引指针猜偏移。仅保留原属性；27段批准内容修改仍须完整。

门：未建立精确格式结构与只影响目标范围的证据不得执行。不存在现成能力则记录不可用，不能盲目修复。

### V

若形成候选，则原.doc独立渲染一次，核对14页、151段批准目标文字、3媒体SHA，日期所有字符与原PDF的文本/字体/字号一致，逐字符坐标容差≤0.1pt；1/2/14等未改区域及表格/页边距/原图无新退化。

门：不只对齐日期首字。任何新根因/新失败保留证据并下一轮Astra；禁止循环试值。

### S

记录诊断分流、实际恢复方式及限定验证结果。失败候选与此前计划/证据不覆盖；仅完全保真通过的DOC替换交付稿。独立PPT工作可继续。

门：不修改源码/环境，不运行项目测试，不提升项目研发/正式研究状态。

## 验收

- 原.doc14页、完整批准正文、3媒体原样。
- 日期全串字体字号与逐字符坐标回原值（≤0.1pt），不是仅首字。
- 其他原样式/表格/页边距及未改区域不退化，所有失败证据保留。
- 没有验证通过时不交付为保真完成，不编造环境或研发验收结果。

## 冻结输入

| 路径 | SHA256 |
|---|---|
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/word-fidelity-followup/plan.json` | `7f609dee27619b2765b96921d97ec9b61630a00a33c548304249331d84d6acba` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/word-fidelity-followup/supplement.json` | `02620eebd1eeee7fbbb20b5df257fecc9919d3c263b8bf28bc30b93a7a3ae823` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-indent-restoration.json` | `071854fe347ac0a24f1c71b5c29ef5cf645c2dd57430e719de78ac881270a2de` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/final-native-layout-proof.json` | `3e702563cb6b80bd9481eda0eb59922917e3b1a5498e4ab49902468d952476e6` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native/开题报告-2501220176 宁业栋.fodt` | `3f2d53a8b25fdc879eebcb31abbf6daf1b9e4ed5b8c6836ef147fe282262ce0c` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native/开题报告-2501220176 宁业栋_修改版.fodt` | `00126149bb24612d5a86ec8fcad979cb90debf93d9a20cf5c5fb21a70b26c452` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored/开题报告-2501220176 宁业栋_修改版.fodt` | `b6a3f160c83b98da7b73bd62bd3b9a080f7a0bd65ebbb25f298e36faca7b2f25` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-doc/开题报告-2501220176 宁业栋_修改版.doc` | `50bc6975e9879bc7d4c111d68a6af5611e0662be4fc647539b852a4987121f33` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-roundtrip/开题报告-2501220176 宁业栋_修改版.fodt` | `0785527793765182c8d7067831a732e490c1b062a3c0a43bb0e583db177f9e6f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/native-restored-render/开题报告-2501220176 宁业栋_修改版.pdf` | `3838c37f57606345a59756ebb4cabdf5c5ce7e3eb826cb56bf7916f6450403ab` |
| `/home/ningyd/.codex/attachments/2cd06be5-6427-4f5f-8086-e5421684b420/开题报告-2501220176 宁业栋.doc` | `2ba25b90eaacc5829812f26d76fd814ce0732383794ec07f8fa594dcc5860cd3` |
| `/tmp/bigsmall-proposal-review-20261021/开题报告-2501220176 宁业栋.pdf` | `d26c906616a908eaa2516e9d26ed6050aa6401869251d20acd9c6d83d26bc280` |
