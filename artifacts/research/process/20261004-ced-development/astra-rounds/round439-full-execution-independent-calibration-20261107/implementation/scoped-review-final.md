**最终限定复核 — APPROVED_SCOPED_REVIEW**

评审人：/root/review_full_execution_calibration；日期：2026-11-08；基础 HEAD：8534419b7e22396985f66d1b0f2714fe8e16e5fb。该结论由原 whole-change reviewer 作出，不是第二次全仓审查。

**F1–F5 在限定代码评审范围内全部闭合，可推进代码交付与 fresh prepare。** 本次只复核 R454/F2、R455/F4 的批准计划、COMPLETE 附录、实现 diff、当前源码 SHA 与已有软件证据，并检查先前 F1/F3/F5 结论是否被这些改动影响。未发现新的实质缺口。prepare 尚未执行或验收，未来 runner/source overlay 仍须纳入准确批准差异及最终源 SHA。

**F2 CLOSED。** native_full_horizon_recorder.py:158–211 在 guard/sampler/首步之前，要求实际同源 operation-N 的唯一 ACQUISITION 原区间为 COMPLETE/error=None，唯一 live frame 有非空 observation_id/checksum，并从已校验库存字节解析 source-frame，核对非 null payload、acquisition/interval 与观察身份。它使用旧 schema 的真实 COMPLETE 标签，不修改旧 converter，不把 ABORTED/null 帧改好，也不补造 failure 作为唯一证据。原错误与原件保留；返回的两个 pass 仍 exact=2。app 的相邻 require_clean_reset 调用位置未改。

**F4 CLOSED。** native_source_effect_graph.py:85–90 从实际 physics 引用集合反求唯一额外 CONTROL，强制当前步=N、CONTROL_APPLY 区间=N→N、payload 目标步=N+1；后续原重放据此校核 state[N] 的时间、关节、目标和方程。原完整 graph 检查仍将同一 extra 映射到末尾当前 N 的 hold→STOP 内部 CONTROL，并保留嵌套、完整操作/guard/active-check 覆盖和无后续物理效果的约束。N+1 没有被计作额外 physics。

| 原 finding | 最终限定状态 | 结论依据 |
|---|---|---|
| F1 | CLOSED | 承接 R453 复核；背景/标签 reader 本轮未改。 |
| F2 | CLOSED | R452 的 observer/audit/write 首步拒绝加上 R454 的原转换区间/payload 完整性拒绝。 |
| F3 | CLOSED | 承接 R453 重放结论；R455 只增加终止状态锚点，未放宽目标、延迟、裁剪、夹爪或 hold 校核。 |
| F4 | CLOSED | R453 全来源图及准确 guard 语法加上 R455 的终止 CONTROL N/N+1 绑定。 |
| F5 | CLOSED | 承接 R453 复核；R454 未更改 pass 计账语义，相关四节点 GREEN 保持已返回与未知计数行为。 |

已阅读原 stdout/result 与实施报告：R454 conversion-red 恰 1 FAIL，断言实际为 reset→guard；conversion-green 为 4 PASS。R455 terminal-red 恰 1 FAIL（DID NOT RAISE），同步回退反例确实未被旧校核拒绝；terminal-green 为 6 PASS。两轮 ruff、format、mypy 各 PASS，所有阶段 reaped=true、remaining_live=[]、source_drift=[]。这些是已有 SOFTWARE_ONLY 结果，本 reviewer 没有重跑测试或执行反例。R453 50 PASS 保持历史证据，不声称它覆盖后续改动。

R456 仅记录 shell 的未限定 python 命令不可用和 before 证据恢复：前置恢复使用已知 .venv 运行时，before 来自冻结的修改前原件，未覆盖当前测试；没有额外测试或产品更改。收到的 shell 失败报告不被冒称为原 stdout 文件。

本次修改范围与 R454/R455 相符，关键当前 SHA 与两轮 step-report 的批准后 SHA 一致。新 graph 仍为纯读取校核，没有 backend/DB/执行入口或授权令牌；native UNKNOWN、execution_admitted=False 的权限边界未改变。旧 backend、camera、raw recorder 与原冻结 SHA 一致。

Critical：无。Important：无未闭合项。Minor：无。Declined-to-judge：实际 physics/render 效果与现场资源表现；R450 服务授权及现场前置；后续九组/native 正式研究资格；Git 推送及远端复现包。本次范围不要求新全仓审查或额外 actual。

**Ready for first actual run? 当前仍为 No，原因是独立环境/授权放行尚未完成。** 代码评审没有剩余 F1–F5 阻塞项；须完成 fresh prepare，并满足 R450 显式授权及原 R439 全部现场条件后，ROOT 才能放行原 seed439001 的唯一 actual。ROOT 报告 R450 尚无人回复、服务操作=0、actual=0；本 reviewer 未操作服务或采集环境。此结论不授予新的运行次数、模型请求、停服务权限或 native 正资格。actual 仍 NOT_RUN，native UNKNOWN，qualified_group_score=null，正式研究 NOT_ACCEPTED。

**精确审阅源码 SHA256**

| 路径（仓库内） | SHA256 |
|---|---|
| src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py | 9db611d7685948629e740f165f20347016a92fa9b908f961bb790a7d23387324 |
| src/cloud_edge_robot_arm/research/native_source_effect_graph.py | 06bf67f77f5e28122aeb6d0f9f8121abb935113cd5d3af59112d6b921275c06f |
| src/cloud_edge_robot_arm/research/native_full_horizon_originals.py | f8923c54649957391e0d56b3ce18fe8f1b0bb05a75e3896178bee1cd8116b8d9 |
| src/cloud_edge_robot_arm/research/native_collection_application.py | b670996d36826e3ad303459dd55b89f67f6c6f52a4b4e67392eacde2ee916d0e |
| src/cloud_edge_robot_arm/simulation/mujoco/backend.py | 498efa2b2947d70cce8e311aa57a77fbcb50a978db592f44cba8d0ac2f5aa7e0 |
| src/cloud_edge_robot_arm/simulation/mujoco/camera.py | d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f |
| src/cloud_edge_robot_arm/vision/raw_recorder_v3.py | 4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303 |
| tests/test_native_observer_failures.py | cf1b09070620bcf9d2a15b59269a0bd64ace65e67cbbaa80ba994b9bb8a75923 |
| tests/test_native_effect_graph.py | b90ee0da66c6b67ba97bde6b8d83d7cd909802969d42429aa1f739d04d90929c |
| tests/native_collection_source_graph.py | f15994625fb39ba9cc58884ca07527679048845597c13ec66225cb2da675d50e |

原 whole-change-review.md SHA256：45059cb098418273310dbdbd9064a6af0bdb487070742f21fc02720f1113e9ee；whole-change-review.json SHA256：9a53e5e98c01f9a4aebd2fdccb89973182bfb373719d9cb28549ae515b006099。本次只新增 scoped-review-r453.md/json 与 scoped-review-final.md/json，不覆盖原 whole-change 报告。
