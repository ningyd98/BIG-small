# 3952 独占复验后处理的只读重建

02dbaef9 原测试已执行一次；exclusive-3952/pytest.xml 中 1 项通过、0 错误/失败/跳过，suite 记录 34.357 s。终态 worker 记录完成 9 动作、物理成功。run_exclusive_3952.py:143 随后遍历全部 camera_adjustments 直接取 step_id，合法的 CURRENT_REGISTERED_MARKER_AND_INITIAL_COMPLETE_WORLD_GEOMETRY 行使用 observation_id 与几何信息，没有 step_id；原包装因 KeyError 退出 1。已将相同表达式在保存的 JSON 上仅仅读回并复现。父轮的一次独占授权已用尽，本轮不运行 pytest、worker、渲染、模型、子试次，禁止执行包含原试次入口的旧包装。

Sol 从 plan.json 所列原件重建新的独立研究回执（仅新建派生文件，不覆盖原日志或虚构原包装已经落地的 result.json）。保留原包装代码、原出口/trace（如未持有完整 traceback 则按来源报告），并区分原 pytest/worker 与后处理退出。读取 JUnit、pytest.log 与 start 的命令、原截图帧和完整 worker 索引。若没有持久的 child exit 数值，记录 null/来源；不得把 JUnit 推断的 exit 0 填作原进程直接观测。对明确按 step 记录的 CURRENT_RGBD_VISIBILITY_RECOVERY 及 CURRENT_MEASURED_PLACE_OVERVIEW 校验 step_id、physics_step 和必要视图/来源，只把对应步骤计入恢复。全局 CURRENT_REGISTERED_MARKER_AND_INITIAL_COMPLETE_WORLD_GEOMETRY 原样另列，记录 observation_id、注册和视角上下文。未知或字段错型的分支予以记录并停止依赖该行的结论，切勿使用全局默认步号或静默丢行。

核对 LIFT 注入恢复观测及后续 PLACE overview、两个 RETREAT、末帧及原独立物理结果。将 step-05/3952 三个原帧与原并行失败及 3ca2f641 基线逐项对齐，按实际 observation_id/sim_time/标定与原 3 份 RGB、depth、mask 的 SHA 比较，绑定 visual_samples 的 stage_wall_ms 和已接受 control_samples 的 sample_and_ik_s。当前独占控制样本 87.624249 ms；原并行 114.533 ms、基线 98.519 ms 分别保留。验收为只读重建可重复、输入逐项 SHA 不变、正确解释六条调整与全局行，未再次执行任何节点。回执明确原并行失败、单次独占通过、汇总异常及未证实的调度/性能归因。
