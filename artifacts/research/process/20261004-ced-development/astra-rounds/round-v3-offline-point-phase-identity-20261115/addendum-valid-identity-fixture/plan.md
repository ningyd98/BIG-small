# 合法阶段身份负例夹具补充

实际模型：`gpt-6-astra`。**PLAN_ONLY_NOT_IMPLEMENTED**。本补充只计划测试修正，原阶段计划字节不变。

原日志 `offline-pure-green-01.log` 显示2 failed、73 passed、12 deselected。失败参数为observation_id和frame_id：辅助函数先把两id变新，再单独还原其中一个，触发 `RGBDObservation.model_validate` 的 `observation_id must match frame_id`。provider尚未调用，不能用此异常证明PHASE拒绝。

仅修改新增测试文件，将两非法单字段例合并为合法“ids同时旧”例：两id都取before原值，capture仍更晚，checksum清空并由model_validate重算，RGB/depth/mask/sim_time不变。构造放在pytest.raises之外，先断言id配对合法、两id仍旧、capture更晚、checksum已改变；随后只对provider.point期待 `FROZEN_POINT_PHASE_REFRESH_REQUIRED`。拒绝后replay_calls与records都仍2。

capture相等例保留：合法的新配对ids、旧capture、重算checksum，构造成功后provider拒绝。正常fresh正例仍应4次成功。两个非法例合并后参数总数3变2，报告这一原因；不能skip/xfail或放宽regex接受模型ValidationError。

不改provider逐字段检查、不改生产validator/not_before，不使用model_copy/model_construct绕过合法性，不改RGB、深度、sim_time或容差。当前完整性/fault并行修改已经授权，实施前核对diff，不能用本轮旧快照回滚。

先跑聚焦两参数例GREEN，再全部point及offline纯软件测试、Ruff。使用固定隔离树PYTHONPATH、共享venv、PYTHONDONTWRITEBYTECODE=1、pytest禁缓存、唯一/tmp basetemp；无需EGL、网络、模型、仿真或提升权限。原失败log作为RED证据，完整命令未被原log记录，不编造。

本轮provider及生产observations.py前后SHA应相同；所有原计划/失败/输入快照保留。输入绝对路径与SHA见inputs.json，验证命令与验收细节见plan.json。原27仍待其余检查完成，不由本轮软件通过替代。
