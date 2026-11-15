# 最终离线证据验证器：状态事件判据修正计划

实际模型：`gpt-6-astra`。**PLAN_ONLY_NOT_IMPLEMENTED**。本轮只规划临时验收脚本修正，不是执行失败修复，不修改已冻结入口，不重跑27。

原 `/tmp/bigsmall-v4-execution/verify-final-offline-evidence.py:93` 断言 `events[-1]["next_status"] == "SUCCEEDED"` 失败。原脚本与日志已原字节保存。本轮独立以 `p.as_uri()+"?mode=ro&immutable=1"` 读取27个数据库并核对前后SHA不变：全部唯一job为SUCCEEDED、attempt1成功、lease已heartbeat/released。全部seq7是job_completed（FINALIZING→SUCCEEDED），之后seq8是artifact_created，状态字段为空。

生产worker明确先切换终态，再追加artifact_created，再释放租约；后续审计事件合法。错误是验证器将末条事件混同末条状态转换。本轮仅核DB状态和事件，不宣称其余物理重算、599来源或逐文件证据已全部复核完成。派生SELECT快照保留全部events/attempts/leases，原DB仍留原地只读，不将派生JSON冒充数据库备份。

## 最小实施

复制旧脚本为 `/tmp/bigsmall-v4-execution/verify-final-offline-evidence-02.py`；02已存在则用下一编号。旧脚本、旧失败log不覆盖。仅改DB状态判据、必要报告字段和新编号输出路径：

- 查询simulation_jobs全部行，要求唯一、job_id与result/attempt/lease一致、status=SUCCEEDED。原attempt1、唯一租约、released/heartbeat检查不变。
- 保留全部按sequence排序events，核对同job。另建立next_status非空的状态事件视图，要求非空、最后状态SUCCEEDED，并确有job_completed成功事件；对当前路径可明确最后状态事件为job_completed且FINALIZING→SUCCEEDED。
- 不以“曾成功”替代最终状态，不删除后续空状态artifact事件，不修改DB或把空值改成成功。不硬编码seq7/8；记录last_state_sequence、last_event_sequence与后续审计事件。

在/tmp的内存行副本做小负对照：成功后artifact空状态通过；jobs缺失/重复/非成功、末个非空状态FAILED、缺job_completed、混入别job事件必须拒绝。不修改真实DB，不新增仓库测试。

保持其他全部验证原样：27分母、8动作16shield、4point1cloud、0新模型/网络、599来源与3入口SHA、逐步物理样本重算、manifest逐文件长度/哈希、589帧新旧零差异。运行新脚本只是读证据并evaluate_evidence重算，不启动仿真。新输出用 final-offline-evidence-verification-02.log/json，独占写入。

## 前置与验收

先复核inputs.json与已冻结3入口SHA；固定新树PYTHONPATH，shared .venv，PYTHONDONTWRITEBYTECODE=1。27DB须是终结静态且无未checkpoint WAL依赖；若有活动写者/非空WAL，不能靠immutable忽略，暂停另核。数据库URI只读，finally关闭，前后SHA不变。无需网络、模型、硬件、EGL或提权。

新旧脚本diff只能含本轮状态判据与报告/输出路径调整；其余检查不删减。完整新验证器exit0、报告生成后才能宣称最终证据复核通过。原3入口、全部DB/events/原始数据与物理阈值保持不变；遇到新失败保存证据并再次Astra。
