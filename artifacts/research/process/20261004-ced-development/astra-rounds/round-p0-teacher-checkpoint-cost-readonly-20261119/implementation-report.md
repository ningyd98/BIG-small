# 教师 SQLite 单读快照软件验证

按 GPT-6.2 Astra 窄轮核对 14 项输入及计划文档哈希。真实 teacher worker 的 check_active 测试先复现 13 次连接、104 条 CREATE，每次仍重复初始化。生产 teacher 的既有 UTC lease veto 路径现在每次检查进入原 publication guard，打开当前同一 SQLite 的新只读事务，只在数据库段复用一个连接。保留原 5 个 SELECT、typed codec、字段验证和调用次序。快照在当次检查完成或出现异常时释放。其他操作、Memory 栈、本地时间 authority 和已鉴权的嵌套 writer 沿用原入口。 [Astra 方案](plan.md) · [原失败](checkpoint-red.txt) · [软件通过](checkpoint-green.txt)

## 并发和关闭

取消、续租、释放、开启或完成 attempt、CAS 与回收进入原 _job_writer；它在执行任何实际写源之前持同一 publication guard。两个独立仓储实例以事件和非阻塞锁探针建立读写顺序，证明 writer 在读期间无法取得锁。后继 checkpoint 确实读到对应续租、取消、释放或 attempt 结束。原 heartbeat 失联与 monotonic deadline 检查保持。覆盖错 worker、失效时间、非法时间及正常偏移、重复 lease/attempt、错 attempt、本地时间 authority、DB 文件替换、缺表以及连接和锁释放。正式冻结源/时限/任务及阶段没有修改。 [定向并发输出](checkpoint-concurrency.txt)

原始并发测试首次缺漏 finish_attempt 的两个必填夹具参数，补齐后通过。首次 CPU 密集片段使用低于后端最低要求的测试 event_limit，随后改为使用该测试协议的真实 guard_event_limit，保留原测试失败日志与产品阈值。 [首次并发夹具错误](checkpoint-concurrency-first.txt) · [首次 CPU 夹具错误](checkpoint-dense-cpu-first.txt)

## 实测

隔离在一颗逻辑 CPU 上，以实际 check_active 左右交错采 40 对。基线关闭本轮专用快照，保留旧真实查询。量纲为 ms。

|  | 原查询 | 新快照 |
| --- | ---: | ---: |
| 连接 | 13 | 1 |
| PRAGMA / CREATE / INSERT | 26 / 104 / 8 | 0 / 0 / 0 |
| SELECT | 5 | 5 |
| 中位 | 6.792 | 1.970 |
| p95 | 7.088 | 2.113 |

稳定正式载荷除实际新取的 observed_at 都相等，固定同一时间的入口测试逐项相等。新源 CPU MuJoCo 使用软件相机，运行实际生产 recorder、真实 job/lease/OC1 owner 与 guard。4 个物理步取得 48 个 guard 检查、22 个替身捕获 pass、45 个成员，取消前阶段 0.187 s。另一仓储提交取消后第五步未执行，原急停生效。独立读回 9 个采集源和 36 个原始叶文件哈希一致。本轮零模型、零 GPU 渲染、零硬件。 [真实入口成对计时](checkpoint-implementation-timing.json) · [CPU 独立原件读回](checkpoint-dense-readback.json)

## EGL 验证的可行性边界

实际 v9 的 29.649 s raw CAPTURE 区间从 RawV3._new_interval 到 _close_interval，涵盖相机 pass、状态哈希、像素转换和后端 END payload 脱离，并在 _record_frame 前结束。62.821 s 尾段在 raw close 后，涵盖两层帧转换、base64 校验、payload/文件哈希与同步写出、END check_active、owner MARK/END 至上界时钟采样。上界采样后仍有原 owner 认证和回执处理。前段余量 27.164 s 含 BEGIN check_active。以上是可复算的区间，正式运行没有上述细项各自的耗时。局部快照改善与这次 CPU 片段的读回不能判定正式 8 s 可达，首组仍为 0/9。 [实际区间](../round-p0-formal-teacher-offline-timing-20261119/read-wall-and-pixels-v3.json)

原有界真实 EGL 程序使用 VisualRawRecorderV3、裸后端与自定义 deadline guard。该入口缺少 NativeCollectionApplication 的登记、真实 worker/lease 和 check_active，无法对本轮快照做同路径验证。普通 v9 工厂按固定配置 SHA 重算发布 ID/seed，启动检查只允许正式 released ID，prepare_once 写该协议的正式 claim。新诊断应以专用登记和独立新 seed 使用真实 app/worker/SQLite/NativeFullHorizonRecorder，并使正式 reader 拒绝它，用专用 8 s 有界退出和独立清退记录保存采样进度。实际启动须等新 Astra 边界、22 组释放后的独占 EGL 及单次新诊断编排。 [生产 v9 首组](../round-p0-first-actual-v9-teacher-20261119/result.json)

Ruff 与同基点对照无新增问题，旧 sqlite_repository 89 项，修改后的应用和测试文件 0 项。定向 mypy 无新增问题，基点与更新后均为 36 个旧诊断。 [静态对照](checkpoint-static-readback.json) · [相邻 CPU 软件回归](checkpoint-regression.txt)

五个相邻软件测试文件合计 285 项通过，1 项 Starlette/AnyIO 依赖弃用提示。原输出存于私有夹具目录，SHA256 `5f1375fc077571edc11708baa4dc68245dd5d0e4513c1e873d1f65d93cbfdfaa`。
