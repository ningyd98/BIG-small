# T12 实际视觉 worker 编排独立审查

审查当前 `evaluation.py`、`execution.py` 和 `test_visual_worker_execution.py`，未修改被审查文件。90 项限定 CPU 测试通过，18.41 秒；明确包含真实租约/attempt 与内存、SQLite 事件仓储的合成来源端到端测试，实际模型及机器人动作均未运行。

发现并关闭一项 P2：可选周期监督直接采集/请求模型及等待期间推进物理，未使用持久来源 claim。实现者已在 `ExecutionPolicy` 对 live worker 的两个选项设置执行前拒绝；独立使用真实 job 租约配合两种事件仓储验证 4 次拒绝，原始预算与 revision 保持不变。该修复属于当前功能未实现时的明确停止；后续仍必须补齐监督和等待的持久 claim，不能把禁用能力计为全部研发完成。

当前未发现新的阻断性代码问题。初始采集、规划均先 reserve 后执行，再校验真实来源并 complete；原始绝对截止时间、全部原始条件/安全约束/时长/retry 保留。实际 OPENCV 路径绕过会删 HOME、改变速度约束的 legacy 编译器。来源路由会清空 grounding，执行路径重新绑定并核对完整 payload，PRE_SAFETY 和 PRE_SKILL 后都直接检查完整原始 native 条件；typed 实际返回结果及独立的较晚帧是效果验证的必要来源。raw recorder 使用工厂已有唯一 executor。

尚未实现且必须保留：监督/等待持久 claim；native 几何/连续运动证书；POST_HOLD 全条件注册（当前缺 object_held）；TERMINAL 对原始 completion criteria 的完整映射。缺失映射目前明确停止，不能记为 hold 或 terminal 验收。当前 UNKNOWN 来源端到端为 3 张合成帧、1 次合成 provider、2 次 quota 消耗、0 动作，两种事件仓储的原始 deadline 和 retry 均未重启。

本审查仅通过软件编排范围，不证明真实 Max、raw COMPLETE、METHOD、INITIAL/FINAL 或物理研究成功。精确源码 SHA、行引用与限定命令见 [review.json](review.json)；独立选项探针见 [optional-effects-actual-repository-probe.json](optional-effects-actual-repository-probe.json)。
