# R406：默认 legacy 模式的引用检查兼容修复

实际 gpt-6-astra；UTC 2026-11-03T08:34:14.499828+00:00。R405 真实默认 factory 路径已确认 `_check_reference` 拒绝 UTC_LEGACY_VETO，转 UNKNOWN 后初次 capture 被拒；foreign thread 尚未创建。R405 原失败、观察、R235/source/cleanup 记录冻结，输入 SHA256 见 input-audit.json。

设计：仅 operational_windows.py 的 `_check_reference` 和 `_check_observation` 两处，将 foundation 分支条件扩为 `{UTC_LEGACY_VETO, OPERATIONAL_LEASE_FOUNDATION_V1}`。两模式已有相同非 local typed 描述；原纯 validator 只验证历史类型，后面的 owner/thread、不可变注册窗口、source、原 clock 与真实 UTC lease 仍必须全部通过。LOCAL 分支和未知模式拒绝原样保留，不改 factory/default 来规避问题。

新增一个小测试模块，复用真实默认 exercise/captured：正例覆盖引用与 observation（显式/隐式）；伪造 descriptor/observation 拒绝；真实临时 DB lease 撤销拒绝；仅负例短暂注入未知 startup mode 并 finally 恢复，两个入口仍拒绝。原 foreign-thread 节点不改，在 GREEN 自然执行 UNKNOWN/VALID 原断言。具体固定名称和边界见 plan.json。

顺序与配额：

1. 新测试冻结，产品未改时新正例 RED 一次≤60s，必须原 unsupported-mode/pretarget 错误，不接受 timeout/infra。
2. 首次 RED 清理后先只改 _check_reference 比较，冻结单比较 intermediate SHA；以同一冻结正例再作一次 observation_contract_red≤60s，必须真实 captured 已完成、reference VALID，随后 _check_observation 正断言失败。再清理后仅改第二比较，冻结最终 successor；两次中间/最终 AST 分别还原1/2处后须等于原 AST。
3. 新模块+原 foreign 节点 GREEN 一次≤180s。
4. 所列原窗口边界/owner/source/lease/重放节点一次≤180s。
5. 所列原 factory/lease/setup/source guards 一次≤180s。

每阶段15s owned cleanup，最多5次行为（两次有界同根因 RED、三次 GREEN）、总 child+cleanup 上界735s；阶段独立计时，无新的全链30分钟钟，不复用任何旧配额。采用新 R406 adapter 派生 R405 supervisor、全新目录、原 R235/R373/env/marker，普通阶段无需观察插件。产品/测试只在无活动阶段时写；阶段内源冻结。静态预检即可，无 helper smoke 或重复 helper 独审。

所有 GREEN 自然通过及新负例有效后，下一次 whole-change 独审合并 R405 因果与本轮改动。新失败须下一实际 Astra 计划，禁止现场放宽保护。旧 repo/worker/native 证据保留其原源适用范围，不能伪称旧 native 在改变后的完整源上重跑。慢 writer 性能、浏览器及最终精选 Git 交付均后续具体计划；本轮不运行它们，不触碰 dirty gitlinks/旧 raw/旧DB。
