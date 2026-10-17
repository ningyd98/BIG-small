# R242 条件同步修复实施计划

> 实际计划作者：`/root/astra_status_plan`，模型 `gpt-6-astra`。仅冻结计划；ROOT 全文及输入门通过前禁止实施。
> 实施者沿既定 sole Sol；使用 executing-plans 逐项落实，不新增代理。

**目标：** 去除竞态夹具中与产品预算无关的固定十秒放行假设，在既有全进程上限内保留真实竞态。
**结构：** 只改新竞态夹具的一次 `release.wait` 调用；真实主线程完成 binding、两库 COMPLETE 与 readback 后仍由原事件放行。失败退出仍由原 finally 放行并 join。
**技术：** Python threading.Event、既有 pytest 三节点、标准库证据脚本。
**规范：** R237 合法 RED 合同、R239 原诊断计划及最终结算；精确引用见 plan.json 和 input-observation.json。

## 事实与边界

R237 恢复 RED 与 R239 诊断均在 writer 的十秒 release 等待超时后继续达到真正 bootstrap、binding 和两库 COMPLETE。原竞态断言确有失败，但失败来自 writer 异常，没有证明正向 legacy 竞争写入，因此全部旧结果仍非合法 RED。

ROOT 完整分类571条保存样本；严格真实 writer 等待窗口分别39/39/38条，观察跨度约9.699/9.942/9.944秒。profile 出现在 top12 的26/25/25条是栈上下文计数，绝非 CPU 百分比。非原子采样不能证明主导耗时或全面排除死锁。Astra 原可选聚合失败已由 R243 保留并放弃，本计划引用 ROOT 原始分析，不冒称 Astra 完成同一聚合。

## 唯一源码差异

`tests/test_local_public_writer_binding_race.py` 中恰好一次：

```python
assert release.wait(10), 'R223 original writer release timed out'
# 修改为
assert release.wait(), 'R223 original writer release timed out'
```

删除的只有参数 `10` 两个字节；其余所有字节不变。原文件16529B / `84e771641c669c5d67d8c19fa51e8df759e32fd480c6c0762c2a98bcb8de2093`；预期新文件16527B / `c14e1f7b02f4e3d93a94245a075c6d8a7d3d386705a61afd173acea979e054ae`，这是预计算目标，不是已实施结果。

这个调用等待既有事件，不另选更长秒数、不增线程/计时器、不变产品 OC1、TTL、原始义务或权限。唯一子进程仍600秒、总清理15秒；其他 wait、join、finally、原断言及观察器全部原字节。进程超时或清理不全绝不是合法 RED。

## 执行步骤

- [ ] ROOT 完整复核计划、输入索引及最终 R239 结算，建立 R242 独立三槽，全部初始 HELD。
- [ ] 唯一 Sol 保存完整 fixture before，实施上述两字节修改，保存精确 diff/report，编写本轮两个作者脚本；不编辑任何旧脚本。
- [ ] ROOT 核对预期 whole SHA、精确单点差异、另外26源/211保护及两个脚本全文、literal argv/env/history map。
- [ ] 仅预约并执行 baseline 一次120秒；保存当前27源完整物理档、固定输入与历史映射，ROOT 接受。
- [ ] 仅预约并执行窄 Ruff 一次120秒，E9/F63/F7/F82 检查唯一改变的 fixture 与两个新作者脚本；ROOT 接受。
- [ ] 仅预约并执行恢复 RED 三节点一次600+15秒。沿用 R235 原 import-only 插件，不加载 R239 sampler 或 R234 trace；完整保存实际结果后 ROOT 结算并 STOP。

精确 argv、cwd、有限环境、路径和实际退出预期均在 plan.json.commands。禁止试跑、额外 collector、预启动 helper 或任何重试。

## 合法 RED 与资源

必须 exact3 nodes / 3FAIL / 0ERROR / 0SKIP，失败恰为原 late-local-binding rejection 断言；同时每例真实 poll/episode、binding、job/event COMPLETE 均先于正常 release，writer 必须真实 returned、无异常，并有正向 legacy mutation 的实际 readback。没有实际写入见证、仅 wrapper1、仍超时或 cleanup 不全都不可接受。

资源按本次实际构造/partial-init/entered/never-polled 分母统计，不照搬旧738。保留线程、锁、broker/session/heartbeat/OC1、方法/profile恢复与真实 finally 清理；未观察到的覆盖仍 null。保存 JUnit、全部 failure_details/cases/resources 后才判 outcome。stdout 限6000 UTF8字节；独立工具流未知时 null。

## 输入代际与保全

input-observation.json 固定17项权威、27当前源、211保护清单、6原case/progress pins、R239最终结算7项精确历史映射及30旧DB/90 absent sidecars依据。STATE/PHASE 仅最终时间点上下文；后续允许事实更新须完整 before/CAS。

旧 fixture84e771 必须解析到 R239 fresh capture/before/sources 的完整实物，不能把 R237 历史 CURRENT_EXACT_BYTES 硬比新 fixture。仅这一个 fixture，以及索引逐项列明的 gate/角色/STATE/PHASE 世代可按精确 original/archive 三元组映射；保留其他属性、完整字节，禁止 blanket skip、递归扩大历史豁免或覆写旧 raw。

## 审查重点与验收

检查事件 release 仍只由原真实条件/失败 finally 触发；原异常不吞、原竞态断言不削弱；没有隐藏新时钟/权限；正确区分历史与当前源；所有超时/资源不完备均保留失败且停止。

旧诊断、旧 RED 与全部已花额度不重置。R223 余四槽/GREEN9、父 T2 GREEN7、fresh review12×600 和 Git0 均继续 HELD。本轮成功也只建立合法竞态 RED；event3 修复和后续 continuation 必须另由真实计划放行，T2/T12/native/formal 均不宣称完成。
