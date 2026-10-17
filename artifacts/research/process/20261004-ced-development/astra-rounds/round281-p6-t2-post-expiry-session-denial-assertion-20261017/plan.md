# R281 后置会话拒绝断言计划

实际模型 gpt-6-astra；本轮只规划 test-only 修正，不运行验证。

唯一 R276.wait_memory 真实 child/wrapper1，181.929秒，无timeout；JUnit1FAIL0ERROR0SKIP。完整47407字符trace已分三段读完：D_lease第二次 reserve_capture 经 runtime/job真实链至 _check_ingress471，抛 OperationalLeaseError('session is closed, revoked or unregistered')，test4339的旧通用期限regex不匹配。

D_app已有完整scenario文件。D_lease到第二次检查前，首次拒绝、holder finally/errors、真实锁→原counter跨越→释放顺序、returned、保留原预算/revision/pending及无COMPLETE断言已通过。源码 _live685–689在原期限过期后invalidate，后续ingress拒绝符合failclosed设计。但首次被pytest吞掉的异常和首次invalidate原因未保留，不能声称已直接观测首因或特定compound predicate。

仅允许同一Sol改该wait test的nested exercise：首raises原类型/regex/操作不变，仅绑定异常；D_lease已有advance记录须唯一并满足before<原session.ttl_ns<=after；仅D_lease后置检查改为精确OperationalLeaseError及锚定完整消息，D_app原断言保持。既有case证据增加首/后异常type/message，所有锁、预算、无提交和cleanup断言保留。不是向通用regex加closed等词。plan.json给精确分支文本和完整scope。

完整ebf1 testbefore/base64/mode已保存。实施必须等待R283真实ROOT失败结算并独立接受，再ROOT source gate释放。旧ROOT RESERVED角色作为历史before，以真实结算archive映射；不得硬比未来live。只允许本exercise变更，其余26源/211保护、observer、helper、产品、runner/plugin、TTL/authority不动。

四新DB原/archive字节与12 absent sidecar已有限核对，无SQL；537attempt/535init/537cleanup为观察分母。raw缺assertions_completed不能当False或PASS（R283另处置）。原raw、失败、角色、旧计划不覆盖。

本轮新运行/测试/static/SQL/Git/review额度0。旧memory已spent不能退款。后续必须新实际Astra执行计划绑定新test世代及明确memory once；unused sqlite/dual保持held，不能直接套旧门。源接受不等于行为通过。冻结后STOP。
