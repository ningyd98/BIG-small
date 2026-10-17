# R214 — writer 参考路径的来源清单

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅计划。

原bfa96d退出2：Memory取消规则与TaskContract两段已返回；猜测tests/test_recovery_lifecycle.py不存在。与R211同类根因是按概念猜basename，不是产品失败。原actual和de98ed两份归档完整保留。

实际清单及import链已确认：test_recovery_lifecycle_module.py 的 detected_record/authorization_proof/atomic_authorize；其依赖 test_phase6_2_replan_resume._contract 和 test_visual_evidence_contract.online_evidence，后者依赖 test_rgbd_observations.observation_payload。四文件完整pins、方法位置与有限ranges在JSON。其他候选不作替代。

ROOT审核精确source/argv/env后，同一Sol仅一次读取这些必要段，共465行、120秒、输出≤36KB；先核文件hash和范围，不重读两个成功段，不重放失败命令。实际return立即store并完整保存；未知独立流null。任何超界/失败STOP，不猜下个文件名。

后续writer参考必须来自这份map或已实证manifest/import/清单，先记录来源与hash，不能按概念拼文件。CPU RecoveryAuthorizationEvidence/contract/observation只是模型输入，不赋予local权限；真实拒绝测试须有效绑定的输入与正确拒绝边界，不能用无关invalid数据代替。

227116测试与27093partial报告为历史归档，合法writer追加不要求current wholefile等于旧SHA。R211/R213已验收不回滚，R212同席恢复不变。新增仅一次metadata读取；产品/测试/AST/static/Git/SQL等0，原T2两槽仍HELD。成功只恢复准备，不证明T2/T12/native/formal。
