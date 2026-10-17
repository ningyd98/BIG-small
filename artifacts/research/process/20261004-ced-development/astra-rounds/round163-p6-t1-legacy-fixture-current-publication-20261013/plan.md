# R163：T1 legacy 夹具的 current publication 与预算哈希修复

> 实际规划者：gpt-6-astra（`/root/astra_status_plan`）。ROOT 审阅激活后由既定唯一 Sol 作者实施；本计划不执行产品。

**已独立确认的源级问题：** UNKNOWN route 真实写入下一 owner revision/generation 和扣费 pool，候选仍把初始化 publication 交给 supervision。现有 production 明确要求传入 publication 与事务 current 行 digest 相同。另一个同根因映射问题是 local budget 已替换 deadline_at，却仍沿用旧 legacy payload 的 content_hash。两者尚未运行，不是实际 pytest 失败。

**最小修改范围：** 只修追加测试的 `_b_legacy_sources`、`_b_local_cases` 及必要 `_b_` 辅助定义。保持七个 T1 测试函数正文/参数节点、原80556字节 A 前缀、runner、全部生产及保护源码。前后历史快照分开：保留 route 的原输入历史，读取真实 current publication/pool/checkpoint/retry供后续 supervision，不伪造 CAS 或更新历史请求。local budget 的新哈希覆盖其新 schema/task/state/revision，旧预算 payload/hash 不改；具体公式及断言见 JSON。

**已核对但不应误报的问题：** lease.identity 与 role bundle 原始重冻绑定有现有 API/严格校验支撑，应保留。bootstrap record.state 实际是预算 dict，不是字符串。这个 repository route 对任何 captured_at > now 拒绝，TTL使用原 strict age > ordinary_ttl_s，不移植别层容差。废弃的可选定位器未返回内容不计覆盖；未新读的构造器细节不声称已验证。

R162实际18c147 exit0已核：原件、A前缀、15命令HELD0均连续。R164已激活并放弃可选定位，零替代读取。本轮十九个真实输入 pins、逐条事实/修复步骤和完整预算边界见 plan.json。

## 实施与检查

- [ ] ROOT核输入和本计划；作者先保存原 test 与四份 R162准备报告精确 before 原件。
- [ ] 修正 current与historical snapshot取用及新预算内容哈希；不删除断言、跳过 legacy control 或宽化拒绝类型。
- [ ] 保存局部 diff、前后 hashes及修正后 fixture-map/报告；状态仍是 source-only pending ROOT gate。
- [ ] ROOT全文复核测试/runner/fixture和字节范围，之后才按原 R158门执行原 baseline/RED。六个missing-contract失败和legacyPASS预期不变。

无新增 pytest/static/probe/Git额度，旧额度不重置。原测试 API/夹具失败不可冒称批准的 RED。

## baseline 独立性

原 mypy_baseline 只检查22个生产文件，不执行这个夹具，因此可独立安排，但须 ROOT单独baseline-only gate核真实runner、22源pins、精确argv/env/cwd、原未用额度与新证据目录，只释放这一条。不得把未完成测试门标为通过；若实际runner无法在不修改/绕过门的情况下分离，则保留原完整testgate顺序。只有唯一作者通过原runner运行；实际 numeric0/1与诊断原件分别记录。任何消费后账本变化按真实结果保存，不再沿用旧0，不刷新预算。

验收仅限定测试准备可审查。T1/B9/runtime仍须原实际验证与独审；native、实际、formal、full T12和Git均未验收。新原因或异常立即停并先交下一Astra计划。
