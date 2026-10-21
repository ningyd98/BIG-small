# Word分页与格式保真限定续计划

实际规划模型：gpt-6-astra；仅计划，未编辑、渲染或测试。

## 原始失败与假设

{
  "raw_receipts": [
    "ba649d",
    "467ab4"
  ],
  "source": "父任务提供的原始比较摘要；完整回执由父任务冻结落盘，不能以本摘要代替。",
  "original_doc_pages": 14,
  "candidate_docx_pages": 15,
  "final_doc_pages": 15,
  "observations": [
    "candidate仅27段文字修改，净减少109字符；candidate全部非文字属性与原中间DOCX一致。",
    "candidate与finalDOC重导DOCX均153段，差异为39段末空格被格式转换去掉，不是新增内容差异。",
    "pgSz、pgMar、tblPr、trPr一致；三项媒体SHA一致；32项tcPr序列化差异待区分纯序列化/实际语义。",
    "2027年5月进度单独溢出第13页，评审由原13–14页推至14–15页。",
    "尚未渲染未改原中间DOCX，初始转换与文字分布两个假设尚不能区分。"
  ],
  "conclusion": "已出现新分页退化；不得以总字符减少或XML非文字一致宣称原DOC格式已保真。"
}

根因尚未确定：先区分初始转换与文字分布；净减少109字符不能保证页数减少。

## 限定范围

- 继承原计划全部范围，仍仅Word内容修订及恢复原版式；不得增加新研究内容或修改PPT。
- 不改变字体字号、行距/段距、表格尺寸/边距/布局、图像、页边距或分页属性以强行压到14页；仅允许恢复有原DOC证据的精确转换漂移原值。
- 最多先完成一个未改baseline和一个原生无编辑另存对照；文字压缩按证据定向，出现新根因立即重规划，避免无界试错。
- 正常工具权限不足走require_escalated；拒绝后不改路径或用替代API绕过拒绝。
- 本子任务只保存计划，未编辑输出材料、未渲染或运行测试。

## 顺序与门槛

### W1

核对输入hash，冻结现有15页候选、最终DOC及PDF/页面/差异证据到本轮before目录；后续试改另起副本，不覆盖上传原件或失败候选。

验收门：原始回执ba649d/467ab4保留；记录真实渲染器、版本、字体环境、argv和输出SHA。

### W2

以与candidate/原DOC一致的渲染器和字体环境，只读渲染未改原中间DOCX，得到baseline；按页面/段落定位比原DOC14页、baseline和candidate15页的文字行数、换行/分页、字体映射、表格边界。必要时重新渲染原DOC仅作为同环境对照，保留原渲染。

验收门：先判定baseline是否已有15页，不能把candidate/roundtrip仅末空格的差异归因于最终导回DOC。

### W3

只读规范化比较32项tcPr：按命名空间URI和局部名、属性名值、子节点顺序及有效默认值比较，识别前缀/属性顺序等序列化差异与实际宽度、边距、合并、垂直对齐等语义改变；同时核对rPr/pPr/styles与字体替代。

验收门：差异未解释不直接判格式一致；禁止凭序列化字符串不同盲目修32处属性。

### W4A

条件：baseline与原DOC同14页，且局部差异证据支持文字分布造成候选增加行/页。

只在原已修改段落内压缩冗余，优先导致新增行的长段及研究进度段；全部主要事实/专业身份/统计口径/阶段边界保留，保留run格式和原非文字结构。不得通过删减必要内容、变字号/行距/段距/表格/页边距或新增分页控制压页。

验收门：每批文本替换有原/新映射与语义清单，重新渲染回14页且无新截断/重叠；进度最后一项与原进度区域同页，评审回原13–14页。

### W4B

条件：baseline已15页，或已识别初始DOC→DOCX引入的格式语义/字体映射漂移。

优先使用原DOC副本经原生办公文档接口（如bundled LibreOffice UNO）在原文本范围内替换同一批准内容并保存原.doc；先做未编辑原DOC的加载/另存对照，证实该路径本身保持14页和原布局。核对接口和字体可用性，禁止安装/修改环境库。

验收门：原生路径未编辑对照不保真时，不反复猜测参数；若已直接证明唯一转换漂移，可仅恢复原DOC实际存在且有读取证据的原值，列出精确属性和值/来源，保持原布局参数。未知值或范围扩大须下一轮Astra。

### W4C

条件：baseline和candidate差异表明转换漂移与文字分布共同造成，或目前仍无法区分。

先在副本恢复经证据确认的原转换语义，再依W4A压缩原段文字；若缺少精确证据则停留诊断，不允许以试调字号/表格/页边距凑页数。

验收门：新的根因、权限失败、原生工具不支持或超出精确恢复范围时暂停受影响编辑并交Astra。

### W5

对最终原.doc重新独立渲染并逐页核对，重复内容及格式只读比较；验证14页、三项媒体不变、原字体字号/段落/表格/页边距及原图保持，完整主要事实未丢失。必要的docx诊断副本只作为读出，不作为原.doc交付替代。

验收门：页数相同只是必要条件；所有新增分页/布局退化消除才接受。原本已有分页缺陷不强修。

### W6

保存step-report.md/json：两假设证据、tcPr分类、采用路径、精确文字/属性恢复、最终hash和逐页核对，保留15页失败原件。未通过时不交付退化Word；独立PPT工作可继续。

验收门：不运行项目测试、模型或机器人，不修改产品源码，不提升研发或正式研究验收状态。

## 最终验收

- 最终交付原.doc，14页且逐页视觉无新退化；2027年5月不独立占新页，评审恢复原13–14页。
- 所有主要事实、完整指标及已有/拟研究边界保留；不牺牲内容凑页数。
- 字体、段落、表格、页边距及原图保真有证据，32项tcPr差异有语义结论；单凭页数/总字符数/序列化一致不判通过。
- 失败原件与原始回执保留，开发验证/真实运行/正式研究状态不提升。

## 冻结输入

| 路径 | 字节 | SHA256 |
|---|---:|---|
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/plan.md` | 15633 | `5c99548793c9ac96b4422c21b8b2761746b39795165d14ef45697d3f272cafd7` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/plan.json` | 19521 | `387f6f808c57a9c267a501df837a752295b5c4783808f648aed9fecfeac422a5` |
| `/home/ningyd/.codex/attachments/2cd06be5-6427-4f5f-8086-e5421684b420/开题报告-2501220176 宁业栋.doc` | 1136640 | `2ba25b90eaacc5829812f26d76fd814ce0732383794ec07f8fa594dcc5860cd3` |
| `/tmp/bigsmall-proposal-review-20261021/开题报告-2501220176 宁业栋.docx` | 1086606 | `a4b490978e414442e524aa8665f6870cae594e7d319365f39ed68deaffec0fde` |
| `/tmp/bigsmall-proposal-review-20261021/开题报告-2501220176 宁业栋.pdf` | 1062427 | `d26c906616a908eaa2516e9d26ed6050aa6401869251d20acd9c6d83d26bc280` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/开题报告-2501220176 宁业栋_修改版.docx` | 1086524 | `e00dae31d1372d006e199cef9583017138e1700f165686d239cacb3c4bcd7887` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/roundtrip/开题报告-2501220176 宁业栋_修改版.docx` | 1086921 | `2cd1b53db463a18a4516314c55d4b67ffd182a0ae6f7996e4737471e93ded2f2` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/docx-change-map.json` | 30582 | `6c578c7b6fdc9da8866570120a56bbb56fc1a4236c59ea7a13c7738eaf6b3122` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/final-doc-text.txt` | 28596 | `88d44bee7a53c6160d04544447e0dc305906b7eda5ed40b35e056c268c35962f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/docx-render/开题报告-2501220176 宁业栋_修改版.pdf` | 995925 | `636d84d689ff0da39ea6bef05c1e7c6cc41051dfb2cb0fb504405056eefe2137` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/doc-final-render/开题报告-2501220176 宁业栋_修改版.pdf` | 995942 | `4cf2f416be6a9914450984c34ea7f13f5aad29cb29f62a1b9574e09c28059657` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/开题报告-2501220176 宁业栋_修改版.doc` | 1125888 | `5221c4ac866f7f89b42175410e9a6773fc290ece6bc75a63f70b64ad53d752ee` |
| `/tmp/bigsmall-proposal-edit-20261021/edit_document.py` | 3695 | `e3299526b38d72fcab1558cf83f7b00e8b96100ee5772afdf02b4b01d5d35e84` |
| `/tmp/bigsmall-proposal-edit-20261021/revisions.json` | 14864 | `ad7793e921c1a1a5fbe131a878a738245e9d1519d5ade6ab5d2cd7a2f5d3fabb` |

原轮次全部其他原件及协议输入继续适用，执行前核对。
