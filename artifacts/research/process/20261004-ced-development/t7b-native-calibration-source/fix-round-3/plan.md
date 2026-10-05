# Task2 UTC原件读取边界修复

保持原REQUEST_FIX、53/175测试报告、原两条真实reader反例及旧baseline冻结。根因是先读取sample字段/转换datetime、后校验schema，异常类型越过_group的ValueError拒绝路径，导致原分配组没有诊断。

先原probe与8个关联恶格式单测qualified RED，再在independent_utc_uncertainty_ns明确检查外层dict、independent source hash dict、samples list、完整sample键和SHA/string UTC类型；无效原件统一ValueError。保留原_group拒绝和完整分母，不扩大except吞业务异常，不修剪UNKNOWN或改变clock/source权限。原件有效控制与缺整sample控制保持；v1缺reset仍拒绝，Source/完整horizon/policy/组件及未来权限不放宽。

随后定向Task2与原real-reader probe GREEN/Ruff/mypy，写新report与精确pin，交原独审者复核。真实UTC/root distance预检只作telemetry，未获native正分支。不运行模型/physical/renderer/decoder或修改消费者/Task1/Stage/Git。
