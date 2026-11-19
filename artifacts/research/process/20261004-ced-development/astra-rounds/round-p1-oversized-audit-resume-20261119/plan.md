# 实槽 11 的独立大结果读回与 12–22 唯一续行

## 实测与原规则

- 11 仅一次 BEGIN/END，原进程/包装/native 为 2/2/0，包装状态 INCOMPLETE_UNKNOWN，signal/stop_reason 为空；其未发布 episode/evidence 成功摘要。冻结 4bdb64eb 的读者对 result.json 使用 8 MiB；这份原件 8,606,790 字节，超 218,182，SHA cbdcbf9e…b745。Sol 初读 3,524 个索引成员、55 源、9 个动作及独立安全与物理、一次 SQLite 终态，记录于已绑定诊断。12 尚未 BEGIN。
- 原 _contained_stops 对成功要求三个退出均 0；audit_originals 还要求包装 episode/evidence 所有权回执。completed_row 取已审计原组件/物理值；score_outcomes 只在20例全部 AUDITED、已关闭时给原方案 Wilson。11 不符合既有包装成功判据。

## 限定工作

- 独立、只读的结果与续行工具放研究轮中，保留旧 fail/success 回执、frozen runner 与 freeze_at 的源码检查。只针对原登记 slot 的 manifest-bound result.json，沿原 root fd/_artifact/O_NOFOLLOW 正则文件规则，拒绝绝对/穿越/链接/重复路径、错误类型和保留字段。先验证受限 manifest、所有成员长度与流式 SHA、原源/所有权和终态。读取 result 时用同一文件句柄或重验大小/哈希避免两遍竞态，先有限再解析；沿原 strict_json 的 UTF8/重复键/非有限字面值拒绝及 EpisodeExpectation、_episode_result 语义，独立完整复算姿态、参数、55源、模型与 costs、SQLite 真实 lease/attempt、commands/帧、安全/物理和动作数。既有 manifest/assignment/source 等 8 MiB 边界保持；为 result 单独在读取前冻结明确有限上限（例如 16 MiB 可覆盖本例，适用范围 8 MiB < 实长 ≤上限），检查生产结构和模型/动作/试次预算。遇其他原因、越界、异常类型、哈希/ownership 不符则拒绝。
- 分层发布三项事实：原包装 INCOMPLETE_UNKNOWN/2（native 0）、预登记的旧 strict audit/评分状态、独立补充审计（组件结局与独立物理各自判，计费与令牌按原件）。用另名且独立的证据 SHA/清单；不把 wrapper 缺失的 summary 伪造为 success，旧指标维持原 scorer 且如 20 未全 AUDITED 则不报其 Wilson。若另报固定 20 分母下保守比例/独立物理比例与区间，明确派生定义、各分子分母及原口径，重复两例单列。
- 恢复入口以已签原 freeze、allocation、部署/wheel/角色/旧 owner runner、正常 launch_slot 和原排序作为唯一发起链，持同一个 exclusive_owner 的锁，锁内重读所有已开始/已完成状态。禁止修改原 runner/其哈希、旧 owner、槽配置/seed 或派发参数。先验 1–10 原 audit、11 的唯一 begin/end/unresolved 及补充读回。在包装退 2/native 0、signal/stop 为空、唯一失败已准确定位在 result 上限、原件完整且补充审计无未知安全/归属异常时，才认定该槽可结案续行。此结案只影响是否可继续下一个未开始槽，不将旧包装失败改记成功。在同一锁/同一已冻 launch_slot/原 BEGIN+无覆盖规则下逐个派发12–22；同根因未来槽须对该槽重新用完整清单/规则独立复算，不能按文件大小直接容错。BEGIN 无 END、签名/未知异常、源变化或原件无完整结局须停相关波次。恢复/并发调用都不能重新发已有 BEGIN。

## 执行前置

- 先对原11实施上述只读即席诊断，签绑定原未解回执、manifest、begin/end、stdout 和核验源码；把独立读回与 owner 续行控制的正负对照跑在隔离复制件（错 source、错 sha/size、跨槽、未识别退出、已 BEGIN、并发/断点）。确保 11 没有产生新的真实调用。读回及核验完即在原授权下继续，现行付费权限和资源门沿用。

## 验收

- 11 保留原 2/2/0 与独立真实9动作和物理结果证据；一次开始归属可核，没启动的槽才继续。最终报告并列旧预注册指标、补充读回和保守统计，列出所有真实失败、未知、成本；严格 Wilson 是否可给由原 scorer 决定。保存新源码/回执摘要与所有实际 BEGIN/END，不向历史 freeze 写 SHA 替换。
