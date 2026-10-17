# R95 Reviewer Capacity Orchestration Plan

状态：PLAN_ONLY，单一编排任务。实际Astra规划；不实施产品、不派代理、不测试/Git。

原`followup_task(/root/sol_rw1_review)`返回`collab tool failed: agent thread limit reached`，未派出独审、未创建代理。原`failure.json`和`tool-return.txt`完整保留。R65要求“Failure to address an existing agent is a new tool issue, not permission to spawn”；本轮据此限定恢复，不继承R65旧权限参数或产品范围。

本次真实`list_agents`列出/root、/root/astra_delivery_boundary、/root/astra_oc2_residual、/root/sol_t12_p1；旧/root/sol_rw1_review不在列表，不能声称已恢复。候选/root/astra_delivery_boundary已完成R91规划，非P3/P4实施作者；实施作者是Sol。当前快照见registered-handles.json。工具未说明更深容量原因，不作推断。

## Task 1：复用确有handle的非作者

1. ROOT复核7有限元数据pins与计划链接，保留原失败。派单前至多一次刷新当前registry确认候选仍registered且idle/completed，禁止反复容量探针。
2. 优先对**/root/astra_delivery_boundary**发一次只读独审followup，明确仅冻结P3报告/实际源码证据，不产品修改、不测试/静态执行、不network/Git/spawn。若候选不再可用或ROOT选择直接审阅，在任何失败派单前改由ROOT作为不同作者只读独审；如实记录reviewer，不能将Sol作者自审改名。
3. 不重试旧handle，不spawn、清理或重跑tests。仅实际成功tool返回或ROOT实际开始/完成报告才能记路由结果，不能凭计划说已恢复。
4. 先看R92冻结材料的只读审查标PRELIMINARY，不能代替待R94检查或最终source审查；最终不同作者审查绑定实际最终冻结及原收据，未来SHA不预造。审查只pin实际读取文件，无全源/历史审计。
5. 新恢复收据/报告exclusive写`HAND/reviewer-capacity-20261008/recovery-round95`（HAND为既有t12-sol-handoff-20261007）或明确独占review目录；记旧失败、实际派单原返、reviewer/author区别、输入pins/结论/限制。旧两个失败文件不覆盖。

R93当前同一Sol单写者和已审R94序贯任务独立继续，不被本编排阻塞，不新增产品/actual门槛。若新followup仍失败，保存新原返并停该派单路线交下一实际Astra，不自动retry/spawn/cleanup；独立已授权工作继续。

验证仅元数据和真实路由/报告：ROOT新registry至多1、当前已注册候选followup至多1；旧handle retry0、spawn0、cleanup0、产品/测试/static/actual/network/Git均0。最高标`ORCHESTRATION_RECOVERED_READ_ONLY_REVIEW_ROUTED`，不是软件独审通过、更非实际或正式验收。本Astra只读一次registry并写本计划目录，尚未派单。

## 实际输入SHA256

| path | SHA256 | bytes |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/reviewer-capacity-20261008/failure.json` | `7f5b324fcf2305ecf7886a5327e3ce79257231ae9d2f0e94a3970b7de97a4d75` | 506 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/reviewer-capacity-20261008/tool-return.txt` | `21bf748c7ed0956d7802c80a66c7aa2904144f3d11c91ebd040b96719ee7af0f` | 47 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round65-oc2-agent-capacity/plan.md` | `76b947ef84068dae03ef8cba1cceae1789e5ac164bcc04ac34ecc85a00a249c4` | 8766 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round65-oc2-agent-capacity/plan.json` | `d6945e95a9f533b4c62f78bad6440087b6326822fa489f7c7020cc7647659e5d` | 13555 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round91-native-full-action-support-20261007/plan.json` | `c1086cf5b979fb1478076c6db547f4eda06f4a2800fdc3283031907f19b903d7` | 8105 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round95-reviewer-capacity-20261008/registered-handles.json` | `8a50b1519c9e569f01495dda75806dfe5ffd07a8a280be329445c22ec2883894` | 1120 |
