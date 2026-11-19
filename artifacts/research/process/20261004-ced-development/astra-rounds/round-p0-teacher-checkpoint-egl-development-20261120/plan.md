# 独立 SQLite 教师 checkpoint 的真实 EGL 开发短窗

## 已知范围

正式 v9 首组原 POST 为 332.829s / 8s，已消费。真实生产 check_active 在稳定 SQLite 夹具中位从 6.792ms 降至 1.970ms；四步 CPU 测试用了替身传感器。旧 391/1920 真实 EGL 时段用了 VisualRawRecorderV3 和辅助截止，未进入 NativeCollectionApplication.check_active。这三个记录分别保留。

普通 collect-once 不能以新角色、seed 或复制 v9 文件完成本任务。read_protocol 对 v9 以固定配置和九个分配重构查验，普通 from_startup 只接受唯一 released ID，prepare_once 再读并写其正式 claim，真实 _live 检查身份、PID、线程及 worker 原点；手工设置内部注册表、伪造 lease 或复制已消费 release 均无法提供独立证据。需要一个用途明确的受限发行分支，保留正常组件，不需要再造物理控制或观测格式。

## 软件与证据边界

1. 建立独立开发注册与只可运行一次的显式入口（可选现有脚本独立子命令）。固定诊断 schema/角色、一个全新 ID/seed、独立目录与 SQLite、真实 +Y 标记/相机/控制器和原动作参数、零模型、一个 MOVE_ABOVE 前缀和固定的首动作 8 秒单调钟上限；独立预登记经过检查的 seed、工作树/wheel 或解释器、配置/资产与全部真实导入 SHA。注册仅能从固定诊断配方生成；来源/资源和 v9 受控执行配方可复用，能力域与 claim 不可混用。普通 release/collect/verify 仍拒绝未知或诊断协议。开发入口也拒绝正式协议/ID/claim/输出、错源、重复、符号链接替代或跨域恢复，不允许任意可执行回调、任意任务或门限覆盖。
2. 在工厂及 prepare 内抽取确有必要的共用应用建立、SQLite job 提交和原 worker 派发。诊断分支单独验证其注册/写排他 claim，使用真正的 NativeCollectionApplication、SimulationWorker.poll_once、活跃租约、原 owner 时钟/源与正式路径同样的 check_active、真实 MuJoCo/EGL RGB-D、MuJoCoCaptureSession、NativeFullHorizonRecorder、真实 SkillExecutor 与实际控制器。复用 run_from_worker 已注册的资源建立/检查/关闭和实际第一动作路径；不得用新旧 tests 夹具替代传感器、直写 _REGISTRY、手设 worker origin、合成 RUNNING 输入或换裸 recorder。诊断配方不得被完整组 registry 接受，任何终态一律 development scope。
3. 在该诊断第一动作原时钟锚点建立 8s 截止；严格按原 PRE/安全、原每 checkpoint 调用、真实 SQLite UTC/lease/取消/heartbeat、原采集密度/编码和身份门运行。仅在诊断分支的既有同步授权点附加较紧的截止检查，原截止之后禁止新控制/物理授权，经原 guard safe_stop、终止登记和资源清退。区分原正式 POST 门与新诊断前缀主动截止；分别报告最后授权时刻、截止/停机、在途操作及窗外关闭耗时。若更早触发既有保护，记录实际退出并结束该次尝试。不把 8s 内未完成全步当作测试不合格或重试理由。
4. 每份结果绑定同一 job/run/lease/attempt、worker 真实派发与终态、输入/导入 SHA、SQLite 读模式，以及真实 recorder 的捕获/控制/owner 事件。低扰动计数必须明确测量开销；至少能从受控真实调用和原件证明应用进入新的 UTC 快照分支，记录检查次数及耗时/SQL能力范围，不用事前 CPU 夹具计数冒充真实时段。保留原 RGB、深度、物理状态、标定、哈希、控制器返回/命令、同步 owner 和 lease 来源；独立读回核帧/时钟/安全停止与终态。无观测到的后续物理状态显式写未知。零任务模型、零云、零真机、零 qualification credit。

## 验证和实际窗口

先在软件阶段验证独立 schema 的生产入口、真实派发构造和来源；用临时测试目录覆盖诊断与正式双向拒绝、已有 claim、无权来源/失效租约、截止停止、清退、普通 v9 路径及 SQL 回归。必要的测试替身只用于软件负控。原 v9 协议/claim 内容和原 20+2 所有权前后核 SHA。若实现需要扩大正式协议的 admission、暴露通用工厂令牌或削弱正式来源判据，应留具体证据另行评估，不把这种扩大作为本方案的一部分。

软件及输入验证完成即可安排一个真实诊断窗口。与正在进行的开发 12–22 及真实模型/EGL 协调原资源锁，待释放时核设备、磁盘、进程、负载，开始前登记运行命令及唯一 claim。用新源/新目录正常 CLI 实际运行一次。验收区分软件、真实 8s 部分时域和仍未通过的正式资格；报告步数/帧数、是否碰到 8s、真实 check_active 与 SQLite 来源以及剩余热点。没有真实派发、未进入目标 SQL 或无可独立读的原件，只能报该环节未验证。本轮独立开发证据不授权重跑 v9 首组。
