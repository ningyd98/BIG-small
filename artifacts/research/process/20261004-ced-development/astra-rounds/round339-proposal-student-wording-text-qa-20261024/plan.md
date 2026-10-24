# R339：学生口吻PPT递归文字核对续接

实际模型：**gpt-6-astra**。仅只读复核与QA计划；本次以用户最新12页稿为准。

## 原始失败与已查明原因

原 delivery-qa.json 保留 needs_review / all_expected_texts_present=false，不覆盖。直接路径 `p:cSld/p:spTree/p:sp/p:txBody` 漏掉源第2页 group 中6条非空目录文字及23个空文字框；导出扁平化后它们才被旧选择器读取。

Astra独立只读递归核对（ef8bc1 exit0）确认：源/目标均12页；应用冻结 edits.json 后，全部页面文字精确多重集一致，空文字框数也逐页一致；所有表格行列及单元格内容符合编辑清单，逐页图片关系目标字节SHA多重集一致；没有遗漏于原生文字框/表格之外的 a:t。**未发现真实内容差异。**完整观察见 readonly-observation.json，输入精确SHA见 plan.json。

## 唯一允许修正

ROOT仅修正QA提取覆盖：文字使用 `.//p:sp/p:txBody` 或等价递归group遍历；表格递归 `.//a:tbl`，保持行列顺序。按presentation关系取页序；保留段落/换行/Unicode/重复次数，原old文本必须每处恰好命中一次。不得只做子串包含、丢掉空串掩盖差异、忽略未知文字载体或放宽表格/图片检查。

允许一次修正后的元数据比较，另存 delivery-qa-recursive.json 并链接首次失败与诊断SHA；原报告、清单、PPT、验证器及正式finalizer证据不改。保持原图像、12页、成品对已审候选、未改页渲染和身份/内容验收条件。原12页视觉审阅与finalizer仅对同一成品SHA复用，无需新导出/渲染/最终化。

## 验收与停止点

完整递归比较通过且输入/成品SHA不变，才允许ROOT据新报告关闭本次QA异常。若发现真实增删、表格/图片差异、selector歧义或未覆盖文字载体，保留证据并交回，不修改成品、不标通过。本只读检查不新增原生PowerPoint/本机字体或研究、物理实验验收结论。不执行Git，不新增产品测试/运行额度。
