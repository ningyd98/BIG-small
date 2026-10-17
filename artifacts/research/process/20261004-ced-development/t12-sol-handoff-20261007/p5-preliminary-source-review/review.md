# P5 不同作者冻结源预审

状态：**PRELIMINARY_SOURCE_REVIEW_NOT_FINAL_ACCEPTANCE**。审查者实际 gpt-6-astra，与产品实施者 GPT-6.1-sol 不同。审的是 R103/implementation/source-after 的十份冻结快照及已批准 R105 修订边界；没有读取 Sol 活动产品文件，没有测试、lint、formatter、产品 import、actual、Git 或源修改。

本次有限源审查**未确证新的产品缺陷**。此句不是软件 PASS。R105 已知六静态诊断和两夹具修订不再作为新问题提出；最终软件结论必须等待该轮终态、最终十源、全部剩余验证原件及独审。原 P5 明示的 UTC_LEGACY_VETO、P6 事务/dispatch 缺口不冒充新发现，也不冒称已完成。

## 已追踪的生产语义

所有以下行号均指 R103 冻结快照，R105 排版后需要重新映射。

| 审查项 | 源证据与判断 |
|---|---|
| 原 startup 和来源 | worker.py:214–231 在真实 RUNNING 后、_run/RESET 之前夹住原 `_active_task_origin`。operational_windows:149–211 读取真实具体 SQLite job/lease/唯一 attempt 与 role policy，排除既有 prefix；:249–262 一次消费 pending，实际 thread/registry/source 再校验。来源字符串/描述不独立生成 owner。 |
| 晚 runtime handoff | worker.py:792–862 绑定已有原 task tuple、真实 source inventory/role/lease 后签 token，:925–939 传入实际 backend episode；windows:532–549 pop token、检查 exact binding/source、episode仅一次。不把 RESET/settle 后 runtime 时间作为新起点。 |
| AGE/HARD 与 parent | windows:364–433 只接受已登记父窗口，展平继承所有 AGE/HARD；分别读取各自 origin 配对 current，AGE within_age 与 HARD before_deadline 分别执行。没有用单 min<= 同时替代两种端点；bootstrap 原 task 硬窗限制原 receipt。:435–493 导出 typed constraints/effective endpoint且 NOT_EXPORTED。 |
| 冻结 descriptor | :51–83 拆解不可变 Mapping/tuple且拒非JSON/非finite/循环；:739–892 验证字段/类型/端点算术，bool不能作整数约束。:619–676 再与当前 issued export 精确比较并使用原 observation/event；codec 本身不授权限。 |
| 原 policy 交集 | :895–932 对真实已注册 observation 固定 requirement/max-age source；已有不同 policy拒绝，:619–646 对原窗额外检查已绑定较小政策，不重新签原 acquisition。worker_runtime:1175–1191、1254–1268 和 785–791 分别接 condition、grounding、supervision 真实原 requirement。 |
| 公共回放与提交 | bootstrap:359–393 用纯 `_derive` 重建完整历史；:764–790 历史重复只返回 HISTORICAL_DUPLICATE，新提交必须 `_consume_transition`。supervision:810–861 同样先区分历史，再消费私有scope。windows:680–711 将真实 owner、完整payload hash、window IDs一次绑定；新版本缺refs不能降级legacy。 |
| 真实仓储接口 | runtime:975–1008 与 :664–714 用完整 typed request 包住实际 repository transition，返回值必须 NEW_COMMIT；新字段纯解码与 live消费分离，避免仓储复制/历史读取误授权限。Memory/SQLite 全部事务内 D 闭包仍属 P6；本次未执行这两个 engine，不把接口源审查说成运行通过。 |
| cleanup | worker:341–344 finally revoke，poll cleanup也撤销；windows:514–529 删除pending/owner/handoff/window/observation并关闭clock，重复无owner即return。R105只校准测试计数，不改变产品撤销语义。 |
| 外部/legacy | unlabelled condition 仍按 UTC；带 operational reference 但无 live owner 返回失败/UNKNOWN。marker replay明确只开发回放；源描述不能使 replay获得fresh/native权限。bootstrap legacy 无新字段不序列化该键；supervision 新字段存在才进入新typed校验。最终旧codec字节等价仍需真实GREEN。 |

这里未把 Python 私有符号当恶意同进程代码的安全沙箱；评价的是原已批准的真实生产者、registry与生命周期边界。

## 七消费者与实际测试证据的界限

- bootstrap/capture/plan：runtime `_transition`、reserve/complete capture 与 plan 实际接 enclosing effect、原 acquisition parent、任务硬窗和私有提交；category 节点确实调用 captured/usable_plan，不只是 helper 名称。
- grounding：category 节点真实 adopt 后调用 publish_grounding；其 D gate在 runtime:1254–1268。
- supervision：category 节点真实 initialize→reserve/complete capture→reserve/complete plan，并调用 decide_supervision；不同 max-age 再调用得到 DISCARD 的断言存在。冻结源中的真实生产 freshness门为 supervision.py:62–68 与 windows._check_context。
- marker：category 节点真的构造CPU图像源并调用 associate_marker_target，含frozen positive、source改变拒绝和真实过期拒绝；过期断言位置按R105修复，不能把原倒退夹具当通过。
- condition：category 使用 evaluate_conditions，且另一个 UTC-jump 节点 tests:323–345 真正调用该消费者，并在D>5秒断言UNKNOWN。

所有 category 尾部 tests:592–597 的 5秒VALID/+1nsINVALID/reboundUNKNOWN 是公共 `_check_reference` 断言。它证明拟执行的共同门覆盖，**不能记成 bootstrap/capture/plan/grounding 各自也已经执行了生产消费者过期/重绑定负例**。本次没有任何实际测试运行；不能仅凭测试名称或 AST 节点数宣称这些动作/分支通过。该差别记录为最终报告的证据精度边界，不擅自新增测试或扩大 R105。

## exception/cancellation 夹具是否只 patch 了名字

冻结 tests:445–467 在 during_episode 替换 `_raise_if_cancelled_or_timed_out`，分别抛 RuntimeError 与 CancelledByOperator。真实 worker:231–233 在 `_run` 返回后确实再次调用同一实例方法；:295–325 捕获后按实际类型选择 FAILED/CANCELLED 并调用 `_settle_failure_status`；:341–344 必经 finally revoke。这是具体后续调用链，不是从patch名称猜覆盖。

当前节点只直接断言清理和撤销，未在自身尾部显式断言所选terminal状态。因此最终可以表述“源控制流通向相应异常/取消分支，cleanup断言待GREEN”，不能把没有独立断言的最终终态伪称已单独验证。实际 factory执行与JUnit尚须最终原件佐证；不因此自行修改原节点。

## Git 导出依赖与最终需补证据

冻结测试 `legacy_codec(name)` tests:35–46 真读取并编译（本审查没有执行）以下两份 pre-P5 原件：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round102-p5-preflight-plan-shape-20261008/implementation/source-before/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py`
- 同目录 `visual_supervision.py`。

后续明确路径交付应保留这两份必要测试原件及 hash/角色，或在单独批准的交付方案中给出等价可追溯 fixture；不能一概排除 source-before 而让远端测试缺依赖，也无需复制整个 CPU/raw。此处只记录依赖，不更改或扩大 R105。

最终复核须补：R105四路径实际delta与六路径保护、import/formatter前后原件及delta proof、真实 Ruff/format退出、唯一GREEN完整JUnit/stdout/stderr/argv及32+原OC1实际分母、最终十源双向匹配、原R100/R101/R103要求逐项证据。须重新核对实际NEW_COMMIT与legacy纯回放，包括真正factory及event仓储实现绑定；不能从预审限定片段单独得出全Memory/SQLite运行闭包。

P5软件、P6、R91实际九组、全T12正常正链、formal分别记录。旧真实calls/已结束P4prefix不计当前live资格。本预审冻结后不改字节，最终审查另写收据。
