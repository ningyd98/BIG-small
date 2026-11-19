# worker 基类异常字段的静态类型兼容

初次 mypy --follow-imports=silent 在组件 101/107 行新增三个错误。typeshed 将 BaseException.args 和 __traceback__ 静态描述为字段的值，不能据此直接查 __get__。CPython 运行时两者实为基类 getset_descriptor。另有一条旧 no-any-return，新 505 行对应旧 422 行。普通导入初始报告 806 项、31 文件，其逐条基点差异与新增三项分别记录。

限于 _record_component_exception 的两个基类字段读取。以固定字面键从 vars(BaseException) 获取解释器自带描述符，再调用 __get__(error, BaseException)，给返回结果标明 tuple[object, ...] 与 TracebackType | None；允许等价且清楚的静态类型写法。不得读取子类覆盖的属性、调用任意异常的 __str__/repr，或以类型忽略屏蔽。保留现有白名单、固定消息匿名化、原 traceback、阶段、二次异常和安全停止/外层传播。若现有测试只覆盖 __str__，增加一个小负控，用覆写 args/__traceback__ 的子类证明读取不触发这些 getter。

核对源、测试、配置、基点源码、原工具版本与两种 mypy 原件；先验原失败，再改两个读取点。运行原命令和常规导入 mypy，与同参 --shadow-file 基点分别对比：不出现三个新增诊断，原有全库问题和 silent no-any-return 如实列出。复验既有 EGL 组件安全与真实单场景 worker 定向集、脱敏/自定义异常/正常完成/二次错误和停止关闭；核对 Ruff、diff、主要回执和历史 1803 原件 SHA。此轮无外部模型或真实槽位运行。
