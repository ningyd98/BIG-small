# R306 执行前限定补充

实际模型：gpt-6-astra。原plan不改；本补充是执行前静态审阅授权，不是新增实际失败。

1. 新micro key已固定为 `observer_serialization`。新runner副本将唯一资源目录判断 `if key not in ("observer_red", "observer_green"):` 改为 `if key == "dual_behavior":`；原 `unit_only=key.startswith("observer_")` 已正确，保留R304缺目录记录。原两key、命令和额度不变。
2. 单session原实测 charged=31988字节、两被动文件合计39096字节；五场景容量有超原限风险，但不预断一定同量。仅新R306插件预先固定为总524288字节（512KiB），payload393216、metadata131072，仍两文件。保留6sessions/64events/12frames、所有事件/内容、计费及实际字节验证和0drop验收。只调整新副本对应常量及真实标签，旧插件不变。

原数字token计数：{'98304': 3, '32768': 1, '131072': 5}。映射须按原token坐标一次替换，禁止串联替换使新131072再次变524288。新diff须如实称身份+容量映射，ROOT source/native/argv审阅纳入本补充。超新限仍失败，不自动扩容。

此处只增大证据文件容量，不改安全/运行时限或测试预算，无额外运行。原一行产品修复、实际失败基线及两个原wait身份接续均保持。
