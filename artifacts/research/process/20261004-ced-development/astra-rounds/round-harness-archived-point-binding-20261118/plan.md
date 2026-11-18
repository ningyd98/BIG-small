# Molmo 原始提示绑定的窄修复方案

GPT-6.2 Astra 制定，GPT-6.2 Sol 实施。候选源码以输入清单中的实际工作树字节为准。此前 129 项焦点测试已通过，首次四例 CLI 仍在 44102 的 _model_point 抛出 archive model point/raw prompt is not bound to the paired observation。首次归档命令、原始栈和 lint 输出全部保留。

生产 MolmoPointProvider.point 将 native_prompt(phrase) 放入带单张图的 user message，调用 processor.apply_chat_template(tokenize=False, add_generation_prompt=True)，prompt.txt 保存完整渲染字符串。七例的前两条请求（14 份）均有同一封套，包含尾随换行。故障代码将这些字节与裸 native_prompt 比较。这里的输入与输出表示差异足以解释首次拒绝，离线分析未发现允许兼容裸文本的历史原件。原索引、观察、RGB、请求及回答摘要、模型点结构、坐标及 reached_cap 门都仍适用。

1. 实施前重算 plan.json 中所有 inputs；保护来源原件及既有失败。限 scripts/diagnose_native_harness_stops.py、tests/test_native_harness_stop_diagnostics.py 和首次 ruff 输出列明位置的机械格式修正。不得更改采集方、控制链、已冻结输入或视觉算法。
2. 先构造本数据版本的两个原始目标/目的地封套作为正例，调用 _model_point 及生产点解析；原实现两例均应在绑定处 RED。负例必须覆盖裸文本、多余图像或角色、缺尾随换行、互换 phrase 与响应、错图/校验、坐标不符与 reached_cap=true。损坏语义测试需在小型自建清单中合法重新索引测试字节，使其真的抵达语义判据；另测未更新哈希的直接篡改应由 FrozenCase 拒绝。
3. 对此已绑定、已核验来源的历史模型，严格比对 UTF-8 字节 **<|image|><|im_start|>user LF + native_prompt(phrase) + <|im_end|> LF <|im_start|>assistant LF**，其中 LF 为单字节 0x0a。保留所有现有校验，禁止 strip、contains、任意模板替换或删除原 prompt 检查。若发现其他真实编码，应保留具体原件交新轮评估。必要时把提示封套错误单列为明确异常。记录历史模型输入的实际 prompt_sha256。无需加载模型、tokenizer 或接入网络。
4. 用焦点测试及父轮原命令在新输出目录运行四例实际归档。确认 44102 两个 POINT 绑定通过、44104 两个 POINT 均通过绑定后进入原确定性几何拒绝、44101 逐视角及 44103 原横退判断与物理标记不变。焦点 129 项原覆盖、增加的正反例及原 ruff 命令均绿，记录新退出码、所有原件前后哈希、阶段报告；保留原失败回执。
5. 仅为离线诊断接线修正，0 云、0 生成、0 真机；独立于之后四次新预登记。独立回归、安装包和资格审计继续按父轮。意外失败留证并由实际 Astra 拟定下一轮。
