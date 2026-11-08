# R483 Astra最小计划：静态helper显式导入ast

实际规划者：`gpt-6-astra`；仅规划，不实施。

**问题与根因：** 外层一次性静态helper漏import ast，在ast.walk(ast.parse(s))处NameError；context记录helper仅导入Path/json/hashlib/py_compile。v2已包含ast import且py_compile先前成功，尚无离线评分/模型调用。根因是外层验证工具导入遗漏，不是v2或产品缺陷。

**范围和执行：** 只新增独立只读verifier（可一次性命令，源码及命令入证据），显式import ast及所用模块；不修改v2、产品、R482计划、模型、提示词、raw或输入。先复核本轮固定输入和R482 input_sha256全部path/bytes/SHA及重复路径；读取当前v2并与before副本hash一致，使用compile(source,filename,"exec")做不执行/无pycache的语法校验，ast.parse并检查实际调用及import。确认不存在网络/模型生成/模型加载/硬件路径，允许R482规定的严格解析与_ground_response调用；AST属性名扫描仅为有限辅助，结合实际源码审查，不冒称完备安全证明。

**验证和验收：** 另存verifier源码/argv、stdout/stderr/rc、逐项hash检查与AST/源码审查摘要；验证成功且v2 SHA不变后继续R482原授权一次离线评分，唯一新输出，所有质量负结果如实保存。静态检查通过不等于评分通过或模型质量通过。不得为了检查通过删调用、改输入hash或重写v2。

**前置与边界：** 仅本地读和R483证据写；限3分钟并计入原预算，不联网、不加载权重、不推理、不硬件。若发现不同根因/漂移/真实禁用调用，保存异常并暂停相关工作，另交Astra；保留原NameError与全部历史日志。

**输入SHA：**同目录plan.json固定AGENTS、R482计划、当前v2及本轮原始失败/context/before副本的path/bytes/SHA256；执行前逐项复核。
