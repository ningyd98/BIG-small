# R458 测试替身补修报告

原 R457 结果 7 PASS / 1 FAIL 保留；原因是禁止渲染的函数替身无法作为 pilot 捕获类的基类。依 Astra 计划改为可继承且一经构造立即失败的 ForbiddenCapture，并保护 pilot 模块缓存中的捕获入口。

一次修复后 8 项迁移契约和 130 项相邻测试通过，ruff/format/mypy 均通过。R458 复核的六个产品源码 SHA 全部保持不变，具体记录见 step-report.json。没有真实模型、物理、渲染、服务或硬件调用，正式研究 NOT_ACCEPTED。

完整迁移结论汇入 R457 implementation/step-report.md；本轮未覆盖、清理或改写首次失败日志。
