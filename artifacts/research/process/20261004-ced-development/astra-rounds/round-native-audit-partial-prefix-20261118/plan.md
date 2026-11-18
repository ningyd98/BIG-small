# Astra：只读汇总工具的提前停止证据分类

实际 `gpt-6-astra`，PLANNED_NOT_FIXED，6项SHA见JSON。首个fixed01只有5动作、615条accepted joint；旧checker已遍历现有interval及绑定/时钟/速度/加速度，最终完整任务数量门 `checked>10 && handoffs>=2` 抛精确 `insufficient continuous command/handoff evidence`。这是新auditor误套完整证据量要求，不是产品缺陷；原日志保留。

仅改新verify_native.py：所有有actions仍完整调用旧checker。只有非completed且异常确来自已绑定旧checker最终require的上述精确ValueError可记 `PARTIAL_HADOFF_EVIDENCE`，明示已有前缀interval检查完成、完整handoff资格未建立；不写PASS，不编造未返回的指标。其它错误全部原样抛出。3个completed仍执行全部原门。无actions的44104必须joint_target=0，只报 `NO_ORDINARY_TARGETS`，不冒跨段PASS。旧checker/require及原raw不改、不猴补。

先小量CPU工具反例验证仅该分支可分类，completed同错及其它绑定/速度等错误仍失败、无actions但有target仍失败。继续保留source snapshots/manifest、原RGBD+标定和独立物理复算。新汇总原physical_success_count误数component_success，限定同时拆成component_completed_count与真正physical_success_count；当前分别3与4，44103物理成功仍worker失败。

随后仅1次只读7case完整重验，新汇总/日志exclusive create；原native-verification.log与旧输出原文保留。任何新失败交下一Astra，不跳过。0GPU/renderer/model/API，不放宽产品或正式验收。
