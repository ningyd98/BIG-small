# R368：UTC 成本测量裁决

实际模型：**gpt-6-astra**；agent：`/root/astra_r367_sha_review`；2026-10-25。只读审阅、写计划；不运行、改产品/历史账证或 commit/push。输入完整 SHA256、预算和步骤见 `plan.json`。**3600 秒 sizing 尚未授权，执行尚未就绪。**

## 四问裁决

1. **保留 `_sha`。** 31 例改前合同、31 例改后合同、26 个 codec 的 JUnit 节点顺序及 completion 引用 hash 已核对。它是有有限开发验证支持的小改动，不是所有语义的绝对证明，不是 UTC 修复；没有当前精确候选的 A/B 性能对照，不能再称已节约 20%。
2. **有条件 C → 再决定 A；不采用 B。** 建议一次完整 memory 节点 sizing，但须单独明确批准新预算，先补 runner 最小边界。测量可能仍只给未完成下界。原“两 backend 合计 600 秒”验收保持不变，既未通过，也不由 sizing 替代。
3. **`_object`/accessor 目前只开放静态设计。** 不允许直接去掉 copy、返回原 Mapping 或共享可变缓存。后续实现须另有单因、可区分方案，覆盖脱别名、严格 JSON 清洗、嵌套双向修改隔离、Mapping/子类、现行循环/深度失败行为及错误顺序。startup profile 不能充当 UTC 归因。
4. **同意独立可回滚交付，但需两个提交。** 当前 HEAD 尚无 `_copy`：先按明确路径提交已接受的 `_copy` 一行、其测试和必要证据；再提交 `_sha`、合同与必要证据。不能把整个产品一次提交称作 `_sha-only`。AGENTS 的持续交付指令支持后续已验证交付；本次只制定策略，不操作 Git。

## 证据边界

UTC 原始 failure（15186B，完整 SHA 见 JSON）报告 child −15、timeout、600.016 秒、group_empty；无 JUnit/case，resources/stdout/stderr 空。

`memory-1` 目录在 factory/poll 之前创建，同一 exercise 返回还包含 finally 清理。目录存在只能定位已进入该路径，不能证明 callback 未完成或整个 600 秒都花在 exercise 主体；更不能推出完整成本 2400–3600 秒、4–6 倍或按六场景线性外推。根因和完整耗时仍未知。

runner 只保留 HEAD 树/status/7 文件 hash，不含完整 dirty/untracked 内容和环境/seed/plugin 核验；after 仅比较未保存，缺 JUnit 时更早退出。它未执行原计划全部资源、输出、存储、capture、outer 上限，TERM5+KILLwait20 可超过 cleanup15；消费槽在正常结尾，异常不自动收口。prerequisite 有 PID 1142394，但缺 owned PID/PGID/起始身份/deadline 链，不能补齐清理证据。

保留三次实测通过和四槽 SPENT；UTC 手工收口原样保留，旧 R365 未运行槽的退役记录与原账本不改。没有实际泄漏/漂移/超限证据；不为补元数据重跑。

## 最小后续步骤（均未执行）

- [ ] 新建本轮有限 runner，沿用已验证的进程/采集方法，不改旧 runner、不重建祖先门禁。保留有效源码内容与环境/直接输入 before、after；文档 HEAD 变化不使源码证据失效。
- [ ] 启动前原子消费独立预算；记录实际进程身份与单调起点/deadline。finally 无条件进行有界清理、source-after、资源清单与结果收口；缺 JUnit 必须保留原始 timeout 和 missingness，不能跳过收口。
- [ ] 一次 runner-only 自检：60 秒/outer90，五个无产品导入、无 worker 的案例，覆盖缺 JUnit、TERM、强制 KILL、输出限额和预检拒绝。具体合同在 JSON；失败留证据、不自动重试。
- [ ] 明确批准 sizing 预算、静态审阅及自检通过后，才运行下面唯一真实节点；断言、产品和测试不变，无 profiler、额外对照或诊断。

```text
tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]
```

独立标签 `RESEARCH_SIZING_ONLY`，一次、无重试；**child3600 / outer3900 秒**，cleanup 总15 秒含 TERM5，capture240，outer kill-after20。并行命令1；最多3次 poll、并发峰值≤2、全命令构造 worker≤64。真实侧车核验不豁免。执行 JSON 列明的输出/存储/空闲空间界限，触限留原始失败，不截断使其通过。

## 验收、后续与回滚

完整测量要求精确1节点/1pass/0skip/0error/0failure、退出0，三场景 case/真实资源/完整源身份/进程清理证据齐全，分开报告 child 与清理采集耗时。只得到该机器与源码下的一次 memory 成本，不代表 sqlite、双 backend 或准入保证。超时只说明此 invocation 未在3600秒预算内完成；不得自动延长、重试或强行拟合总耗时。回交实际 Astra 决定下一步；不自动释放 A 实现或 B 正式 cap 更改。

提交前按 JSON 核对两个精确 staged blob，不覆盖工作树、不夹带文件；验证后推送并核对本地/上游/远端 SHA。研究验收与既有数据交付边界不变。

回滚只反向 `_sha`，保留 `_copy` 与全部账证；runner/sizing 失败不自动触发回滚。新失败/范围扩大交实际 Astra。
