# R402 — native 结果身份关联断言纠正

实际模型 gpt-6-astra；仅测试输入/身份合同纠正。原生 ETEAC已在1.551207828秒自然SUCCEEDED、task_success=true，attempt结束/lease释放；sentinel仍QUEUED attempt0，错误断言使第二poll未执行。旧失败原样保留，不能称pair通过。

worker 将 job.run_id 放入 ExperimentConfig.experiment_id；runner 将它放入结果 experiment_id。结果 run_id 则是 stable_run_id 的确定性哈希，**不是随机值，也不是job.run_id**。

只把现有一行 `assert experiment.task_success and experiment.run_id == job.run_id` 改为 `assert experiment.task_success and experiment.experiment_id == job.run_id`。其余断言/fixture/源/超时不改。旧测试已逐字节保存inputs/test.before.py；精确预期新SHA见input-audit。修前必须等所有活动阶段终止并清理；R401两个guard优先在旧冻结测试上完成。

AST仅反向标准化这一个Attribute后应与旧树相同。原R399 freeze不覆盖；adapter只对新R402 successor stage接受明示新SHA，不能全局豁免测试。旧RED/GREEN及guard依据不变；最终说明新旧测试快照不同，guard产品及实际guard测试字节未变，不能称全源pinset相同。

新增一次fresh-DB native pair successor≤90秒（原inner75、每poll30、cleanup15），原argv/输入/真实worker不变。两任务须自然通过全部原断言并记录官方实际source_tree_hash。原native额度已用，不复跑旧stage/不覆盖失败；本轮明示新一次，0retry，仍在R399原1800秒内。

guard验收仍独立必需。最终独审及Git仅用R399原配额，窄附加本轮小计划/失败/编辑静态回执/步骤/解除和新验证记录，旧测试副本/DB/raw留本地。未实施修复或执行验证。
