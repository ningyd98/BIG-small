# 2026-11-18 四槽原件索引负例

GPT-6.2 Astra 制定方案，GPT-6.2 Sol 实施。实施前复算机器可读计划登记的 7 项输入，大小和 SHA256 全匹配。初次实现的 19 项检查中 18 项通过，缺失深度索引引发了生产错误码 `FROZEN_FILE_NOT_BOUND`，新测试的原小写正则没有匹配。原日志与来源保持可读。 [方案](plan.md) · [实施前指纹](inputs-before.json) · [首次测试](../round-harness-four-fresh-positions-20261118/verifier-first-green.log)

测试现在先重建一份完全匹配的 RGB-D，再分别断言缺索引的精确错误码以及替换 RGB 的 `FROZEN_FILE_HASH_MISMATCH:frame/rgb.png`。仍调用同一生产 FrozenCase。审计器只改机械折行，原 Ruff 报告和首次折行后剩余的两条行宽报告保留。 [原 Ruff 证据](../round-harness-four-fresh-positions-20261118/verifier-ruff-first.log) · [折行过程](ruff-green.log)

最终 19 项通过，Ruff 检查通过。审计器 SHA256 为 `e1d672a5e65a9250c7f383b64ae368a65215bc625b5b2df67153e90047965fb3`，测试为 `fdc9e1c0cbef2cd7120490e09fc94bcf0d0bdb1dc9bfb5f5aeba905c971b0c0e`。追加的批次启动器互斥、未知占用和历史重复负控与这 19 项合计 24 项通过。测试未使用 GPU、模型或云请求。 [单轮最终日志](verifier-final.log) · [单轮 JUnit](verifier-green.xml) · [最终 Ruff](ruff-final.log) · [24 项综合日志](../round-harness-four-fresh-positions-20261118/offline-controls.log)
