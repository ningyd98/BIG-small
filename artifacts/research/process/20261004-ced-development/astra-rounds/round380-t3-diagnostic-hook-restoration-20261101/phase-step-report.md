# R380 诊断作用域恢复

实际 Astra 计划76项输入已核对。行为保持提取后，短 RED 为正常/异常退出2项 identity 失败、委托1项通过；唯一修复将 fault owner 交接给内部 scoped，D/F 按同栈 LIFO 撤销。短 GREEN3通过，原输入合同3通过。

原 confirm_timeout 单次执行通过（pytest246.19秒/外层247.127秒），真实请求出队→主线程超时→迟到broker→拒绝链完成，public accepted=false 与原完整文件/SQL断言完成；675资源、无清理错误。长 test 同进程 method identity 检查与短重复正常/异常恢复均通过。全部阶段前置accepted、源不漂移、无超时或残留。独立审查另附，不把旧observer字段单独当invalidate恢复证明。

仅CPU软件instrumentation修复；commit_close单独转R381，旧R376失败原件/过期预算不改。旧runner重复取消静态风险延期，未做信号压力验证。本地完整raw/DB不属于远端精选复现包。详见plan.json、terminal-handoff.json与review/code-review.md。
