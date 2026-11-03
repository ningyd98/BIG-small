# R400 — AST 保留检查的比较方向

实际模型 gpt-6-astra。本轮只纠正一条 inline 静态检查，不修改产品、测试或 R399 计划。原报告为 `AssertionError: initialize_retry_budget_if_absent`；完整原检查器没有文件，original-finding.json 如实保存会话报告和原表达式，不冒称冻结原完整脚本。

检查器应将 **修后 NEW AST** 的七个明确 `self._…_unlocked` 调用映射回原公共名字，再与 OLD AST 比较。原式却标准化 OLD、直接比较 NEW，因此命名差异必然失败。`_unlocked` 长度9，`[1:-9]` 的结果正确；采用明示映射更窄。

允许写短 R400/static-check.py：六 reader 的新 helper 先确认新增首行是 docstring，再比较其 body[1:] 与原 reader body；公共 wrapper 的签名、装饰器和唯一匹配委托须正确。内部 list helper 也单独比较，外部列表保持；其它方法对 NEW AST 限定标准化后精确比较，锁/guard/事务/SQL/参数及未涉及模块结构不能被忽略。禁止扩大归一化来掩盖差异。

一次纯静态运行≤30秒，通过后才写 R399/preflight/product-comparison.json，并保存 R400/static-result.json；失败保留真实错误，不改源。无需另开行为/helper审查循环，最终 R399 独审覆盖此小结果。

运行中的独立回归可继续。R399 原1800秒时钟持续、不重置；行为、Git及网络配额均不增加。精选交付仅窄增本轮 plan.md/json、input-audit、original-finding、static-check.py、static-result.json、step-report、review-resolution 八小记录及该 product-comparison.json。
