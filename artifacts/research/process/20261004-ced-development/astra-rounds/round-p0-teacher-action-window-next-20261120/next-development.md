# 教师首动作下一轮开发决策

GPT-6.2 Astra，2026-11-20。先用原帧打通编码与消费者的完整读回，再用新开发实例测整条动作的互斥耗时。可以立即着手 CPU 适配。新 PNG 策略进入真实开发试次的时点是跨接口验证通过、开发配方明确冻结之后。编码基准尚不足以支持正式放行。

## 单项收益有多大

正式 v9 首组控制 740 步、保持 1180 步，首个 POST 报 332.828674 秒，门为 8 秒。较新的 SQL 开发实例在截止前完成 99/1920 步，未到控制器返回。两次的种子、源码和观测时段不同。原任务要求 1920 步及其全部同步工作平均最多 4.167 毫秒/步。现有前缀不能预测全动作墙钟。

真实 242 帧按 AB、BA、BA、AB 配对。压缩级别 6 改 1，968 对 recorder wall 中位差 −2.344 毫秒，四块总时间从 2.319–2.331 秒降至 1.747–1.757 秒。只取原 8 秒窗内的 117 帧，四块 recorder 实测分别节省 0.276343、0.272755、0.272717、0.282831 秒，约为原窗的 3.4–3.5%。这是同内容在离线 recorder 上的收益，活跃控制器的动作收益仍待测。每块完整输出从 166,473,697 增至 168,117,706 字节，增加 0.988%。原采集 ID、解码像素、深度和标定能复现，PNG 文件及派生 checksum 已改变。[原帧软件与计时报告](step-report.md)

## 优先次序

1. **先统一同一采集两端的编码。** 显式采集时，RawV3 的边界回调在会话返回前把 detached SensorFrame 编码入原件，随后 MuJoCo 会话再次把返回的 SensorFrame 编码成上层 observation。RGBDObservation 的 checksum 纳入原 PNG 字节 SHA。Native recorder 用 acquisition ID、文件 SHA 和反馈 checksum 登记当前来源，grounding 绑定 reference/current，独立 reader 从文件重建并比较 tracker 与反馈。只改 recorder 会使相同 frame_id 出现两个 checksum。最低成本做法是在新开发配方绑定一个编码级别，传给两个实际编码点，保留原路径默认 6。先从 242 原帧覆盖显式、逐步、隐式缓存三类，验证 6/6 和 1/1 从 raw 一直读到 acquisition、反馈、tracker/grounding；6/1、1/6 和同一步不同 acquisition 的错配应被拒绝。比较同一 profile 内时间、源、RGB、深度、mask、标定、物理状态、实例与各 pass；旧 6 档可逐字节回读。实测前缀未到达的阶段用既有软件正控或历史回放注明证据等级。

2. **再定位整动作的首要耗时。** 1,331 次 SQL 上下文累计 1.345148 秒，117 个完整窗内 CAPTURE owner 并集 3.042196 秒，其中 RawV3 body 并集 1.069169 秒，raw 关闭至 owner 结束的尾段为 1.655190 秒。SQL 可落入这些区间。先复用原时戳；新开发实例补缺失边界，按同线程单调时钟及 operation、guard、acquisition ID 记录父子起止。分出物理/控制、相机各 pass 与取回、detach、两处编码、同步文件/metadata、SQLite、owner 校验和剩余墙钟。嵌套区间取并集后扣除子区间，多线程另列关键路径。准备、跨截止帧、清退与 flush 单列。计时开销以带与不带探针的同帧回放量化，优先低成本汇总。如果此次已用 1 档，所得是该配置的实际前缀。要归因整动作 A/B 收益，须另行登记同姿态同配置的 6 档比较实例并报告运行方差；历史 99 步只作参照。

3. **按首要开销决定是否改采集架构。** 若同一显式 acquisition 的重复转换占主导，可在单次 capture 内传递一份不可变编码结果，并校验采集 ID、来源与编码策略；不能仅用 physics_step 或图像相似度作缓存键。隐式缓存刷新没有实例通道，注册逐步采集同时有独立渲染、实例和边界；同一步可以有不同噪声、ID 和原始字节。保留两次来源，直到新方案能独立证明采集合同等价。若主耗时落在渲染、guard 或同步落盘，按测量另定软件范围。后台转码涉及立即可读的 acquisition_source 文件 SHA、owner 封口、失败前缀与磁盘上限；采用它需版本化记录合同，并验证有界回压、崩溃/乱序/丢帧检测及 ONLINE 来源立即可核验。现有 write/flush 时间不能解释为物理磁盘 fsync。取消、续租、截止复核频率与正式样本密度继续按原规则执行。

## 真实开发窗口与正式资格

下一次真实验证使用新的开发登记、同姿态/相机/控制规则、独立 assignment、claim、数据库和输出。原正式 v9 和已耗开发实例保留。运行前冻结两个编码点、依赖、源码与实际导入，独占 EGL，记录活跃进程、CPU 负载、磁盘余量及原预算。单次 8 秒开发首动作窗，零模型、零付费、零硬件；磁盘规划计入 242 帧额外的 1,644,009 字节并遵守现有资源上限。截止时保留最后授权/拒绝、在途帧、hold/estop、worker 和 lease 终态。独立 reader 核帧和 pass、时间、物理与控制、SQL、退出与损耗，报告实测吞吐、未归因时间及全程原件体积。

正式资格仍为 0/9。正式原件有 12 个标记未知的采集集中在物理步 862–867，须与首个 POST 超时分别评估。即使开发实例达到 1920/1920，也须再核控制返回、HOLD、POST、全时域标定与几何、遮挡/颜色身份和安全。待开发证据支持新正式发布，按新协议只释放一组；该组全程原始证据经独立 reader 合格后才扩至九组。本文件仅为后续决策。

## 依据

生产入口相对 src/cloud_edge_robot_arm/。显式采集与原帧编码见 vision/capture.py:87、vision/raw_recorder_v3.py:565、:609 和 vision/observations.py:136、:251。来源读回见 research/native_full_horizon_recorder.py:415、:499、:625、:699，research/native_collection_grounding.py:1366 和 research/native_full_horizon_originals.py:1416。逐步/缓存采集见 simulation/mujoco/backend.py:417、:1526，动作约束见 simulation/mujoco/native_horizon.py。

| 只读依据 | SHA256 |
| --- | --- |
| experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/run-02/preregistration.json | 7b81b263c41a05e08ac9cc428bd3315b0bfce79496b8aefa9f7182f8877e9078 |
| experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/run-02/frame-measurements.jsonl | 126f8399005bcadd305e2c57a82a56d699d4526b9e52a3ef20c67be41abf4045 |
| experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/run-02/summary.json | 86d5c7f3ca117634a81b1c00cc1a5a70de1d2977157012531b1ee63cac554a62 |
| experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/run-02/independent-readback.json | e287a27ff60c337d3006a6f7f6b50666d78ce6aed0988837c42e0d2cad9cb50c |
| experiments/results/phase9/p0-teacher-checkpoint-independent-reader-20261120/actual-first.json | 20d33461e7adf6d6770fd3f34a1297d62fb722142c1df3d814441dae96f3dcc8 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-action-window-next-20261120/benchmark-results.json | 40a9d8bfa83000ef1161afcc3f4203ec66e79040198583d1e2beb7f5b7bf9ec7 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-formal-teacher-offline-timing-20261119/read-wall-and-pixels-v3.json | 885c7882e9af2b12540b1480ea4841229d7cb9b78f1eef52ea8a222e64df1349 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-formal-teacher-offline-timing-20261119/read-marker-gap-v3.json | a35ffc37d0352bcf213053c23c206e6002b9c8caaafd56b9d9327befbc754b65 |
