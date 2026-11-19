# v9 教师 POST 墙钟开销的只读核查

生产首动作的 POST 墙钟为 332.829 s，门限 8.000 s，所需加速约 41.60 倍。首动作完成 740 个控制步及 1,180 个保持步，资格仍为 0/9。13 个所读源码与真实运行的 v9 冻结快照逐件 SHA256 一致。使用新临时 SQLite 软件夹具和原生产 OC1 源做轻量计时，未打开历史运行数据库，未启动物理、GPU 或模型。 [生产证据](../round-p0-first-actual-v9-teacher-20261119/result.json) · [夹具计时](checkpoint-timing.json)

## 可测的重复工作

- native_collection_application.py:1226–1273 在每次 check_active 取一次 job，worker.py:1856–1871 复取，worker_owner.py:149–238 在 publication guard 下第三次读取，并读取 lease、attempt。SQLite 的 get_job 与其 _fetch_one 各调用一次 _initialize，名单方法也各调用一次。一次夹具检查实际触发 13 次连接、26 条 PRAGMA、104 条 CREATE、8 条 INSERT OR IGNORE 和 5 条 SELECT。真实首组的实体范围是单任务与单 lease/attempt，主要结构性浪费是反复连接、DDL 和 WAL 设置。
- 保持原 typed 查询与固定 UTC 读取参数，将整次检查放入同一 publication guard 的单读事务、复用一个连接。合法稳定夹具的 lease 载荷逐字段一致。40 次测得中位数 5.747 → 1.045 ms，p95 6.473 → 1.173 ms。夹具测量 SQLite 子路径，复用连接仍做原 3 次 typed job 读取。生产实现须证明并发等价。
- 根据 backend.py:229–288,416–424,915–926、native_horizon.py:196–208 及 recorder 的 CAPTURE BEGIN/END，每个正常物理步至少做 12 次检查。1,180 个保持步各另有两次，合计下界 25,400 次。再计 step wrapper、隐式采集与控制命令，约 30,000 次。夹具差值按该量级相当于约 141 s，供确定优先级。生产累计 SQL 时间待直接测量。
- operational_time_v1.py:260–288,312–352,414–424,496–523 的单次 active 时间核对触发 9 次 identity 检查，普通事件 begin/mark/end 合计 10 次。一次 identity 含三条 /proc 读取、time namespace 检查等。60 次真实本机 OC1 小计时的中位数分别为 0.926 和 1.061 ms。事件表及回执按身份索引，未发现 owner 查找本身的全表重扫。另有 policy、protocol 反复解码已固定的注册 JSON，可验证只缓存不授予执行权的预算标量。
- raw_recorder_v3.py:538–560 每个命令从整段历史重建去重集。后端虽只返回本次切片，backend.py:593–594,688,718–719 在切片之前会深拷贝全部命令历史，正常和异常出口均受影响。两项各为 O(C²)。可验证先切片再脱离对象及随 append 更新的唯一序号集，保持原顺序、冲突和失败记录。首动作的实际累计命令耗时待测。
- raw_recorder_v3.py:565–596 对成功帧执行 PNG 编码、深度打包、base64、校验及 payload 构建。native_full_horizon_recorder.py:498–552 逐字段解码后写盘，再重编码作 canonical 检查，并哈希 base64 及完整 payload。显式 MuJoCoCaptureSession.capture_with_instances 还对同一个传感器结果生成在线观测。可验证共享同一个不可变、已验证的编码结果，要求检查值、源文件字节、哈希与顺序可复核。
- 原运行 3,373 帧、8,789 个 pass，配合冻结 reader 的 2/3 pass 合同可算出 2,043 个三 pass 与 1,330 个二 pass。每物理步的三 pass 含实例，step 末的缓存更新另做 RGB/depth。去掉全部二 pass 最多减少约 30.3% 的 render pass。原合同为每次采集保留不同身份、时间、因果顺序，reader 也要逐帧估计几何。缓存变更须核对消费者、噪声 RNG、原计数和失败分母。既有有界 391 步测得渲染 0.994 s、转换 2.924 s。同速率外推到 1,920 步两项合计约 19.24 s，供确定测量量级。 [有界证据](../round-p0-first-actual-v9-teacher-20261119/plan.md)

## 候选验收

以同一 checkpoint、同一 publication guard 的单次读快照和现有 typed codec 消除重复初始化。保留 fresh job basis、唯一有效 lease 和未结束 attempt、heartbeat 失联、取消、到期、owner identity、OC1 时间、检查频度和拒绝行为。若 SQL 聚合不能复现日期解析及逐行负控，使用同一连接里的三次窄查询及原 Python 判据。验证稳定 payload/摘要逐项等价、同时续租和取消、guard 等待后的更新读回、过期和错误源、重复/未知记录，以及数据库替换时停止。现有测试入口为 tests/test_visual_worker_owner.py、tests/test_native_collection_authority.py、tests/test_phase11_1_simulation_runtime.py 和 tests/test_operational_time_v1.py。优先以实际连接和 schema 语句次数验证局部收益。

将 _record_frame 同步写盘挪到 owner MARK/END 之后会触及 acquisition 路径、SHA 可用性及崩溃前缀合同。独立异步方案须验证完成、积压、取消边界及逐帧原件。当前夹具不足以支持正式 8 s 时限可达，独立读回的 marker 缺失仍需单独处理。

私有夹具源码位于 cache/local-verification/20261119-worker-docs/teacher-timing-readonly/checkpoint_timing.py，SHA256 6e8bbb7b8d50792f77456585c2669d393d5de08ae8af490be190e36ff54f0c2f。原计时回执 SHA256 df76d87948d896e7f08def6e42897f7329ca10aaae573c40be7a9dfecda1f4a2。
