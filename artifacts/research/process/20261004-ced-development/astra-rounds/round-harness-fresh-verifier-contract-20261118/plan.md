# 四槽审计器缺失索引负例的断言修正

GPT-6.2 Astra 制定、GPT-6.2 Sol 实施。四槽审计器首次实现后的 19 项检查中 18 通过，test_missing_or_replaced_frame_cannot_pass_the_index 在删除 frame/depth.f32 索引后已抛出 ValueError('FROZEN_FILE_NOT_BOUND')，小写正则 index|bound 未命中，第二个篡改分支尚未执行。现行生产 FrozenCase.read 明确区分缺少绑定 FROZEN_FILE_NOT_BOUND 与内容变更 FROZEN_FILE_HASH_MISMATCH:<相对路径>。本轮只纠正测试契约，并修复 1 条 I001 和 15 条 E501。原预期的缺模块 RED 属父轮开发记录。

1. 按 plan.json 核验两个研究脚本/旧测试输出/生产类的 SHA；保存首次18/1原件，使用相同真实 FrozenCase，切勿只测试模拟异常。
2. 在四槽目录 test_verify_fresh.py 保留先对完整帧逐值相等的正例。删除深度索引的负例应精确断言 str(exc.value) == "FROZEN_FILE_NOT_BOUND"，随后替换 RGB 字节同样精确断言 "FROZEN_FILE_HASH_MISMATCH:frame/rgb.png"。可采用锚定且对路径作字面匹配的正则。完整、缺索引和字节篡改三段均须实际执行。FrozenCase 和审计器决策不得更改。
3. 限上述测试及 verify_fresh.py 实施机械 import 排序和折行，不更改校验条件/异常/预算。运行 python -m pytest -q <四槽目录>/test_verify_fresh.py 和 ruff check --no-cache <四槽目录>/test_verify_fresh.py <四槽目录>/verify_fresh.py；验收预期 19 项通过、lint 0 项，原资产与预登记/旧结果字节不变。保留命令、退出码、前后 SHA 和简短步骤报告。这轮仅核实软件故障负例，0 模型、0 云、0 真机，四槽付费运行继续服从独立冻结前置。
