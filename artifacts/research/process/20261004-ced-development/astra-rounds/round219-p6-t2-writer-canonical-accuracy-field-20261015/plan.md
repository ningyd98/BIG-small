# R219 — writer 精度字段单点修正

实际计划作者：gpt-6-astra。等待 ROOT 门控，唯一实施者为原 gpt-6.1-sol。

实际 OriginalActionRequirements 仅有 allowed_error_m；当前 _b_t2_writer_authorization 访问 required_accuracy_m。原 writer 与 R218 F4 都沿用了错误名称；R218 已接受的是源码范围，不是行为。保留其计划、归档、报告和门禁原件，本轮单独纠正这条字段映射。尚未运行复现 AttributeError。

仅将 allowed_error_m=requirement.required_accuracy_m 改为 allowed_error_m=requirement.allowed_error_m。当前254022B/4d9bb9dc…；唯一匹配位于241879。内存计算目标254018B，SHA ed602dc9ba5c0b15af20fbe8ca4d9b58d2e4e45fac621dc6f5e5e2cd4a94e7d3，尚未写入。禁止模型alias、getattr/fallback、默认值、校验放宽或其他字节修改。

按 ROOT 要求已额外源级核对实际模型字段和相关协议签名：ExecutionCheckpoint.current_step_index确实存在；legacy/local retry、local verification引用、域record getters与已核constructor字段未发现另一个确认错名。完整有限范围及局限见 input-observation.json，不能视为全部运行链可用。

ROOT先全文/pin gate；Sol先独占保存完整before并CAS，再单次替换，保存after/diff/report/actual。ROOT要求after严格等于before的唯一替换、其余全部字节及旧168003前缀恒等，并核runner/roles/19产品/211保护。duration/TTL/horizon、七正文、其他helper不动。

新增执行/测试/静态/审查/Git槽0，原T2两槽各0/1 HELD不重置。只正常stdlib元数据范围核对；完整行为仍待原GREEN。计划保存后STOP，无T2/T12/native/formal晋升。

