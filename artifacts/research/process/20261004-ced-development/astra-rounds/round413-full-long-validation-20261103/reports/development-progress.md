# R413 全量长测后的研发进展

本轮完成一次全量诊断执行，整体尚未达到全部通过或正式研究封板条件。ETEAC不结束问题已有当前代码的原生MOCK队列回归证据；新暴露的测试接口不一致、租约交接、回执真实性和事件复现问题继续保留。

被测分支 `research/20261004-continuation`，代码提交 `ab18abd0f82a024b62f4423c946c6585f8d18c65`；官方 real_robot 源码指纹 `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4`。

运行区间：2026-11-03 18:11:58—2026-11-03 23:08:22（北京时间）；全流程墙钟 17783.674 秒（4.940 小时）。UTC 起止为 `2026-11-03T10:11:58.963126+00:00` / `2026-11-03T15:08:22.637110+00:00`。

## 当前可确认的研发交付

SQLite持锁内部读取路径修复后，ETEAC与排队PCSC都能自然结束。下列运行各attempt=1，租约释放，结束后心跳线程与运行DB句柄列表均为空。这是开发用原生MOCK证据；不能升级成实体机器人验收。

| 开发运行 | 终态 | 耗时/秒 | attempt |
| --- | --- | --- | --- |
| r399-native-eteac | SUCCEEDED | 1.475165 | 1 |
| r399-native-pcsc | SUCCEEDED | 1.610095 | 1 |

UTC默认模式已进入原typed validator，未知模式拒绝以及owner/thread/source/clock约束继续保留。Memory与SQLite两项UTC长场景均通过，T3完整9项通过，之前5个失败目标在本轮全部执行并通过。关键闭环合计94项通过。

UTC性能仍未达标：Memory 2268.880秒，SQLite 2233.629秒，合计4502.509秒；原合计600秒门槛未满足。诊断每项7200秒额度不替代原性能门槛，也不代表生产请求延迟。

浏览器本轮42项通过、1项原有跳过，旧19项失败逐项恢复；研究页面/导出展示契约通过，仍明确为600组、4200项全部blocked、actual research NOT_RUN、formal=false。前端单测43项和构建通过，但API新增publication/confirmed_succeeded等发布确认字段尚未同步到仓库生成契约。

| 范围 | 本轮结果 | 含义 |
| --- | --- | --- |
| Python采集 | 4753唯一节点 / 288模块 / 0采集错误 | 比旧4732清单增加21项，未丢旧节点 |
| 软件节点 | 4709 PASS / 35 FAIL / 6 SKIP / 1 INCOMPLETE | 4751项均STARTED一次；不以未完成或skip冒充通过 |
| 真实数据节点 | 2 NOT_RUN_EXTERNAL_DATA | robomind / graspclutter6d实际数据未运行 |
| 关键闭环 | 94 PASS，另9项关键回归PASS | 9个T3长节点+85闭环节点；关键9项含native队列与模式兼容 |
| 浏览器 | 42 PASS / 1 原有SKIP | 旧19项全部PASS；cleanup=True |
| 前端开发 | Vitest43 PASS；app/node类型、ESLint、构建PASS | Prettier与API生成一致性检查FAIL |
| Phase12 full | 5580结果行；verifier=PHASE12_REJECTED | 登记行、raw声明、内层真实回执、正式验收分别统计 |

## 当前问题及优先次序

| 类别 | 失败数 | 证据解释 |
| --- | --- | --- |
| 测试替身接口不一致 | 21 | RuntimeSpy缺少_local_mode，21项在check_active处失败，目标capture/plan/supervision断言未得到有效验证。 |
| 回调签名不一致 | 1 | post安全门场景的recapture测试lambda不接受completion关键字，不能据此宣称实际安全门已验证。 |
| 租约交接并发/授权 | 5 | 3项嵌套public mutation授权拒绝、1项database is locked、1项跨进程Queue.Empty；产品与测试注入前置的根因尚待分离。 |
| 运行回执与验收契约 | 2 | F20计数应1实际0；另一项期望accepted实际evidence-gaps。内层BLOCKED_BY_ENV而外层宣称SUCCESS需要优先处理。 |
| 事件轨迹复现性 | 2 | 两项相同配置/seed的result_hash比较通过，事件摘要或payload_hash不一致；具体差异字段未通过额外重跑定位。 |
| 中文规范与覆盖 | 4 | 29+9+2个公共文档字符串缺口，及2330个tracked代码路径未纳入默认审计；这是被测ab18基线下的计数。 |

1. 先恢复21项RuntimeSpy接口与1项recapture回调的真实测试前置，保留现有source/lease/clock拒绝规则，使目标位置得到验证。租约组5项需要单独分清并发实现与测试注入契约，不能直接放宽授权或替换锁使检查通过。
2. 修正Phase11适配器的输入模式与内层终态传播。已保留的新鲜回执显示：draft省略input_mode而默认走RGBD，MOCK报RGBD_CAMERA_REQUIRED，main/recovery/duplicate均BLOCKED_BY_ENV；外层仍声称SUCCESS、runtime_completed及task_success。F20断言计数0而非1直接暴露该问题。必须先保证结果真实性，再解释成功率或论文样本。
3. 定位两项seed事件复现失败，以及UTC两后端合计4502.509秒的性能瓶颈。本轮没有追加重跑、profile或放宽阈值；具体复现差异字段与耗时根因尚未确证。
4. 处理静态与契约缺口：Ruff 1156条（42文件），format 139文件，Prettier 11文件，文档检查18条规则命中。Mypy本次因缺py.typed直接exit2，没有形成有效源码类型检查结果；不能称类型检查完成。文档敏感内容规则命中未经逐条证实，不直接等同泄露。

## 全量实验与正式研究边界

Phase12 full固定矩阵预期5580行，本轮落盘5580行。raw声明adapter_attempt=5580、runtime_invocation=4860、runtime_completion=4860、BLOCKED_BY_ENV=720；这些字段不等于成功任务数。内层回执审计中Phase11不支持外层完成声明的行数为900，其中F20为180。最终verifier `PHASE12_REJECTED`，门控后的论文权威行数为0。详见测试报告及phase12-audit.json，不能使用raw SUCCESS数量替代正式验收。

本轮未完成真实外部数据、真实模型/Isaac/ROS/实体控制器及正式CED资格、校准、B0/INITIAL/METHOD/FINAL验收。云端沿用用户选定方案，边缘模型选型后置，端侧OpenCV及可见姿态标记、顶视相机、控制器方案均保持。

## 来源、历史与交付

R414在工作台7项首次启动前移除共享SIMDB覆盖，同序7PASS；R415修正新续跑器嵌套资源目录准备，只接续可信从未STARTED节点。原075的2项失败和1项未完成保留，原073/076两个管理阻断均为零行为，不加入测试分母。产品与测试字节未改，旧raw、partial目录、两个dirty gitlinks保留；不称整个工作区干净。

旧R407采样子进程精确退出原因仍UNKNOWN，本轮不能反推其原因。原生回执沿用的patched_worktree=true等历史标签不改写，当前来源以实际HEAD与源pin为准。docs/current_authoritative_status.md仍是11月2日快照，其ETEAC/旧19浏览器待办不能替代本轮结果。

这份报告对应被测ab18代码。后续交付提交仅新增精选证据与报告；新增tracked路径会影响治理审计输入，未宣称对交付提交重新执行整套长测。完整raw、运行DB、缓存、凭据、模型、SDK及大图像/trace留在本地；精选清单不等于完整远端复现包。最终review与Git三处SHA回执在本轮review/delivery目录另存。

配套：[测试报告](test-report.md)、[唯一覆盖总账](coverage-ledger.json)、[Python失败分类](python-outcomes.json)、[全量实验审计](phase12-audit.json)、[来源与清理核验](../postflight/checks.json)。
