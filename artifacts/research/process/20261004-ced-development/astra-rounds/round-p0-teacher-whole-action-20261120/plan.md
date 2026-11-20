# 教师首动作完整测量

GPT-6.2 Astra 设计，GPT-6.2 Sol 实施。

用户明确要求先真实测完整首动作。一次非正式开发、同 seed 11920067、同姿态同配方，计时自真实 PRE step_started_at_mono 到同一锚的真实 POST；同时取得控制器返回、保持和终端 acquisition。独立记录测量覆盖、动作接受及教师资格。

## 原始证据

正式 v9 首组 seed 11919001，dispatch120→return860→terminal2040，POST 332828.674ms > 8000ms，worker BLOCKED_BY_ENV，正式0/9。旧开发 seed11920067 由专用 _CheckpointDiagnostic.authorize 在8秒后拒绝第一条 checkpoint，仅120→219、99/1920，无返回/HOLD/POST。正式检查由同一 Shield context 在 PRE 和 POST 使用原 StepTimeoutRule（elapsed_ms > step.timeout_ms），原 worker/checkpoint/任务总截止一直有效。8秒前缀是旧开发专门附加行为，两份历史资格和预算独立。

已验证242原帧：219逐步+21缓存；2显式帧 acquisition-123/124 模拟借用后端走了实际 session/RawV3/Native recorder 路径，6/6、1/1反馈与生产 grounding/PRE相容，混档和同物理步替换两个真实消费者均拒绝。B档使 PNG/checksum 改变，原像素/深度等同，完整输出增0.988%。117窗内帧仅在离线 recorder 省0.273–0.283s。早先 SQL 1.345s 与 CAPTURE owner 3.042s重叠；历史比较不构成整动作提速的配对实测。

## 实施边界

1. 给第一动作测量单列不可混用的新开发 schema、scope、固定 assignment 与 canonical 单一注册/BEGIN 位置；使用新 worker job、数据库、输出、独占 lease/attempt=1 和 fresh 单实例 owner。种子11920067以及资产/相机、dt=1/240、初态、原始 MOVE_ABOVE 配方与注册条件沿用已消费开发参照。新 worker 真实读取与注册匹配的源码、编码和原预算，公开回执绑定 source/root、登记 SHA 和父源 SHA；保留旧正式 v9 和旧 cutoff schema 的独立拒绝、历史原件和原有 guard。新用途零教师学分、无正式真值使用权；不得经复制目录、回滚状态或在别的输出重复同一登记。只发第一动作。

2. 执行实际 NativeCollectionApplication、SimulationWorker、实时 SQLite/单一 lease/heartbeat 与取消、原 owner 时钟、backend hard safety、真实 EGL、实际控制器及每物理步采集与原 NativeFullHorizonRecorder。新 schema 的计时没有旧开发专属 authorize(now>=8s) 中途撤权；不得通过捕获该异常继续、关闭检查或跳过初始 PRE。复用原 Shield PRE、原 session.execute/_run_registered_horizon（真实返回步数、剩余步 HOLD、终帧）、POST context 重用同一 PRE monotonic 锚，走原 POST shield 和独立条件汇总。不得将 timeout 改为更大/重置 PRE 锚或手工构造 POST。原 run 若 PRE、controller、租约、任务截止、采样、资源或任何物理安全先拒，立即按原 fail-closed 清退出完整前缀。POST 合格或拒均结束首动作，不能发第二动作；保留原错误码与结果/worker/CLI的独立状态。

3. 只在新开发实例从同一冻结参数传 PNG=1 到真实 MuJoCo capture_session 返回路径与 RawV3 边界观测编码路径；默认及旧源的6档沿用，禁止运行时全局 monkeypatch。所有帧仍有原 acquisition、全三通道/缓存各自真实 pass 和标定/物理原件，同帧反馈、tracker、grounding、PRE/POST 和 reader 均以该实际编码的 checksum/文件 SHA 重建。POST 回读须重新验证运行时 freshness、lease 和 terminal acquisition，不能移植旧图像/派生。仅按需改注册/入口、诊断测量、这两个编码点、调用与定向测试，生产安全规则/时限和正式验收不改。

4. 同一真实进程从 PRE 开始记单调钟纳秒与 thread（可辅 process/thread CPU），标记 controller dispatch/return、HOLD begin/end、terminal acquisition、POST instant 和判定落盘；另列启动/settle/bootstrap、shutdown/flush。对动作内计时记录可独立重算的 span 或有原顺序/ID的等价有界轨迹：按线程和 operation/guard/acquisition/step 对齐真实控制与 MuJoCo step、render/取回、detach、session 与 recorder 两处 encode、同步写/索引与 hash、SQLite、owner/guard、未分类；没有可分信号的项明确 combined/unknown。计时器按真实嵌套相减并对同类区间取并集，跨阶段/线程分别求交或单列，残差显式覆盖到 POST；不得把嵌套时间加总。记录样本数、探针额外读钟/内存/输出范围和同软件夹具开关额外开销，未校正与不可分残差如实报告。避免每行同步刷盘增压或以减采样制造提速。必要门与现有记录始终同步生效。

## 运行与验收

1. 先 CPU RED/GREEN：新旧 scope、错误登记/策略/来源、再次启动/复制、正式 verify、异常和 early-stop 均有负控；旧 cutoff 边在8秒仍拒。新模式用真实 gate 受控时钟核对 >8s 在 POST 拒、是否等于边界遵循原比较，原取消/lease/physics hard stop 即停。测试第一动作返回/不足/保持/真实 POST 与不发第二动作，双编码6/6、1/1及混档、source/feedback、篡改/缺失计时拒绝。source/reader 用同基线对照；Ruff、受影响的 mypy 新增零及相邻 authority/recorder/诊断 reader 专项。已冻结跨接口 242 的历史回放不得挪作新 POST 原件。

2. 实施前对输入逐件核哈希；前置 restore 真实源/venv/独占 GPU EGL，确认源和实际导入/原生库的稳定性、原 registration/claim/数据库不变。依据实际 recipe.settings 输出卷门34,359,738,368B=32GiB，raw cap16GiB，实际 RSS cap8GiB、task_timeout_s=1800，原物理/相机与 render 等预算保留。预查时 W卷可用58,750,799,872B；实跑前在真正输出目录复查空间及预计全动作原件、计时与只读回执支出。教师仅零模型，60GiB 模型加载门适用于单独模型路径。不要删原件或用测试盘豁免生产门。记录正在运行的进程、机器负载、EGL 实际设备/独占锁/退出后释放、磁盘/进程内存峰值。先冻结再启动唯一 claim，保留进程确认、PID、stdout/stderr、实际 wait 退出、单次资源和账本。用户已授权，此轮软件/源与生产前置合格可执行，不增设额外审批。

3. 独立 reader 新进程只读，复核初态/同姿态来源和实际 seed、源、单次 claim、真实 worker SQLite、PRE 基准&allow、receipt dispatch/returned/terminal 及 controller/HOLD、逐步 RGB-D/实例与 pass、PNG1 真实文件、guard/owner/原命令、POST input/result、条件层和 Shield 各 rule、关停与进程费用；核所有原全量 inventory 与计时包含关系，计时和敏感 raw 依原交付存本地，公开清单与 SHA。两次只读决定性输出匹配；保留拒绝缺失、混档、来源、计时漂移的负控。正式 reader 理当拒绝新开发用途。

4. 达到真实 POST（含其拒绝）并可重建首动作全段时，报 measurement_complete=true、原 elapsed_ms、8000ms、speed ratio 如仅作相对期限比，action_pass 依真实 Shield/conditions，qualification_credit=0。若 STEP_TIMEOUT 是唯一拒因：整动作已测、动作超时、资格0。若提前保护或原件不足：measurement_complete=false，记录最后阶段、真实停止判据、可测前缀及无法取得的返回/HOLD/POST 字段；不得假设1920或修正成完整。任何终态均消耗新登记唯一试次；不自动重做、扩组或改写旧实验。

基点为 de0f79bfe44c45799d7c3b4fd6bab8b7299e33a1。输入文件及 SHA256 见 [plan.json](plan.json)。
