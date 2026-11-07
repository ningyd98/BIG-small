# T3 — 独立完整时域读取器开发验证

原 T3 RED 保留：1 个预期 API assertion failure。原 T3 GREEN 唯一一次完成：97 PASS，pytest 52.29 s；supervisor 53.047804888 s，returncode 0，reaped=true，source_drift=[]，remaining_live=[]。完整 stdout、JUnit、spec、逐事件日志和运行来源清单保存在 ../validation/t3-green/。

新读取器从独立原件目录重建库存哈希、原计划/租约、操作与物理序列、逐帧 RGB-D/实例字节、八动作/保持/终态、原 grounding 与 Shield 输入、UNKNOWN 收集准入、离线物理评价和逐点联合误差。新增九个 CPU 测试含八动作原字节图、损坏原件、RELEASE 完整名义变换/八顶点、保持区间、调用者缓存分数无效、完整九组分母；旧 completion/horizon/reader 组件回归一并通过。

八动作 fixture 明确 SOFTWARE_ONLY，是 schema/算术/原件读取测试，不是实际 collector 原件或工厂权限。R445 明确命令姿态与实测姿态的区别；旧 geometry 与旧 UNKNOWN 结论不改。未运行组、缺帧、必需 UNKNOWN、失败和不完整 full H 保留无穷分数，单组不能产生 q 资格。

本阶段实际 MuJoCo 初始化、physics、render、模型请求均为 0。R444 生命周期/来源闭合测试与 R446 首次注册帧顺序修复仍待原 final-regression；最终静态检查、一次独立审查、prepare、唯一首组实际采集和独立 read 尚未执行。本报告不宣称真实 full-H 完成或正式研究验收。
