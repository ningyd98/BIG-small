# R03 唯一真实 RESET prefix 诊断

**RESET来源前缀完成，时钟仍UNAVAILABLE。** 独审通过的P1–P4和CLI由root执行一次 `prefix-1`，进程退出0；真实SQLite job/lease/attempt、RESET、120步SETTLE和2次缓存相机采集完整保留。没有planner/model、显式RGB-D acquisition、动作请求或重试，原件读取器独立返回VERIFIED / prefix_complete=true。该完成值只表示前缀采集链完整。

GNU time实测整个进程wall **2.47秒**、peakRSS **221932KiB**。保存488个原clock pair、2个RESET事件、120条物理步骤、486个operation事件和2份真实缓存帧。独立只读核对56个非runtime-DB文件/**7989524字节**，before/after不变；原件、库存和判断见 [机器记录](independent-actual-review.json)。运行数据库仍本地，不作为Git来源授权凭据。

## 实际时钟结果与限定拒绝原因

实际只发送1份A请求并收到1份数据包；固定wrapper在协议字段检查阶段拒绝，B记录为SKIPPED_A_UNAVAILABLE，没有第二次UDP请求或自动重试。离线原包重放同一pinned binary返回1、stderr为 `response nonce differs from original request`，保存于 [wire-replay.json](wire-replay.json)。没有将该失败称为网络不可达或密码学签名无效。

对原收到字节只做framing/tag诊断：framing长度一致，包含SIG/VER/PATH/SREP/CERT/INDX六tag，**缺NONC**。[冻结draft08 §6.2及§6.2.3](https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-08#section-6.2)规定响应携带请求nonce；[固定官方Go实现](https://raw.githubusercontent.com/cloudflare/roughtime/75645289794cfbd71a08f0e7ecf9bc4f3f87d133/protocol/protocol.go)同样检查响应NONC。故本次原包与冻结协议不兼容，现有守卫的拒绝有依据；没有删除检查、换key、切draft或生成伪造响应。

签名验证未进入，收到数据包的远端身份尚未认证；configured hostname及实际DNS/endpoint原件留在exchange-attempts.json，不能据未认证包断言Cloudflare全部服务不符合标准、全球不可用或公钥错误。本试验也没有证明任何其他UTC路径不可用。

historical_conditional_intervals为空、historical width及TTL比较为null；issuer accuracy仍UNVERIFIED，current/nativeUTC、consumer feasibility、role绑定不可用，raw source UNBOUND、source consistency INCOMPLETE。没有adopted RawV3、有限几何/运动界、校准组、任务完成或正式研究升级。

## 软件与读取验证

运行前R03限定独审31owned CPU、16窄回归、8源Ruff/format及3源mypy通过；105输入before/after不变，见 [独审报告](../implementation/independent-review.md)。actual复核只读取已终态原件，不重复这些测试或renderer。

root读取摘要首次误从frozen对象查找不存在的operations字段；实际operation-ledger.json含486项。改为读取该真实ledger后摘要完成，原prefix/source verdict没有改变；该元数据lookup失败在机器报告保留，不计软件或物理反例。所有旧失败、CPU替身与真实本次调用分别记账。

后续按[Astra计时审计](../../../astra-repair-planning/clock-dependency-review.md)及[执行补充](../../../../../../../docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md)推进新版本单机操作计数域；它不回填本次旧UTC原件。R03严格UTC路径继续保持原语义，本次拒绝不阻塞独立的标记可见性或离线教师研发。
