# T2 真实工厂入口的软件验证

按R439执行，适用R440资产修订、R441教师准入、R442 RawV3适配与双pass补充；序列化失败由实际Astra R443修复。原T2两项API RED保留；原GREEN 71P/6F不覆盖；修复GREEN 80P/1deselected，完整证据在相邻R443目录。

调用链已接入：prepare预登记九组 → 私有NativeCollectionApplication → 入队前OC1原deadline → 单SQLite作业 → 原SimulationWorker.poll_once/唯一lease与attempt → 新exact worker dispatch → 唯一backend/recorder → 像素grounder与原Shield/条件 → 原SkillExecutor → full-H runner。软件worker测试真正经过SQLite租约，但用软件执行体，没有初始化MuJoCo。

原帧采用逐帧原字节落盘，完整inventory保留每个分配。旧RawV3保留GROUND_TRUTH_TEACHER兼容类别，新envelope说明PIXELS_PROPRIO_REGISTERED_CONSTANTS控制与OFFLINE_LABELS_ONLY真值用途；无模型hash为None。原MONOTONIC/UTC descriptor不转换，BOOTTIME链另存。FULL_HORIZON_HOLD映射旧HOLD；三pass采样和两pass缓存刷新分别记录。

通过软件测试不能证明实际八动作可完成；独立reader尚待T3，完整软件最终回归/静态/独审尚未完成。实际physics/render=0，native=UNKNOWN。
