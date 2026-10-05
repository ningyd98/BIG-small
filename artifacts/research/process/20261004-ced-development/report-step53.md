# 第53步：端侧状态保护及校准读取器软件修复

当前开发主线为 T12/18，T13 并行；较早的 T3b/T7b/T8 真实前置尚未验收。最直接的阻塞在 T7b：完整动作逐帧采集未完成，真实 RESET/独立时钟原件与独立校准组不足。本步关闭两项软件缺陷，未新增完整动作实测或模型调用，formal_accepted=false。

| 问题 | 已取得的证据 | 当前剩余缺口 |
| --- | --- | --- |
| 逐数组状态检查将部分 MuJoCo getter 的新分配内容当作物理状态变化 | 新保护模块区分真实 view 与有来源依据的 owning getter；保留结构、库存和另外11项保护成分。dtype 描述伪造缺陷经原反例复核关闭，root 本步62项 CPU 通过 | 新完整动作采集器还需通过运行前独审并实际跑完；不能把软件通过当作相机采集无副作用的实测结论 |
| UTC 原件缺字段/空值使整个校准读取异常退出 | 原 registered-reader 反例及八类恶格式先 RED；修复后61项 CPU及独审通过，拒绝资料仍保留 assigned group 与 UNKNOWN 分母 | v1原件没有真实 RESET 时间证据；尚无真实 app-owned 有限界正分支，也未取得至少9个独立且有支持的校准组 |
| 正式验证所需证据尚未形成 | 现有真实诊断和旧失败资料保持原样；本机只读检查确认 NTP 服务报告同步 | 同步标志和上游 root distance 不构成每帧 UTC 误差界；真实 Max、风险校准、完整机会/200故障、合格 B0 与 INITIAL/METHOD/FINAL 仍未验收 |

新状态保护模块的[独立复核](capture-state-guard/fix-round-1/independent-root-review.md)限定于软件记录与比较合同：真实 view 比较完整字节；固定版本动态 getter 的 owning 数据不能冒充原生 C 状态，但其结构/support/inventory 变化仍拒绝。dtype 的 schema、规范描述、itemsize、shape 和字节数必须一致；没有通过排除五个或七个具名数组来跳过检查。旧 REQUEST_FIX、RED 和原始诊断保持原字节。

校准读取器的[第三轮报告](t7b-native-calibration-source/fix-round-3/report.md)与[独立复核](t7b-native-calibration-source/fix-round-3/independent-review.md)记录结构修复。缺 UTC 字段、null、非法容器等现在进入原有逐组拒绝路径，不扩大异常捕获，不删除失败组。完整 v1 软件控制仍因真实 RESET 缺失而 INCOMPLETE；缺原件控制为 INVALID，几何/动作界均保持 None。严格 mypy 发现的 tcp_pose 字典类型错误已改为用原验证坐标构造 Pose，没有更改校准量或来源权限。

本步 root 新复跑分别为状态保护62项（0.56秒）、校准61项（23.44秒），五个 owned 源/测试的 Ruff 通过，见[命令及结果](step53-verification/results.json)。这些范围与作者/独审重叠，不累计为全仓测试数量。本步新增 physics、renderer、camera、decoder、provider 与 hardware 调用均为0。

历史实测不升级：旧完整采集仍为11分配/10保存/1失败，未进入教师动作；上一诊断仍为10被动步、11采集/11保存、末尾 copy guard 失败。更早 outboard-v3 的9动作和10动作边界观测仅支持离散开发诊断，不能证明完整连续角速度或校准覆盖。[本机时钟预检](native-clock-preflight/report.md)只保存原命令输出和时间括号，external UTC uncertainty 仍不可用。

新 V3 完整采集器首版已软件冻结：作者及独审61项 CPU 通过，32项来源/418333字节/20环境 pins 已准备。但独审及root真实reader重放另复现六个合格反例：PHYSICS BEGIN步号、CONTROL BEGIN类型、CONTROL END/ACTUATOR episode错误，以及额外ACQUISITION_FAILED或未结束BEGIN，仍被首版判为VERIFIED。操作身份联结和原journal分母两项问题待修复，原首版通过日志不追溯改写。见[root复现原日志](step53-verification/v3-reader-open-findings.log)及[精确命令/原probe SHA](step53-verification/v3-reader-open-findings.json)。这些仅为软件夹具，0实际采集，尚无实际 attempt。真实 RESET/UTC v2 设计也已冻结待审，本步不将这些待审入口和采集器混入已验证软件交付。下一项直接验证是用同一顶视相机、控制器和 outboard-v3 标记场景跑完整120步 settling、9动作与原两次 dwell，随后离线解码并如实保留遮挡、异常和失败分母。真实原生 RESET/时钟、独立校准和消费者接入随后单独验证，不改写旧原件。

[第53步机器索引](implementation-status-step53.json)记录当前来源与未完成项。边缘模型按用户要求后置；本步软件交付遵循显式路径提交、推送和远端 SHA 核验，结果写入阶段总结与 Git 记录。
