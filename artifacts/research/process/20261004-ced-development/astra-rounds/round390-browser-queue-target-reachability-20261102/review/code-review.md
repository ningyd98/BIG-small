# R390 唯一离线诊断产物独立审查

`APPROVED_R390_BOUNDED_OFFLINE_EVIDENCE_SCOPE`。Critical/Important/Minor均无；可将准确的离线结果纳入精选证据。原19个browser目标仍开放，不能称browser修复或新行为验证通过。

产物确认一次隔离script完成，elapsed0.084775秒，stdout等于diagnostic-result且stderr空；协调席报告工具exit0。execution-start绑定批准的4f1037…script和原120/15/300预算。63input-freeze逐项等于plan及当前bytes；10closed trace pins匹配。审查未重跑script、导入产品、执行测试、连接DB、联网、发信号或写Git。

只读副本观察包含14job/2attempt/79event/2lease，均低于10000行上限，无query limitation。原DB前/后/最终SHA一致，原/副本DB当前byte hash复核同为a562982…；只有副本产生SHM及空WAL。reviewer仅按文件字节hash，没有SQLite连接。

## 已确认与尚未确认

PCSC sim-619…记录SUCCEEDED，started10:59:34.193821、completed10:59:35.697114 UTC。随后ETEAC sim-636…记录RUNNING/attempt1，started10:59:36.009520、updated11:06:46.974494、completed为空；其attempt ended和lease release为空。其余所选任务QUEUED/attempt0，其中三个MUJOCO capture任务亦未领取。

源码的dispatcher同步轮询worker，而heartbeat是独立线程。因此证据支持“ETEAC同步执行未记录完成/返回，后续任务未领取”。没有实时线程栈或return探针，不能定位至runner.run内部、清理或某把锁；internal location=UNKNOWN、deadlock/performance root=NOT_PROVEN保持正确。stored timeout30不是已证明的异步中断或含排队端到端SLA；queue_position源于queued_count，不应当精确排名。

三项RGBD仍各自保留原停点：未到SUCCEEDED；capture仍QUEUED、后续visual-planning提交未到；published_groups0、cancel请求未到。trace和副本记录不支持“render已运行失败”“视觉规划失败”或“取消失败”。没有跨trace相对钟、虚拟时间与UTC混算。

## 后续边界

下一实际Astra计划应先限定如何取得ETEAC完成/返回位置的缺失证据；任何active probe、源修、等待/并发策略调整或重跑都不在R390额度内。之后再分别判断capture调度与目标可达性，不能先并根因或扩大timeout。

R393可依自己的批准门交付已验证版本修复和如实报告；原DB、forensic-copy及完整raw仍按原边界留在本地。精选清单/派生报告不是完整远端复现包。本席不判断Git推送状态，也不升级真实运行、性能、硬件或正式研究验收。
