# 1803 的未返回动作证据与 1804 的一次性前置判定

冻结产品 5103e7f4，active freeze daf46bd16aa98ff60b1e27afe3f1623f596e42553adb4d87996efdf5e0e6cc21。1803 已启动且终止；父、包装、child 的退出码均 2。原 worker 只保存 ValueError，研究审计器因缺少 controller_return_step 抛 KeyError。两者必须各自保留。applied scene 与此次工作绑定，step-01 MOVE_ABOVE 从 PRE 允许到 finally 记录的起止均为 120，visual_servo 仍为 INITIALIZING，无 controller_result、返回步、接受的 joint_target、动作步进；原始命令只有同刻的 hold_current_joints 和 emergency_stop。component/physical 均失败，1 云、4 本地生成、1 加载，货币费用未知。原 study 失败回执与原件不可重写。

**第一步，只读解释与修正审计**。Sol 先核 plan.json 的 SHA。对已固定的索引内原件使用真实读取器、配置、角色、SQLite/worker 和物理重算。保留所有既有完整动作与已发命令区间的检查；只允许没有控制器返回的终止前缀在语义成立时以 null 报告返回步与返回结果。对这类证据严格核对单个最终未返回动作、同刻 start/end、无动作计数/普通 joint_target/控制或视觉样本、终端 worker 失败、PRE 与有界安全停止及独立物理结果。其他已执行动作或普通命令不得借此略过归属/连续性。单列已尝试动作 1 与真正执行 0，禁止把 hold/急停算普通关节命令。新派生回执另写路径，保留原 AUDIT_REJECTED 作为首次软件结果。允许修正研究审计器、启动器、相应研究负控与派生回执，禁止改产品、配置、原始模型/worker/动作字节，禁止重跑 1803。

**第二步，只对这个之前槽的专门证明**。从 freeze、索引、stage-02/post-cloud、step-01/reference、after、原已解析 target Pose 与注册 family 重建同一冻结生产 OpenCVServoFeedback 构造。经真实 detector 测量，原绑定帧抓取点差 30.881889 mm，大于 10 mm，参考帧差 31.129708 mm。两个标记均 OBSERVED。以参考帧捕获时刻至 after 捕获时刻的 0–30.199 ms 为原始化时间界；仅在隔离的只读历史复算内以该两端时刻供给原 freshness 检查。两端都经原有效性/标定检查而在 servo.py:183 抛出相同身份不一致 ValueError。并非原 worker exception message/trace。存储并从 pin 重新核验原三帧、同一 episode/标定/时间/几何、费用/资源及上述结论，保持原异常类和任务失败。不能据此批准其他 ValueError、无法匹配的帧或没有这种原件的未返回动作。

**1804 切实可继续的条件**。只有在 1801、1802 已过原门、1803 的 active freeze+预登记 seed/id+exact native manifest SHA+job/episode+唯一失败前缀+上述字节绑定的复算+三层退出 2/无信号或 wrapper stop、原计数不超额、独立物理/安全证据无越界且模型/worker 已结束、共享 GPU 锁可取得并释放且无遗留占用后，允许把 1803 读成「已核失败、停止边界由冻结输入复现」，仅用于首次启动还没有 start 的 1804。推荐以完整 manifest 和独立研究证明的真实 SHA 钉住这条特例，且必须同时检查前槽和后槽确为 1803→1804。原通用 _contained_stops 对 ValueError 维持拒绝。其余已授权槽位占用、身份、三重退出、锁、来源及剩余额度经原门逐一复核；禁止以模型重试、调门限或换产品追求成功。缺任何证据则保留 1804 NOT_LAUNCHED 分母。1804 的独立扰动条件与同一产品、零重试设置保持，原失败不因其结果改变。

先以原失败/小型 fixture 取得预期 RED，保留本案正例、无返回且发生普通命令/物理推进、假造返回、不同 manifest/seed/fee/角色/帧、ValueError 的其他原因、错误退出/信号、试图再次启动 1803 均拒绝。可复用既有针对配置/预算/失败退出的负控。运行受影响研究测试和 Ruff、真实 1803 只读核验；静态证明副本和旧原件 SHA 前后相等，0 新模型/试次，向父协调者反馈，再由原单 owner 正常派发 1804。
