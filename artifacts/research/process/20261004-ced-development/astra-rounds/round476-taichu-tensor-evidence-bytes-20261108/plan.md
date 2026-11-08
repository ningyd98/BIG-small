# R476 Astra 补充计划：BF16张量证据字节读取

实际规划者：`gpt-6-astra`；保持R473与R475其他范围不变。

**原始失败：** 官方processor已返回features；证据助手对BF16 pixel_values执行detach().cpu().numpy().tobytes()报TypeError: Got unsupported ScalarType BFloat16。原始stderr定位process_pair.py第32行；外层PROCESSOR_REJECTS_TWO_IMAGES是错误归类，不能据此判断processor拒绝两图。

**根因：** NumPy转换不支持此BF16张量dtype；异常发生在证据字节编码阶段，未证明processor或模型不兼容。

**范围：** 仅改R473 artifact implementation/process_pair.py的张量字节提取及异常归类/新结果路径，R476保存验证与解释。保留diagnostic/process_pair.before.py、原a结果及所有失败字节；不改产品代码、processor实现、模型输入、量化/运行版本。R475依赖工作独立继续。

**修复：** 实施前复核本计划输入SHA。显式import torch；hash用value.detach().contiguous().reshape(-1).view(torch.uint8).cpu().numpy().tobytes()，先记录原始dtype和shape，并记录字节序/字节数。这是张量逻辑连续顺序的原始dtype字节视图，不声称包含非连续storage空隙；禁止float()/float32转换来绕过错误，禁止修改原features。分离processor调用与证据序列化异常：真正processor调用抛错记PROCESSOR_CALL_FAILED，返回成功后证据编码异常记EVIDENCE_ENCODING_FAILED并保留processor_returned=true；不得统一标拒绝双图。输出新processor-a-v2.*及独立状态解释，旧processor-a.*不覆盖。后续B测试可复用此helper。

**验证：** 在实际选定环境用BF16、INT64、FP32真实张量运行字节读取，断言len(bytes)==numel*element_size且原dtype/shape/value未变；包括非连续张量连续化、标量和空张量，记录hash与原始结果。该检查仅为证据helper单次验证，不新增产品测试。随后对同一固定RGB/depth二图重新调用真实processor，保存a-v2张量dtype/shape/bytes/hash及两图来源hash；不加载模型权重、不产生假推理。核对旧a日志/JSON和before.py SHA未变。

**边界：** 限时10分钟、只用已有processor/图片和现有隔离环境、无需联网/权重加载/GPU推理。通过只表示张量证据编码修复且processor两图路径实测；不表示模型加载或输出质量通过。新异常保存原始traceback和阶段，若不同根因则另交Astra，不修改实际输入迁就验证。修复后继续R473原阶段/预算，正式验收仍NOT_PERFORMED。

**固定输入SHA：**完整path/bytes/SHA256见plan.json的input_sha256，含AGENTS、R473计划、待修artifact及本轮全部原始诊断。实施前逐项复核，不修改预期hash。
