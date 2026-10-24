# R343：文档入口更正并接续R342

实际模型：**gpt-6-astra**。仅只读核对及计划。

78a191 exit2源于误查不存在的api/shapes.md、api/rich-text.md；完整原失败保持不变。实际文档为原技能的api/references/shapes.spec.md与rich-text.spec.md。当前报告、PPT、R342计划、编辑清单/脚本、失败和两文档的SHA256均已冻结在plan.json，所提供三项关键SHA全部匹配。

已读实际文档及当前脚本：`slide.shapes.add({geometry:'textbox',position,fill,line})`、`shape.text.style={...add.style}`、`insets:0`、`verticalAlignment:'middle'`均有文档依据。**当前两新增文本框无需API修正。**允许ROOT使用正确文档路径，按原R342前置继续authoring marker与已准备脚本；这不是实际导出/版式通过证明。

若仅发现两新增文本框的明确API语法差异，可保全before后做有文档依据的等价API修正并记录diff/SHA；文字、样式数值、位置与编辑清单不得改变。当前没有此类修正必要。新根因或范围扩大另起计划。

R342的12页、原图表/字体/学生口吻、指标限定、一次完整最终化和递归QA边界全保持，不新增执行/视觉检查额度。不改原PPT、代码、冻结计划或失败证据；Astra不执行authoring、产品测试或Git。
