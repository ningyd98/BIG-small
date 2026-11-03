# R408：浏览器工作流复测

实际 gpt-6-astra；UTC 2026-11-03T08:45:36.631201+00:00。执行须等 R407 两 backend 原节点均终态 PASS、source/cleanup 门完整，再冻结最终 applicability receipt；规划不读取增长日志。当前源码基线为 ac6351b 研发分支上的已修工作树，以 current-source-index.json 实际 SHA 固定。

一次默认40项（console37 + RGBD3，保留 E2E06 skip），一次独立 research3项。旧 R377 20P/17error/2failure/1skip 的19未通过逐项比较，不假定都是同一锁根因。产品、测试、模式、registry、version、断言与内部等待不改。

新目录中派生旧验证 overlay，只替换 stage变量和路径；research spec 只改输出路径变量，backend原字节复制，20份fixture按原hash复制并前后核验。默认45s、research60s用例限额与30s服务ready、workers1/retries0/reuseExistingfalse原样。不要误将research改成45s。配置、DB、导出、截图、tmp/cache全部指向新stage，不直接运行旧config。

使用缓存Node22.23.3/venv/Chromium/node_modules，不安装更新。先只读查端口/依赖；根据已冻结旧sandbox拒绝，专用require_escalated工具审批后才作≤30s本地bind检查及运行。审批未通过或端口占用即停，不杀他人、不改sandbox flags。仅localHTTP/WS；Isaacdisabled/realmotionfalse，无付费模型/物理动作。RGBD是真MuJoCo/EGL图像仿真，与MOCK和research软件fixture分开报告。

复用实际R377 subreaper/owned-process监督器，新文件移除旧总钟，默认cap600s、research300s，各30s清理，独立阶段无全链30分钟限额；所有进程回收、端口释放后才下一套。default断言失败但源/清理干净时，独立research仍可完成；受影响修复暂停至下一Astra，禁止复跑。

执行期一次官方 current_source_tree_hash（≤30s）登记真实工作树，HEAD仅登记提交来源，不冒称包含未提交修复；原phase10示例e2e-tree仍是fixture，不作为真实来源。保存40+3完整JUnit、旧19映射、原失败、新日志/trace/errorcontext、源快照和清理。research仍须600/4200BLOCKED/NOT_RUN/formalfalse/真实export一致。

失败如实保留并下一计划，不放宽等待/断言/并发。后续一次fresh whole-change独审与具体精选Git交付计划，不在本轮运行Git；完整raw/DB/fixture/trace/大量截图仍local-only。
