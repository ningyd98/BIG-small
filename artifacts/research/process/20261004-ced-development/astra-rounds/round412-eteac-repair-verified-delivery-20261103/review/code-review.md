# R412 最终独立代码、证据与精选交付审查

结论：**可按 R412 执行精选软件研发交付**。Critical 0、Important 0；1 项既有 lint 债务作为 Minor 延期。此结论针对冻结 core，不表示提交、推送或正式研究验收已经完成。

- 审查者：独立 fresh `gpt-6-astra`；未实施修复，未派生其他审查员。
- Base / 当前 HEAD：`ac6351b66a6dd05fb67aadd59935ce5726748709`；分支 `research/20261004-continuation`；读取时 index 为空。
- Core manifest SHA256：`4bdd426f8c1695dd35e54d252f901788e480bc2d97b5bbf566d1759691f97346`。
- **388 个唯一普通文件，5,210,029 bytes**：逐项重算 bytes、SHA256、mode 均匹配；恰为 375 个原 allowlist 条目加 13 个明确新 core 路径。
- 当前 1220 项源 pin 全部匹配。四个交付源码的完整 pin 见同目录 JSON `current_source_pins`。

## Strengths / 审查依据

SQLite 修改保持最小边界：六个私有 reader 的函数体与原公共 reader AST 完全相同；其余 11 个既有方法在反向替换指定读取调用后 AST 完全相同。新增 recovery-list helper 保持原 SQL 和顺序，仅改走私有 recovery reader。普通 Lock、事务、BEGIN IMMEDIATE、真实写权限 guard、CAS、回滚和拷贝语义没有改变；公共读入口仍经过原装饰路由。已持锁的 legacy 路径避免再次进入 `protocol.py:215`，没有放宽外部写入口。

`operational_windows.py:789` 和 `:831` 只将合法默认 `UTC_LEGACY_VETO` 纳入已有 typed validator 分支。读取当前 owner 会先验证真实 owner/thread、worker/source、UTC lease 和 clock；后续 immutable descriptor、注册 window、原采集身份和 age 检查仍在。未知 mode 仍拒绝。新测试覆盖默认模式成功、伪造 source/window/observation、错误 kind、真实 UTC lease 撤销和未知 mode；原 foreign-thread 断言仍要求外线程 UNKNOWN、原线程 VALID。

原始锁 RED 的栈确实是 `protocol.py:215 → sqlite.py:976` 同线程重复取锁。19 份选定 JUnit 全部解析：4 项锁测试、272 项原仓储语义、220 项 visual 加 4 原 skip、4 项 worker 短测均与记录相符。R402 的真实 native MOCK receipt 表明 ETEAC 1.563512 秒完成，先已排队的 PCSC 仍处于 QUEUED/attempt0，然后 1.692480 秒完成；两者均 attempt1、attempt 已结束、lease 已释放、heartbeat/SQLite FD 列表为空。结果以真实 `experiment_id` 关联 job，保留结果自己的确定性 `run_id`。

R405 原始异常/UNKNOWN/transition 前置失败链与两处 mode 分支相符。R406 两次原失败分别发生在原前置和仅第一分支修好后可达的 observation=False；同一新 test SHA 跨两 RED 和三 GREEN 不变，GREEN 共20项。R409 两个原 writer 节点完整 setup/call/teardown 自然 PASS，141.598/140.934 秒，R235 前置已接受；源码中的全部 writer 库存、前后快照、negative cancellation 和原 profile/cleanup 保留。新 launcher 先保存真实 child-exit 与 raw terminal，再解析报告；没有将 R407 原 UNKNOWN 升级为通过。

浏览器两份新 XML 为默认39 PASS + 原E2E-06 SKIP、研究3 PASS。原R377 XML中19个 failure/error 身份与旧映射完全一致，且逐项唯一匹配新自然PASS。三个 TypeScript overlay 仅做计划允许的路径/环境变量替换，反向还原与冻结原件字节相同；原 backend 和19份 fixture、以及新副本共20项输入 SHA 全部核对通过。研究依然是600组/4200条BLOCKED、SOFTWARE_ONLY、NOT_RUN、formal=false；原测试明确比较页面与真实下载 JSON。RGBD 是 MuJoCo/EGL 图像仿真，不能表述为物理机器人验收。记录中的所属进程回收、四端口释放和无源码漂移与两次 terminal 相符。

独立读取 R410 冻结源，确认 SQLite/native-test 整模块 AST 前后相同；legacy-test 仅前三个标准库 import 顺序规范化后相同。R412 官方新工作树 hash 为 `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4`；读取了成功调用与 stdout，没有自行再跑产品 hash 函数。原 native `25b44519…` 和 browser `4b41e88f…` 仍各自指向原运行字节，不是格式后重跑证据。

R399 1959.506秒行政关闭超过原1800秒、旧 guard 未完成/ready=false/未交付的历史完整保留。R407缺 child终态、旧退出码未知及随后报告读取失败保持真实。R411将无time的原skip记录为 null/available=false，不伪造0秒或PASS。候选不含运行数据库、完整raw、截图/trace/export、复制fixture、冻结源码副本、权重、SDK、凭据文件或两个gitlink；有限常见secret格式扫描也无候选。精选报告不能替代完整远端raw复现包。

## Issues

### Critical (Must Fix)

无。

### Important (Should Fix)

无。

### Minor (Nice to Have)

**M1 — 既有40条 Ruff 告警保留。** 位置：`sqlite.py:126` 起的历史告警、`operational_windows.py` 的历史 import/长行告警，精确位置见 R410 `lint/after.stdout.json`。独立对照 HEAD 的规则编号与归一化逻辑行完全一致：SQLite27、operational13，共37 E501 + 3 I001；两新test无剩余告警。四文件 Ruff 仍 exit1。影响为既有可读性/格式债务，不是本次新增行为缺陷；建议单独范围处理，本次允许延期，不能宣称全 lint 通过。

## Declined to judge

- **D1 — Physical robot, paid/external model use, and formal research acceptance**：Outside this software-only delivery; no such execution evidence. MuJoCo/EGL RGBD is simulation, and the research fixture remains 600 groups/4200 BLOCKED, NOT_RUN, formal=false.
- **D2 — Full 4732-test suite and long T3 acceptance**：Not rerun in this approved scope. Focused repository, permission and browser evidence does not establish those wider outcomes.
- **D3 — Exact cause of R407 historical child termination**：The old child exit code was not persisted and the native stack is partial. The later plain-run passes and observed zero OOM counters do not resolve that historical cause.
- **D4 — Product performance improvement or general SLO compliance**：The two original permission nodes take approximately 141 seconds each. Split 240-second supervision enables unchanged assertions; it does not establish optimization or a new performance target.
- **D5 — Fresh behavior execution on final formatted source bytes**：No post-format native/browser/test rerun was authorized or performed. The exact AST/import bridge supports applicability while original execution hashes remain historical.
- **D6 — Complete remote raw reproduction and excluded local evidence portability**：The candidate intentionally excludes full raw, DB/WAL/SHM, screenshots, traces, exports, duplicate fixtures and frozen source copies. Selected manifests/reports do not constitute that package.
- **D7 — Commit/push success, three-SHA equality, and nested dirty gitlink interiors**：Git delivery is still a subsequent executor action. Review only checked outer entries/HEAD/branch/empty index and did not enter either protected nested checkout.

## Metadata append policy / 交付条件

明确接受 `metadata_append_policy_accepted=true`：冻结后只允许把 core manifest 自身和本审查员这两份报告加入最终 entries。最终 manifest 必须恰为388个core + 3个metadata = **391 entries**；它不列自身hash，而由独立hash校验并精确staging，合计**392条路径**。没有任何其他 helper、回执、补写总结或实质内容可进入此授权集合。任何core/source字节变化使本审查失效。此确定性策略避免自指循环，无需再次fresh审查相同内容。

执行者仍须逐项裁定 M1/D1-D7，重核所有冻结 hash 与受保护外层状态，验证 staged/committed blobs 和精确成员，按计划普通提交推送，并核对本地HEAD、上游和实时远端三SHA。两dirty gitlink只核对了外层条目，未进入内部，不声称重新审计其内部dirty字节。Git最终回执留本地，不能提前宣称交付完成。

## Assessment

**Ready for delivery: Yes，限已批准精选软件研发范围。** 两产品修复、原断言与真实运行证据相互吻合，没有发现Critical/Important问题；历史失败、格式桥与未执行边界均诚实保留。

审查采用只读Git、标准库AST/SHA/JSON/XML及关键源码/日志精读；所有core字节已哈希核验，没有逐字重复阅读所有大型pin JSON。未运行pytest、产品导入、SQL、网络、Git写操作或行为测试；只新建本目录两份审查报告。
