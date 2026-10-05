# T10 独立模块软件准备

状态 SOFTWARE_ONLY_READY；研究与运行集成 NOT_RUN。33项新软件测试与41项已有在线验证测试共74 passed；定向 Ruff 和3文件 mypy 退出0。初始22项缺模块失败、加固6项失败、机会回放4项缺模块失败的RED日志均保留在父目录；GREEN日志 t10-module-green.log。不能将这些测试写成真实G3或任务成功。

新增不可变视觉证据、动作契约、提交身份、有效期验证与B3消融。新门计算 error + motion*(age + action duration)，缺校准/身份/传感器/前置证据为UNKNOWN；B3仍保持普通TTL、条件、上下文和确定性版本检查。决策复核检查task/episode/frame/plan/command/mode/context/candidate身份和取消/过期，当前bool版本也拒绝。

接口裁定：计划四参数纯验证接口仍保留，新增可选 online_evidence 以通过唯一evaluate_conditions入口重新计算精确目标/容差的前置条件；不接受外部PASS声明。缺此证据时有前置条件的动作UNKNOWN。嵌套条件与传感器集合复制冻结，避免审批后可变输入漂移。后置条件只在执行后验证。

离线Opportunity/GateReplayRecord绑定原快照/候选/来源组/标签hash，完整固定集合回放不由政策动作选择分母；独立标签从不传给在线验证器。UNKNOWN与误放行/错误拒绝单列，缺组、重复、变更或混合方法拒绝汇总。

限制：实际已冻结固定机会尚未生成；未接入task_executor/ReplanApplyService/SafetyShield/云返回的两次提交边界；既有执行器因此尚未宣称获得新门。独立审查待执行，T10整体仍IN_PROGRESS。

## 独立审查修复第一轮

F1显式提交时钟与canonical条件时钟统一；evaluate_conditions增加可选now（旧调用保持当前UTC行为），JOINT/B3均传提交时刻。F2每个固定Opportunity必须明确冻结replay_at/replay_calibration_version，并复制冻结RobotState、TCP Pose和嵌套visual_facts；这些均进入content_hash。回放仅消费已冻结online_evidence，不能外部替换；时钟/配置不匹配拒绝，旧判定不能汇总到已变更输入。F3 EvidenceVerdict和GateReplayRecord严格校验枚举，不支持的状态不能形成零错误报告。

新增clock两项RED与输入/类别两项RED保留。修复后37新+41已有=78passed（与此前74有重叠）；Ruff及4文件mypy通过。当前源码fix-round-1-hashes.json；fix-round-1.diff含唯一canonical条件入口的窄接口增量。等待独立复审，仍不是整体T10验收。
