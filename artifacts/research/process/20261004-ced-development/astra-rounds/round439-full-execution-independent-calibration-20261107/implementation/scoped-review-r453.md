**R453 限定复核归档 — CHANGES_REQUIRED**

评审人：/root/review_full_execution_calibration；日期：2026-11-08；基础 HEAD：8534419b7e22396985f66d1b0f2714fe8e16e5fb。

本文件归档同一 reviewer 在 R451–R453 完成后、R454/R455 修复前已经发出的限定结论；归档写入发生在最终复核时。下列行号对应当时 R453 源码快照。原 whole-change-review.md/json 保留，当前状态另见 scoped-review-final.md/json。本轮仅阅读源码、计划、diff 和已有证据，没有运行测试、probe 或 actual，没有修改产品、index 或 HEAD，也未派生 agent。

**当时结论：暂不能放行首组 actual。** F1、F3、F5 已闭合；F2、F4 尚有具体缺口。

| 原 finding | 当时状态 | 复核结果 |
|---|---|---|
| F1 | CLOSED | 接受原始 -1 背景；非负实例仍须标签；未知负编号拒绝，未补造原件。 |
| F2 | PARTIALLY_FIXED | RESET 写盘、observer、audit 失败已首步拒绝；转换异常分支仍待 R454。 |
| F3 | CLOSED | 已重放初始目标、延迟、裁剪、夹爪、hold 清队列，并比对所有 CONTROL 原件及方程。 |
| F4 | PARTIALLY_FIXED | 操作覆盖、双 PHYSICS guard、step RETURN、active-check 对应和真实 STOP 链已建立；最终 CONTROL 当前步仍缺绑定。 |
| F5 | CLOSED | 返回 pass 在可失败持久化前计入；重复 END 不重复计数；未完整返回时保留下界和未知精度。 |

**Important / P1 — F2：RESET 转换异常仍能通过首步检查。**

R453 native_full_horizon_recorder.py:124–163 的 require_clean_reset 未检查采集 RawInterval 的 ABORTED/error 或观察 payload 完整性。旧 vision/raw_recorder_v3.py:572–578 捕获转换异常后仅修改 interval；新 recorder 随后仍可保存 observation_payload=None 的 source-frame 和 receipt。因此现有 failure 列表为空时仍可能进入 SETTLE。确认属于已提交 Astra 的 R454 同一 F2 根因，无需另开问题。

**Important / P2 — F4：STOP 内部 CONTROL 未强制处于最终 N。**

R453 native_source_effect_graph.py:351–369 只确定额外 CONTROL 的身份、顺序与嵌套；:190–203 仅要求 payload 目标步等于其自身当前步加一。静态反例：既有七步软件图的关节位置不变。将最终 CONTROL 的 source、event、ledger、interval 当前步一致改成 6，payload 目标步改成 7、时间改成 state[6]，目标重放仍吻合；:458 的 guard 重建又跳过该 CONTROL，因而缺少拒绝跨步终止记录的约束。须绑定 STOP 当前步=N、内部 CONTROL 当前步=N、payload 目标步=N+1。这是 F4 尚未闭合的边，不属于 R454。reviewer 当时未执行反例，后续交实际 Astra 制定 R455。

优点：新增模块保持纯读取，返回 execution_admitted=False、native UNKNOWN，没有增加执行权限。正常 guard 语法与冻结 backend 一致，包括重复 PHYSICS 检查和准确的 safe STOP 例外。已核对的关键源码 SHA 与 R453 报告一致，旧 backend/camera/RawV3 与冻结输入一致。

当时已阅读的已有软件证据：R451 2 PASS；R452 3 PASS；R453 5 PASS、限定回归 50 PASS、ruff/format/mypy 各 PASS。全部仅为软件证据，不替代 actual。

Critical：无。Important：上述 F2、F4。Minor：无。Declined-to-judge：实际运行效果与资源表现、R450 环境放行、后续九组/native 正式资格，均不属于本次限定复核。

**当时审阅源码 SHA256**

| 路径（仓库内） | SHA256 |
|---|---|
| src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py | d9bfbfc3e4f59aa1c843e4a7e457d423e11e8d2d49f4de6dd0ddb223257b374f |
| src/cloud_edge_robot_arm/research/native_source_effect_graph.py | e1a42b970d383d4af99759edaca294e96406c3b98c7151e7b29b46609d3258fc |
| src/cloud_edge_robot_arm/research/native_full_horizon_originals.py | f8923c54649957391e0d56b3ce18fe8f1b0bb05a75e3896178bee1cd8116b8d9 |
| src/cloud_edge_robot_arm/research/native_collection_application.py | b670996d36826e3ad303459dd55b89f67f6c6f52a4b4e67392eacde2ee916d0e |
| src/cloud_edge_robot_arm/simulation/mujoco/backend.py | 498efa2b2947d70cce8e311aa57a77fbcb50a978db592f44cba8d0ac2f5aa7e0 |
| src/cloud_edge_robot_arm/simulation/mujoco/camera.py | d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f |
| src/cloud_edge_robot_arm/vision/raw_recorder_v3.py | 4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303 |

首组 actual 当时为 NOT_RUN，native UNKNOWN、qualified_group_score=null；代码未获本次限定评审放行。
