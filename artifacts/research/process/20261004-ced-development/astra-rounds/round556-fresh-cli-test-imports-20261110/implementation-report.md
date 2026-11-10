# R556 导入顺序修正

实际 gpt-6-astra 计划限定于 same_session_fixture 的已有导入排序；4 项输入字节与 SHA256 全部复核。原测试保存为 original-test.py.gz，原 Ruff 日志和 diff 保持不变。实际文本差异与原 Ruff diff 完全相同；导入完整 AST 节点多重集合一致，仅对该函数开头连续导入排序后，整个模块 AST 相同。

验证：26 项 CLI 测试通过；7 个相关 Python 文件 Ruff 通过；git diff --check 通过。精确源码 SHA 见 edit-verification.json。没有生产逻辑、阈值、运行时或预算变更；真实模型/生成/云端调用均为 0。继续执行 R554。
