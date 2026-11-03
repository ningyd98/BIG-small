# R413 全量软件长测与研发报告计划

> **For agentic workers:** 使用 superpowers:executing-plans，由既定主执行者原生执行；本文件为实际 gpt-6-astra 静态规划，不表示测试已通过。

**Goal:** 按用户“执行一次全量长测，输出研发进展和测试报告”的新授权，验证当前已交付源码并诚实交付结果。

**Architecture:** 新采集的唯一节点账本驱动分段 owned 子进程；长节点隔离，独立失败后继续，原始状态先保存。只生成新轮执行与报告产物，不修产品或测试。

**Tech Stack:** 已缓存 Python/.venv、pytest、Node 22.23.3、TypeScript/Vitest/Playwright、MuJoCo/EGL。

**Spec:** 本次用户授权、根 AGENTS.md、同目录 plan.json（精确 pins/argv/caps/路径策略）。

## 适用性与输入

HEAD `ab18abd0f82a024b62f4423c946c6585f8d18c65`；分支 `research/20261004-continuation`。官方 source tree hash `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4`。父执行者已完成唯一 collect：4753 nodes / 288 modules / 0 collection errors；4751 软件节点，2 个真实 RGB-D 数据节点单列。不是旧4732清单，也不是旧预算续时。normalized Git-Z audit 与官方算法不混用。

历史依据：UTC 双后端约4711秒，writer每后端约140秒；R373大组截断曾遗漏尾部，R399行政1800秒已关闭，R407 child code UNKNOWN原样保留。全部关键输入 SHA256 见 plan.json inputs。

## Global Constraints

只写本轮允许产物和新独占外置tmp；不修改源码、测试、断言、产品timeout/并发、registry、旧计划、原raw/DB；不进入两个dirty gitlink。依赖仅缓存，不安装下载；不付费模型、不真实机器人/ROS/Isaac运行。软件/图像仿真/native/正式研究分别报告。失败是一轮全测的观察结果，不触发自动修复或重跑。

## Review Focus

重点核对唯一覆盖与未启动尾部、R235初始hooks与资源输入、退出码先于可选报告、源码/fixture来源、外部BLOCKED及skip不被升级。无需为每个行政helper另设审查链。

## 可执行顺序

- [ ] **1. 前置和分配。** 复核 plan.json pins/HEAD/branch，复用已经完成的本轮collect，不重跑。生成显式source pinset与一对一assignment；记录2外部数据NOT_RUN。核对venv/Node/cache/磁盘与本地端口，不导入旧DB；建立每stage新resource/modelDB/simDB路径以及root外basetemp。子进程白名单环境、R223两resource路径、R235 plugin及R381精确legacy goldens按JSON配置；相关operational helper模块也使用同一资源前置，不遗漏R235可导入路径。
- [ ] **2. 冻结本轮执行器。** 派生已验证exit-first owned supervisor与R408 browser adapter，替换旧round gate为本轮pins。统一schema；静态检查无source写入/危险CI restore-clean/可选报告抢占退出结果。raw-exit先写，finally保存cleanup/source；父20秒资源采样，不加profile/trace/faulthandler。所有stage新目录，原始文件排他创建。
- [ ] **3. 全量Python。** 94个closure节点各一次新进程；UTC2个每个7200秒，其他T3 7个每个3600秒，其余closure600秒。其余4657节点分286模块正常一次，每模块1800秒，无-x/maxfail。module异常后只有STARTED从未出现的尾部允许一次独立600秒；已开始无终态记INTERRUPTED/UNKNOWN，不重跑。参数化完整列入；保留所有setup/call/teardown和JUnit。每进程cleanup最多30秒，前15秒TERM后15秒KILL，仅owned树。
- [ ] **4. 静态与前端。** 按JSON分开的argv各一次；ruff明确研发Python路径，mypy包范围；不扫历史artifacts/gitlink。typecheck buildinfo、Vite dist、OpenAPI导出/生成/格式化全部在stage，比较当前两生成原件；不直接api:check、prepare-e2e-tests或广泛CI脚本。静态债务原样报告，不修40既有lint或新增失败。
- [ ] **5. 浏览器。** 从R408 overlay只替换输出路径；default40与research3各一次，workers1/retries0、原等待与模式不变，600/300秒、cleanup30秒。20research输入按hash新复制、不复制旧DB。专用本地require_escalated上下文，服务不reuse、不杀别人。逐case class+name比较旧19；skip缺time=null。没有一次失败后的重试预算。
- [ ] **6. Phase12 full软件矩阵。** 复核固定adapter及无外部runtime前置后 run full 14400秒；fresh output后analyze/export/verify各1800秒一次。原CLI的skip标记不是执行防护，必须保留真实环境BLOCKED，不能启用模型/Isaac/ROS或改adapter。上游缺权威产物则下游NOT_RUN_DEPENDENCY；不能填入旧raw。
- [ ] **7. 报告和交付。** coverage ledger总数恒等，汇总全部退出/失败/耗时/清理/缺口；形成研发进展及测试报告。当前报告可如实包含FAIL，不伪称全绿。一名fresh Astra审完整证据与精选manifest，随后精确一次stage/commit/push/exact remote核对，local/upstream/remote三SHA一致。仅本轮精选记录交付，大raw/DB保留本地。

## 时间预算与继续规则

不设置全链30分钟或单大pytest总门。最大值由真实assignment计算：Python初始cap合计 605400 秒；含所有异常尾部及cleanup的保守极端上界 3550710 秒；其他阶段上界储备36000秒。该上界不是预期耗时或产品SLO；通常只消耗实际数小时，执行者先公布initial/contingent两列。正常失败继续独立组；源码漂移、无法清理、意外外部动作才暂停受影响部分。未跑/缺失/被截断均不算通过，不临时涨cap。

## 自审与边界

已核对：新collect唯一性4753；外部数据2；Python分配闭合4751；UTC不受旧180秒/1800秒影响；R235无额外hook；root外tmp保留outside-root fixture语义；浏览器与OpenAPI不写源；Phase12不重跑pytest；真实退出先落盘；失败允许报告、修复需新计划。当前只生成计划，执行者已有授权，无需再次向用户要确认。
