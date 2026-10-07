# RW1 / P1b 独立代码与来源审查

审查者 `/root/sol_rw1_review`，实施作者 `/root/sol_t12_p1`。只读审查完整 RW1 增量与现有原件，未运行 pytest/Ruff/mypy/actual/network，未导入产品、派子代理或改产品/旧证据。

- Spec compliance：**REQUEST_CHANGES_RW1_SOFTWARE**。
- Code quality：**REQUEST_CHANGES_RW1_SOFTWARE**。
- P1b 格式与来源链：**PASS_SCOPED_FORMAT_AND_PROVENANCE**。
- RW1 软件整体：**尚不可验收，先交 Astra 规划两项发现**；不开放 RW2/3、恢复0002或任何 actual/正式门。

## 发现

**RW1-IR-01 / HIGH — 生命周期拒绝没有锁存失败。** `src/cloud_edge_robot_arm/research/protocol_generation.py:1014,1049,1119` 在失败记录的 try/`_current` 之前调用 `_require_live`。plan/allocation/process 身份拒绝在这些入口直接抛错，不进入 `:1003` 的 `_remember_failure`。静态反例：已有有效 BEGIN/END 且 D 未到截止的 owner，令 `plan["attempt"]=2`，`check` 在 `:1119→:907` 拒绝；恢复为1后不传 caller failure，`finish` 在 `:1133` 成功检查，`:1155` 可得到 `wall_pass=true`。观测到的来源断裂被恢复原值抹去。此处是代码控制流推导，没有运行新反例。

Round66 来源合同第6项要求 identity/event/read/injection/end 验证失败锁存并禁止后续成功。现有测试 `tests/test_protocol_generation_sources.py:1089–1095` 拒绝后直接传 `failure="CPU lifecycle refusal retained"`，不能证明 owner 自己已锁存，也没有恢复后终态反例。必须由 ROOT 先交 Astra，审查者没有修复。

**RW1-IR-02 / MEDIUM — 被拒绝的原始 D 值丢失。** producer `:917–924` 读取原始值后直接抛错；`_current :1101,1105` 仅在读数有效返回后写入 payload。现有 round68 CPU 原件证实 negative/bool 的 CHECK_FAILED 只含 failure/kind，缺实际 `-1/True`；missing_pair 原件含 `lower_ns=120` 但缺实际 upper `None`；rollback 同样缺被拒值。不能从失败原件复核值及括号位置。`_recovery_wall_evidence` 无法保留未传入的值。截止拒绝仍然 fail-closed，但未满足 Round66 保留全部 original partial observations 的证据合同。具体原件路径、完整哈希与记录见 JSON finding2。旧原件必须保留，修复先由 Astra 规划。

## 已核对的完整范围与证据

审查原始 producer `before/protocol_generation.py`（SHA `7038a6d2ff76ae14e83dc5f91028b912c2fd6e25fe1de78f14e6a21e00025d3f`）到当前的全部增量：私有 reader/lease/owner/registries、renderer context 创建及释放、BEGIN/END/check/finish、生产与 CPU 工厂及全部新增测试；既有函数只有 renderer_exclusive 发生行为增量，旧测试无语义修改。审查不是仅最终格式。

固定 deadline 是整数 `b−+60_000_000_000ns`，upper 等值拒绝，无 S/UTC 换算；原1800s/60s/byte/disk预算保持。原事件没有 episode_id，当前代码从精确 owned live backend 分别读取 episode/step/S，保留未改事件、原prefix/ordinal，END要求同步 same-step/same-S和恰一条新事件。未把 CPU seam 或历史平台报告冒充真实授权。上述正确分支不抵消发现1的失败锁存缺口。

两完整模块独立 `ast.parse(type_comments=True)` / `ast.dump(include_attributes=False)` 相等，没有归一化；tokenize 评论内容相等，完整函数参数/装饰器/类型注释/断言值相等。完整格式diff只有 producer新增1空行、tests新增2空行与同值长断言换行。

| 源 | 格式前 SHA256 | 当前/冻结后 SHA256 | 完整 AST SHA256 |
|---|---|---|---|
| producer | 07e12a8921cc41b2f0229235614f8a16ec3b4520bd266b0bc46bc198ecc09bd7 | cb63e18ef0d259077914ea0cc3beec414fb19c8cf1243ddd05e7588fb46775e2 | ac09145c9017207104ca0bf0d31d80232efd1d946a3b3e31f5a5f50332477bba |
| tests | a3ec1598ff056c371eafbc2071da66c3920e9fcb6deeaaddac9ace58ec02224b | 9e2ed58417e4497adf43e37128cf5e278a9a24e95d7d07fc5ed4ba2f1f4b9037 | 5b3f4b5b24d9c51e9c888358d2e30e9bf0e256428e2dd3dbcbfc171c62fd7872 |

当前源码与 source-after 字节完全匹配。47项 input-check-after 实际hash全部匹配，其中45项保护输入与预期一致，仅两源码为批准格式变化。Ruff format写入、check、format --check、pending_regression各原一次exit0，日志与收据匹配；原mypy exit0按 producer完整AST/typing/config等价继承，无重跑。

原 Round66 RED为82唯一失败/0error，历史GREEN为81pass/1fixturefail；Round68 GREEN为82唯一pass/0fail/error/skip，32deselected。当前AST的82参数节点与原JUnit按序完全相同。原82 JUnit SHA `aad48e84d1becf29786958d71cef2d9ccba8aa8a7387fda5f0bbbd225ac1d355`；新窄回归为19唯一pass/0fail/error/skip、95deselected，JUnit SHA `251087675944bea0dbb5a919741be64eedfa4e7fb7498460ea83ba42fdb29b06`。两组节点无交集，未把重复运行累加为独立分母。418份新回归本地CPU manifest 文件全部存在且hash匹配；此清单不是完整远端复现包。

Round68 fixture使用独立JSON深副本和immutable prefix bytes，首拒绝特定源ValueError、恢复fixture后同一已失败owner第二END拒绝；原 round66 source_not_dict 的0字节journal与缺terminal仍原样保留，没有补造。

## 验收边界

可接受 P1b 纯格式变更、原82/mypy的等价继承及新19窄回归的证据来源；**不可据此接受完整RW1软件**。两项新发现已报ROOT，下一修复前须 Astra。当前 `_run_physical`、teacher、alarm/receipt reader与v3未接入owner是明确RW2/3待办，未当成本轮缺陷或扩范围。未重跑作者测试，静态反例不是实际运行结果。

平台报告SHA `1f7dd09001b4b288a81ccdf44adb2682ffeecd8276c82ea59dc525c5888cf7f6`、真实事件接口receipt SHA `b8d2e3f0867952d5c5445c5b5a4f7e063a363684de9153942daad51ece922021`已核对；它们不证明当前真实平台生命周期、suspend/restart/hostpause或实际fault接线。actual/teacher/native/T12/G4、UTC/SI/正式研究仍未验收。OC2活跃四文件与ROOT阶段摘要未纳入静止声明。

JSON附全部观测hash、原节点/命令、来源检查和精确发现。`formal_accepted=false`，`g4_measured=false`。
