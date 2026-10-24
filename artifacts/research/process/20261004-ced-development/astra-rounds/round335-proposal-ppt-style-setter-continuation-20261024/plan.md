# R335：text.style 赋值接口限定接续

实际模型：**gpt-6-astra**。仅规划。

940717 exit1 在 patch-v2.mjs 第18行把只支持赋值的 text.style 当可读对象，导致 undefined.typeface TypeError。失败发生于保存前；Astra已确认 v2 输出不存在。完整dispatch/completion及输入SHA见 plan.json，旧失败不改。

仅将原脚本复制为同目录 patch-v2-fixed.mjs，并精确替换唯一一行：

```js
p.resolve(target.anchor).text.style = { typeface: '微软雅黑' };
```

其余字节不变，按 plan.json 命令运行一次。保持原v2输出路径及R334表格边距、完整QA、原字体政策和剩余一次finalizer许可。文档支持 grouped style assignment；实际仍须比对封面文字、字号、颜色、粗细、位置、断行与其他样式，不能仅凭无异常就宣称其余样式保留。

成功后继续R334既有流程；新失败/非预期样式变化需新限定计划，不盲重试。不新增研究/产品测试或finalizer额度，不修改旧脚本/验证器/PPT/冻结计划，不执行Git。
