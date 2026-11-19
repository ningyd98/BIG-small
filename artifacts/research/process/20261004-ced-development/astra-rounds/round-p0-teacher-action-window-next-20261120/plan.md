# 首动作 8 秒窗口：CPU 原帧离线配对取证计划

- 轮次：`round-p0-teacher-action-window-next-20261120`。
- 规划角色：按项目 AGENTS.md 指定的 `gpt-6-astra` 修复规划；主线方案设计模型仍为用户指定 GPT-6.2 Astra。
- 状态：PLAN_ONLY，交回主代理决定是否指派 Sol；本轮没有实施产品修改，没有启动模拟、模型或真机，没有新增正式组。
- 使用 systematic-debugging 的先证据、后假设原则。授权范围仅本目录内离线取证程序、测试和报告；生产 `src/`、协议、采样、守卫、8 秒门限和身份规则不改。

## 问题与原始证据

唯一正式 v9 首组 POST 为 332.828674 秒，原限额 8 秒；控制 740 步、HOLD 1180 步，合计 1920 步；正式资格仍 0/9。该历史运行未用此次优化后的 SQLite 路径。独立开发 seed 11920067 才实际穿过优化路径，8 秒内完成 99/1920 步，未到控制器返回、HOLD 或 POST，截止拒绝后保持与急停，242 帧保留完整。两次不是同 seed 配对实验，不把它们称为实测加速比，不用 99 步线性外推完整动作耗时。

开发首动作 1331 个 SQLite 读取上下文累计 1.345147708 秒；117 个完整窗内 CAPTURE owner 并集 3.042196209 秒，RawV3 body 并集 1.069169329 秒，raw 关闭至 owner 结束尾段并集 1.655189768 秒。还有一帧跨截止，单列，不塞入完整窗口分母。SQLite 与 owner/尾段重叠，不相加，不把尾段直接称为 I/O。现存统计不能证明 PNG 是主要根因。

已核对代码路径：RawV3 先 `_close_interval` 再 `_record_frame`；后者将 SensorFrame 转 observation，PNG 编码、float32 pack、base64 与模型验证都在其中；Native recorder 再 base64 decode、同步文件写出、再编码规范性检查、字符串/文件哈希、实例打包、metadata canonicalization 和写出。owner 还包含 END 检查与封口。`_write_blob` 是 `open(xb)→write→flush→close`，没有 fsync；本轮只能测用户态写入/页缓存交付，不得称为物理介质持久化延迟。camera 内 RGB/depth render、copy、tuple 化、校准和实例处理也没有独立历史打点。

现存原件不能分离历史转换、PNG 编码、文件写入或 fsync 时间；禁止按剩余量回填精确阶段时长。可检验假设仅为：在此 320×240 实际画面内容上，PNG 压缩级别 6→1 是否减少 CPU 序列化总成本，且新增写入字节是否抵消该收益。现有函数已有 `png_compress_level` 参数，离线调用显式 6/1，无需改产品默认值。

## 为什么现在可以做真实 CPU 内容基准

开发原件 `frames/acquisition-1..242` 保存 lossless RGB PNG、depth.f32、mask.u8、instances.i32 和 source-frame.json。本计划生成前已核对 inventory 的全部 1228 件文件长度和 SHA256，逐帧目录 1212 件文件（含 2 件 feedback）的真实路径及 SHA256 全量列在 plan.json。可以解 PNG 得到真实 RGB 像素，unpack `<f` 还原 float32 深度，读取真实 mask、实例、相机和身份，冻结为 CPU 输入，在计时前构建 SensorFrame。保留所有 acquisition、operation、physics step、role、frame_id、captured_at、calibration、source provenance，不生成新采集身份。

这叫“从实际原件重建的 CPU 输入”，不叫原始 pre-encode SensorFrame 快照。原运行的渲染前数组、copy 边界、depth tuple 的更高精度信息、分配状态和调度现场未保存；f32 roundtrip 不能证明恢复那些历史对象。RGB lossless 与 depth/mask/instances 的原始文件字节可以严格验证。渲染/GPU、detach、worker/SQLite、控制器、真实 guard 和完整动作一律不进入该基准结论。

## 限定实施步骤

1. **冻结与前置复核**：逐一核对 plan.json 输入 SHA；核对 source-freeze 和实际导入清单，记录 baseline import `__file__`/SHA，优先用历史冻结源码。当前 observations/camera/recorder 与冻结源码 SHA 已相等，仍需运行前复核。禁止把当前未冻结代码冒充实测版本。验证 originals 全 inventory（含未选入时间样本的 settle 帧），正式 protocol/已消费 claim 及保护清单前后 hash 不变。只读原件；SQLite 如需独立 reader，只读私有拷贝，不让原库生成 WAL/SHM。
2. **离线工具与预期 RED**：在本轮目录创建 `benchmark_original_frames.py`、`test_benchmark_original_frames.py`。先保存输入文件损坏、角色/身份被改、baseline 重编码不等值、阶段覆盖重叠、输出覆盖尝试的负控 RED，再实现。禁止网络、模型、backend.initialize/reset/step/render、GPU context 和真实硬件调用；工具入口不调用 collection CLI。测试若需要 fixtures，显式标 synthetic，不能混入性能样本。范围外失败暂停，留原日志，重新交 Astra。
3. **重建与资格门**：加载全部 242 帧，按 acquisition 数值顺序预登记，不挑快帧。输入解码/重建不计入编码主指标，但独立记录。对全部帧以冻结默认 level 6 走 `observation_from_sensor_frame`，比对重编码 RGB/深度/mask 字节、observation payload 与原 digest；对实例和 metadata 用独立 reader 校验。若某环境 PNG 输出不再字节一致，报告环境差异并停止将它认定为生产字节等值基线，不自动放松要求。允许单独保留已完成的内容一致性结果，后续范围需重新计划。
4. **单变量候选**：A=原参数 level 6，B=同一现有函数显式 level 1。只变 PNG 编码参数；尺寸、RGB 像素、depth.f32、mask、实例、元数据身份和帧数必须逐项一致。PNG 字节、对应 base64、checksum 和下游摘要通常不同，按新输出重新计算并独立验证，明确列差异；不得借用旧 digest 或修改原 inventory。B 仅隔离实验候选，不迁入运行或登记。
5. **两层真实测量**：第一层用未打点现有函数取得每帧 encode+validate 的 wall/process CPU，以及在隔离输出目录走同等 recorder 序列化与文件合同的总 wall/CPU/bytes。优先调用原 recorder 方法配最小只读上下文；任何适配器均须与 A 原产物逐字节验证，并明确不包含真实 owner/worker。第二层在离线进程临时 wrapper 中打点现有 Image.save、pack/base64、model validation、canonical/hash、file open/write/flush/close 等调用，按嵌套栈计算 exclusive 时间，留下 residual；不改 `src/`，不使用这些 wrapper 结果替代未打点主指标。没有可可靠包裹的细项留为合并 residual。另跑同内容无打点/有打点配对量开销，不从业务阶段生硬减一个常数。总跨度、exclusive 栈及 residual 必须闭合，禁止跨重叠段相加。
6. **配对设计**：全部 242 帧均参加；每帧两次 AB 与两次 BA，共 4 个完整配对块；块顺序和帧顺序预登记，单独预热一次（不入统计），每个变体用独占新目录。计时前两侧输入已在 CPU 内存；单线程不并发竞争。结果分别报告 REGISTERED_PER_PHYSICS_STEP、IMPLICIT_SENSOR_CACHE_UPDATE、REGISTERED_ACTION_BOUNDARY，settle/动作窗内/跨截止分层。报告每个 frame/block 的原始 ns、CPU ns、输出字节、配对差值、分层中位/p95 和完整块总 wall；不能将 242 帧当 242 个独立实验或把重复块当正式组。不得用 best-of 宣称获益。计时值非确定性，只有输入/内容核验应重复一致。
7. **独立读回与交付**：独立程序重读 A/B 输出，比较 lossless 内容、角色、身份与新的 SHA，自身不依赖 benchmark 的 pass 标志；构造一项篡改负控确保拒绝。保留原始 stdout/stderr、每个测量记录、环境、输入和输出清单、失败日志，生成 `benchmark-results.json`、`step-report.md`。公开提交工具、测试、小回执及清单；完整新输出留受控本地目录，不能称为完整远端复现包。仅提交本轮明确路径，由主代理按研发分支工作流推送并核对 local/upstream/remote SHA。

## 实际执行前置条件与停止条件

使用项目已有可导入 Pillow/Pydantic/NumPy 的 Python 环境，先记录实际解释器路径、版本、包版本、源码 SHA、CPU/亲和性、负载、内存、输出 filesystem/mount、空闲盘；不依赖 shell 的 `python` 别名。规划时一次只读 shell 调用发现 `python: command not found`，后续使用 `python3` 完成取证；没有对此环境做修复。计时使用 perf_counter_ns 和 process_time_ns，记录 clock resolution。

给 CPU/磁盘留独占可用窗口，不与主线模型或其他基准并发。执行前可用空间至少 6 GiB，输出硬上限 4 GiB、进程 RSS 上限 2 GiB、墙钟上限 10 分钟；超过上限只停止并保留部分输出，不能删历史或静默减样本。执行脚本记录零模型/网络/模拟/真机计数与拦截证据。进程异常、原件 SHA 漂移、baseline 不等值、来源缺失、超预算、未解释阶段重叠均不算接受；保留失败交 Astra 下一轮，不能先修再补计划。此基准不需要新的 claim、seed、GPU lock 或正式许可。

## 验收与下一工程决策

本轮工程成功标准是：全部输入可追溯、A 基线可重建等值，B lossless 内容/身份等值且摘要诚实更新，配对计时与字节/资源记录完整，负控拒绝与独立读回通过。候选可以“无收益/噪声内/变慢”；这也是完成取证，不是隐瞒的失败。仅当 4 个完整块均总 wall 改善、按帧配对中位方向一致且收益超过实测测量扰动，并满足输出预算时，才建议另轮考虑该参数；这不是产品接受或 8 秒通过门。

若收益不明确，或发现 residual 主导，先交下一轮具体定位建议，不自动引入异步队列、批量落盘、缓存 guard、降低帧率或改变独立身份。若要识别运行内成本，下一轮需单独计划开发专用、默认关闭的单调钟分段见证：sensor return/detach、observation conversion/PNG/validation、序列化/hash、write/flush/close、check_active、owner close；同一 operation/acquisition 与统一时钟，嵌套关系明确，计时记录缓冲到安全终态写出，完整记录异常/in-flight 和 instrumentation overhead；时钟适配/跨 BOOTTIME 对齐先验证。需要观察物理持久化则另列 fsync 实验语义，不把当前 flush 改成 fsync 后混称原路径。

这样的在线取证改造及任何新 EGL 运行均不在本轮实施范围。实际验证需重新冻结源、唯一开发登记、原同步守卫和原采样密度、可用资源与清退条件；不得以离线提速推断 live 通过。只有另行授权且按未改门限的完整原动作真实测得结果，并走独立正式验收，才可能改变正式结论。本轮正式资格固定 0/9，新增正式组 0。

## 输入索引

`plan.json.inputs_sha256` 列出本计划直接读取的报告、源文件、原始证据路径及真实 SHA256；`frame_inputs_sha256` 列出全部 242 帧目录内的 1212 个原始文件（含 2 件 feedback）。历史与开发分开来源，不复制大型 raw 到 Git。执行人必须先验证这些键对应的实际文件，再写新产物。
