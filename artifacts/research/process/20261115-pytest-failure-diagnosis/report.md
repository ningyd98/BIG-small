# 继续失败定位与独立验证

本轮接续 `7c326c1d141f81723042bfcb9e1471bc31d4c7a8`，分别处理软件验证失败和原 V3 的 13 个失败病例。原研究结论仍是 27/40；原 held-out 已参与修复诊断，其 8/15 不作未见场景泛化证据。没有启动付费 Sol/Molmo 或新 seed 的模型端到端实验，也没有修改控制器轨迹、MSAA 和安全阈值。

原 9 个几何失败全部由原判据复算得到相同拒绝：4 例是颜色连通区域中 1–9 个无效深度像素；5 例是 2–3 个边界像素位于顶面前方。逐像素依据见 [冻结数据复核](frozen-failure-diagnosis.md)。补充的 [独立射线诊断](frozen-ray-diagnosis.md) 在匹配原物理状态和相机标定后查询 33 个异常像素，27 个内部对照的最近几何全部匹配、深度最大残差 3.096 mm。边缘仍存在解析交点与原深度/实例的差异：其中 4 例原实例标签虽为 link4，中心与子像素查询却未命中该几何，不能仅凭该标签认定机械臂遮挡。解析射线不等价于光栅化深度，MSAA 因果归因仍未证实，不能直接把边缘前移像素当作可忽略飞点。

另行执行的 4 个冻结控制器前缀全部精确复现失败，初始、动作前后及 safe_stop 后状态哈希和结束步数都匹配。3 例右指在 39 mm 指令下反馈达到 40.1015–40.1168 mm，越过原 40.1 mm 停止线；IK 病例在零动作期物理推进下复现原 UNREACHABLE。详见 [独立物理诊断](controller-prefix-diagnosis.md)。它使用原 resolved_step 作离线教师，没有重跑原契约、shield、规划和 worker，不计抓取成功率或新模型端到端验收。

软件失败按共同根因合并修复。生产可执行修改仅为规划 API 的四处缓存接口适配；机器人运动、几何判据及安全边界未修改：

|根因|修改及保留的检查|
|---|---|
|4 项公开 API 中文说明缺失|在 9 个源码文件补充 47 处中文文档；去除 docstring 后的可执行 AST 与输入 commit 相同，见 [哈希及 AST 对照](evidence/docstring-changes-final.json)|
|默认中文审计覆盖与冻结归档混在一起|新增 tools 和两份 Playwright 配置覆盖；为新增配置及工具元数据补说明。覆盖测试只排除冻结 artifacts/output，保留原字节和历史依赖，不删除日志或改写冻结文件|
|默认沙箱阻断 socketpair.send|独立探针确认 EPERM，导致 asyncio 回调无法唤醒。实际异步、ASGI、原生测试使用正常权限环境，没有以改应用逻辑绕过环境问题|
|工作树缺运行前置文件|恢复共享虚拟环境的忽略链接，按 SHA 精确补回两份历史 R569 原计划；未下载依赖或模型，原生产 CLI 的计划硬绑定保留，见 [工作树恢复记录](evidence/workspace-restoration.json)|
|旧测试依赖手工配置的证据环境变量|缺省时选用每测试独立 tmp_path，旧显式证据目录、独占写入、符号链接拒绝、资源观察和清理断言保留；legacy golden 缺省指向已提交的原 R166 文件并硬校验 SHA|
|工作树绝对路径、归档 tracker 接口漂移|先按声明输入清单的完整相对后缀唯一匹配旧路径；tracker 负例使用真实生成的当前 binding 后仍验证原 exact original pixel tracker 拒绝|
|标记注册冻结版本与已验证开发源码不匹配|新增 DEVELOPMENT_ONLY 的 v3 注册，仅更新开发标识及 pose_markers、observations 两个已检查源码哈希；v1/v2 原字节和旧来源拒绝测试都保留，不升级安全准入|
|API 测试遗留真实后台 dispatcher|最小 API 前置 + T2 组合复现 poll 调用 160 次而原断言要求 1 次。新增测试边界回收本项实际启动的 dispatcher，原启动、停止实现和单次轮询断言保留；生产 app 生命周期未修改|
|旧租约竞争注入穿过当前公开写事务|测试先确认嵌套公开写拒绝及回滚，再在事务外完成真实交接/心跳，以捕获的旧 CAS 或只读旧快照验证 SQL 拒绝。跨进程锁测试先完成子进程数据库初始化，再进入原锁竞争；生产事务和调用者限制未放宽|
|HF 冷导入测试把 Client 类替换成函数|三项冷启动独立失败，真实 HF 的运行时类型注解因此抛 TypeError。落地的测试类保留原 Client 初始化、流读取、钩子和重定向，只注入 MockTransport；请求、TLS、取消、字节、凭据断言保留，生产异常脱敏不改，见 [诊断证据](evidence/hf-cold-import-diagnosis.json)|
|AUTO 事件摘要直接比较随机事务身份|两个相同 seed 配对分别生成 34/38 条事件，仅三条模式切换的随机 entity_id 及相应 payload_hash 不同，结果摘要相同。共享测试摘要对三类事务作每 run 一对一别名，保留事件关联、不同身份区分和全部行为字段；Phase8 逐条重算原事件 hash，Phase8.1 沿用原 lifecycle 排除边界，新增拆链、合并身份、时间、模式及其他实体 ID 负控。生产 UUID 和 raw 不改，不称为原字节一致，见 [首次诊断](evidence/phase81-identity-diagnosis.json) 和 [补充诊断](evidence/late-software-diagnosis.json)|
|规划 API 仍按旧 tuple 解包新缓存记录|GET、dispatch、监督直接查找和 task ID 遍历共四处改读现有记录的 response。保留原查找顺序、监督回退和 404/409/501；没有改缓存准入、gateway 或 shield。完整监督闭环同时覆盖 request/task ID，拒绝路径均无真实 gateway；见 [原始失败与候选对照](evidence/late-software-diagnosis.json)|
|Phase11 旧测试把默认 Mock/RGBD 阻塞当作完成|原 F20 的 90 份回执均正确拒绝 RGBD_CAMERA_REQUIRED，执行器未运行。测试现验证阻塞及真实 DB/lease/attempt/recovery/hash，保留既有显式 legacy 软件完成正控；同 run_id 重跑以测试独占新 DB 的已提交哨兵验证实际重建。生产 adapter 和输入模式均未改，见 [91 份原始回执索引及摘要](evidence/late-software-diagnosis.json)|
|冻结协议原件有绝对命名空间约束|工作树副本的字节/原硬 hash 相同，路径仍应被拒绝。测试先验原硬 hash 并断言副本无输出拒绝，再从已绑定 header 解析现有原始目录作正控；consumed、PROVEN、source-drift 拒绝保留。仅原外部夹具缺失时显式 skip，冻结字节和生产规则未改，见 [路径诊断](evidence/late-software-diagnosis.json)|

全仓基线首次正常权限运行因已收集到足够共同根因而中断：中断后 JUnit 汇总为 1994 passed、97 failed、71 error、21 skipped，后续未执行部分不计通过。该次没有完整逐阶段回执，计数仅用于基线定位。首次修复后的分片逐阶段回执实际得到 3534 passed、27 skipped、3 failed、3386 unfinished；后 3 个失败揭示后台线程遗留和旧租约测试注入问题，保留了 [该轮原结果](evidence/phase1-shards.json)。中断时 JUnit 可能为仅完成 setup 的节点留下没有 failure 的 testcase；本轮核对脚本以 setup/call/teardown 实际回执分类，未把这些条目计作通过。这些部分结果均不是全量通过。

最后一次批量验证固定为来源 A：6950 节点、1062 个来源文件，原四分片完整且不重叠。前三片接近 3600 秒外层上限时提前约 100 秒 SIGINT 保存回执；第四片完整结束。补充批次分别有 1200/600 秒上限；使用相同来源逐节点合并，重复执行不重复计数，任何失败不被另一轮通过抹去。实际得到 **5333 passed、27 skipped、7 failed、1583 unfinished**，各轮来源前后哈希均匹配；[核对结果](evidence/final-source-a-coverage.json) 保留全部未完成节点及失败名称，[原始日志索引](evidence/final-source-a-raw-index.json) 可定位对应退出码与 JUnit。7 项失败分别是 HF 冷导入、两个事件重复性测试、规划 API、两项 Phase11 旧预期和冻结协议路径。它们均在后续来源 B 中修改，不能把 B 的定向结果回填成 A 全仓通过。未完成节点包括两项完整 UTC 跳变观察器、部分 Phase12 长项和未到达的协议/注册测试。

落地后的来源 B 重新收集为 **6953 节点、1063 个来源文件**。**212 个不同测试节点全部通过**，含 174 项 API/规划安全/事件/租约/原生回执回归、37 项中文公开 API/审计回归，以及约 574 秒的完整 F20 默认批次；另有三项 HF 冷进程重复验证，总计 215 次节点执行。F20 的 90 份原生回执均为正确的 BLOCKED_BY_ENV、runtime_invoked=false、runtime_completed=false，测试通过不代表 RGBD 任务已执行。全部逐阶段回执、JUnit、退出码、准确节点及来源前后哈希已核对，见 [当前来源定向结果](evidence/current-source-targets.json) 和 [完整本地原始索引](evidence/current-source-raw-index.json)。临时 /tmp 候选结果不计入当前源码通过；B 未完整重跑全部 6953 节点，不能宣称全仓绿色。

完整资源和时钟观察器均保留。原 publication control 在第一轮完整观察器下通过，用时 472.258 秒；另两项确认故障控制各约 469 秒。移除 profile 的对照仅为性能诊断，不是验收。早期一个启用 faulthandler 的组合进程 exit 139，未取得原生回溯，不能归因于 codec、MSAA 或 faulthandler。仅该复杂证据缓存与观察开销问题调用一次真实 Astra 作只读分析，其 [原计划](../20261004-ced-development/astra-rounds/round-pytest-temporal-codec-performance-20261115/plan.md) 建议先保留全部观察器完成验证；本轮未实施 codec 优化。其余诊断、修改和执行由当前模型完成。

质量检查另计：完整默认中文审计 CLI 仍报告 412 个历史文件说明缺口并 exit 1，不能宣称所有质量门禁绿色。最终修改及新增 Python 范围的 Ruff 与输入 commit 比较，已有问题从 356 项降到 343 项，没有新增问题；新增诊断脚本及 fixture/helper 均无 Ruff 问题。代码及其他交付差异检查通过；保留的原始诊断 patch 中四行空白上下文标记使全暂存范围 diff --check exit 2，原字节未清理，见 [质量记录](evidence/final-quality.json)。未为清除历史说明缺口修改冻结资产或批量重写无关文件。当前模型的 [后续只读复核](evidence/static-review-late-delivery.json) 未发现阻塞；它不冒充 Astra，也不代替实际运行。

原 27/27 固定外部输出的完整 worker 结果仍归属于前轮 `8ebad9f6/7c326c1d` 的源码，当前新增 docstring 后 SHA 已变化，不能沿用为本轮当前源码验收。本轮逐像素复核及控制器前缀复现是独立证据；正式研究验收、付费新模型实验和新 seed 泛化的计数均没有增加。

完整日志、JUnit、逐物理步数据等留在忽略的 `raw-local/`，提交清单和派生摘要供审阅；运行数据库、凭据、权重、SDK 及完整批量原始实验不进入交付，也不把摘要称为完整远端复现包。本轮按明确路径作本地提交，公开推送仍遵守之前的暂缓决定。尚待另行验证的是全仓未完成覆盖，以及获准后的轨迹配对、渲染因果对照和新 seed 模型端到端泛化；这些均没有用本轮软件绿色替代。
