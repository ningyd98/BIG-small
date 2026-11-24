# G1 双标观察器的正式场景绑定补充计划

gpt-6.2-astra · 2026-11-24 · 研发祖先 `2da8a704a0ee249ea060aed681728e429fea5815`。本轮只修复独立 G1 正式槽身份传入双标观察器及离线读回时缺失的问题，完成后继续执行[原四对计划](../round-g1-formal-paired-20261124/plan.md)。[原始输入、SHA256 与判据](plan.json)

历史 d01 的非研究身份回归中，原单标到第 824 步停，保存了 94 帧。双标在第 120 步的 bootstrap 以 `registered_scene_mismatch` 停止，仅保存 3 帧；原 d01 双标在第 1120 步接近时触发硬安全停，共 133 帧。核对到 `g1_dual_observer.measure_frame` 将每个真实帧的场景直接与静态资产的 `S01_NORMAL_STATIC` 比较；新槽已在实际 reset 与 RGB-D 正确使用分配场景。失配回归两个槽共 127 件原始文件均按清单重新验算，日志与清单摘要相符。正式消费为零。

## 修改与复验

1. 保持原独立 G1 正式计划的四个坐标/种子、八个身份、AB/BA、额度、零重试、控制/摄像/评分及输出根。到本计划编制时正式输出根未创建，正式 claim/运行均为 0。仅使用其他路径下同一历史 d01 摆放做验证。
2. 在新的独立 formal runtime 中，给双标测量接入经校验 allocation 确定的期望 scene。可以使用严格作用域的 ContextVar/contextmanager，其进入值来自当前已核对的发行及槽 allocation；finally 恢复 token；或等效的显式参数透传。覆盖 derive、servo_measure、matches_current_owner 所走的同一 measure_frame 路径。旧开发调用没有该上下文时仍严格匹配 S01_NORMAL_STATIC；具有绑定时只允许该槽精确值。空、错槽、旧场景、上下文外泄或空 episode 必须按原门拒绝。不得从正在检查的帧、scene 前缀或其他自报信息推断期望值。
3. 离线评分先以独立登记槽、claim/alloc SHA、复位与帧索引、episode、truth 交叉校验，匿名 bundle 的 expected scene 必须来自核验过的登记值并封入 index digest。新鲜盲读进程按该 bundle 的期待值向同一观察器显式传参，并逐帧比对场景及 episode；不得以帧自身或单独未核验的索引自证。开发用历史 bundle 即使未带新增字段仍按其原调用约定校验，缺失的正式绑定应拒绝。包内不带 offline truth、运行结局或臂的成功标签。
4. 衍生源代仅容许 observer 中的 expected scene 选择与上下文管理、formal capture 的槽上下文、formal runtime 锁/元数据约束及 formal scorer、pixel readback 和必要的打包传递。身份来源可另设小模块并封入完整新代来源；避免修改资产 provider、社区库、控制器、检测或安全数值。两臂所有有效源码以文件枚举绑定 parent 的旧 SHA、允许变更的确切路径及新 SHA；登记前存放隔离差分和校验回执。历史第四代 553 个源、482/483 两臂原清单及父计划输入 SHA 保持可复核；涉及原计划已锁的工作树文件时，应在衍生副本修改或分别核对历史已归档原字节和显式批准的当前指纹。拒绝忽略全表、任意变更或通过改旧原件更新输入哈希。
5. 在生成新 effective geometry 时只为双标精确重算 development_dual.development_sources_sha256 中本次实际改变且原清单涵盖的 observer 文件条目，以及 development_dual.development_source_generation 的规范摘要。若采用单独新上下文模块，将其列入运行源清单，不随意扩展 geometry 原清单。加载器、登记、双盲读与捕获都要验证 recompute 后的新 geometry；与历史 descriptor 的其他字段逐叶相等，包括原 schema/authority、名义注册 scene_id、相机标定、标记哈希、质量、坐标、阈值。在线 per-slot scene 经过独立执行上下文进入观察器。原单标 descriptor 全字段相等。
6. 在非研究路径跑 RED/正负控：未扩展的原件示出 120 步处 scene mismatch；旧 S01 默认成功与拒绝异名、同一像素内容配当前授权测试场景有效、其他模拟正式槽/S01/空身份均失配。验证上下文撤销（含异常退出）、在线三调用路径一致、blind reader 拒绝篡改 packet/bundle/跨槽和新正式 bundle 缺绑定、两独立读回一致、伪造 geometry 附加字段或源码哈希被拒绝。避免预看 f01–f04。软件验证及开发兼容性分别记录。
7. 用新私有目录和非研究的 fixture 身份对历史 d01 单标/双标以同样种子、重置及名义机位各实际运行一次，无正式 claim。对照原 d01：单标 94 帧/824 步，MOVE_ABOVE 视觉伺服拒绝；双标 133 帧/1120 步、APPROACH 硬安全停（夹指与载板），包括期望的动作、接触、覆盖、步数与像素盲读，同一观察器在新身份下有有效图像。原数据中时戳/运行唯一身份可变化；在确定性条件相同的有效载荷/数值上核验，不以全文件相等比较新生成时间戳。两个独立盲读进程实际读取这些非研究图像，逐帧验证临时场景并复算，存命令/退出码；意外差异保留后按根因重新计划。
8. 监督器从已验证的 receipt、完整 seal、真实 reset/worker/命令/终态与槽身份判预期停止。正常视觉/控制/硬安全拒绝计真实失败，保留原始分类并继续下槽。历史 d04 的 tracking.py::_acquire_initial_geometry、BOOTSTRAP、ValueError、initial RGB-D identity/extent unavailable: top_support_height_span_unresolved 属本设计可观测的视觉拒绝；不要凭 SOFTWARE_ADAPTATION_OR_OPERATION_ERROR 或宽泛异常名统一判继续。registered_scene_mismatch、跨身份、来源/库存错误、未识别软件异常或审计失败须封存已耗槽并停止未耗槽。按真实 d04 正例和 d01 失配反例及损坏/未知报错负控测试分类。首个正式 claim 前执行父计划规定的 Git 交付，登入父/补充计划双摘要和新的完整冻结源，不再询问四对授权。
