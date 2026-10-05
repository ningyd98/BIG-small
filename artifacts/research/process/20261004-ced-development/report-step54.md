# 第54步：Astra修复计划与完整采集启动

用户指定的 Astra 已完成[修复计划](../../../../docs/superpowers/plans/2026-10-05-astra-repair-plan.md)：10项任务、48个执行步骤。原18个主任务及全部验收门保留；这些修复任务不表示原主任务已经完成。Astra只制定计划，没有执行实际试验，见[模型与输入报告](astra-repair-planning/report.md)。

计划先完成本轮 V3 采集器验收并立即采集、解码；RESET/UTC与Max配置独立推进，不成为V3开发诊断的前置。随后按真实来源→至少9独立支持校准组→三消费者/G1，结合Max与离线机会/200故障→B0/INITIAL→METHOD→功效/FINAL→正式统计和复现的顺序执行。边缘模型继续后置。

本轮 V3 两项软件P2已由[独立复核](t7b-continuous-visibility-v3/fix-round-1/independent-review.md)关闭：90项CPU通过（5.18秒），未修改原六反例均拒绝；额外BEGIN/FAILED保留4次分配和3帧保存。全部操作身份、原journal分母、成功120步settling/9动作/两次dwell配方及首model/reset/camera前真实运行时来源检查成立。新协议为32项来源/440598字节/21环境pins；原首版和旧失败原件不改写。

Root唯一完整仿真采集session75370已终态退出0；原始summary记录4807次分配/保存、0采集失败、9个动作BEGIN/END、0动作失败，wall_elapsed_s=915.764513714。这些是运行摘要计数，尚待原件完整性重算。原件位于 `t7b-continuous-visibility-v3/fix-round-1/attempt-1`，summary SHA256为 `ebc43279533d53d390fa545278c6dae625a9dda46901f22b0daf53dd83f27dec`。Root随即启动固定读取器的完整性检查与条件离线解码，session60356仍在运行，输出位于 `astra-repair-execution/R01/offline`。不启动第二次采集，尚不报告decoder结果或连续证书；完整原件和活动离线日志不混入本步静止软件交付。

Astra新增一项提前判断：秒级量化及整个RESET/SETTLE slab可能使UTC区间过宽，必须先用一次prefix比较真实区间宽度与原TTL/deadline，再决定9组可行性，不降低阈值或用NTP标志补精度。[RESET/UTC设计独审](t7b-native-calibration-source/reset-utc-v2-design/independent-design-review.md)确认A→真实RESET/120SETTLE→B、planner工厂前prefix和独立unbound原件导出三项修正。Python/Go仍是未完成checkpoint，未接真实worker或发布者，本步不交付其未验证代码。

[Max只读预检](max-configuration-preflight/report.md)确认当前定位的app配置不可直接启动新的角色probe；保留历史35call证据与当前T3b的区别。真实密钥/应用配置仍需就绪，不能构造假profile或换型号。未扫描外部账户/会话内存，不宣称全局无key；本步新增Max/provider调用为0。

[固定工具链准备](native-clock-toolchain/report.md)保留官方Go1.27.1下载超时，改用按APT清单SHA/大小验证的固定UbuntuGo1.22.2包，在/tmp解压且version检查通过；无系统安装、Roughtime wrapper构建或UDP查询。

当前主线T12/18、T13并行，native/continuous/future及INITIAL/METHOD/FINAL仍未验收，formal_accepted=false。采集终态已记录，离线原件检查和解码结果另生成报告并汇入阶段总结，不将软件独审或计划文档当作真实研究完成。

Git静止交付已推送 `eed552283c1804e707f661c82ab547b7e1ac2916`，112路径/1,264,879字节，本地/上游/远端一致。原始日志101处尾空白及pinned legacy fixture的一处末尾空行保留，新代码和文档diff检查通过。见[交付记录](git-delivery-step54.json)；本段随后续文档提交推送，完整实际raw与活动decoder输出另行交付。
