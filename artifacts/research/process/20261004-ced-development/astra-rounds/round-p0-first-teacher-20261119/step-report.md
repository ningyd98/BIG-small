# P0 零云教师首组

## 生产入口和软件验收

复核 Astra 计划和 11 个输入。v9 沿用 v8 登记几何、动作时域、每步采样、控制器和安全守卫，新增九个独立种子 11919001–11919009。生产入口只释放 `native-p0-20261119-0001`，拒绝第二组及重复 claim。软件夹具在隔离 SQLite 中核对一次性归属、首组种子及 1,800 秒所有者时限。v8 的零释放保持成立。

新专项从旧代码的 6 个预期 RED 到 6 项通过。最终三文件回归为 60 passed、19 skipped、58 deselected，耗时 15.58 秒。回归 JUnit SHA256 为 `acb3014fa445373240326a00f42f981e7631aff31788b931868d8ce78d8bb5da`。独立生产 CLI 在 486 文件冻结副本上完成 prepare、拒绝错误分配和 verify。verify 返回九组 `NOT_RUN`、联合界为空、资格 `UNKNOWN`。准备协议 JSON 文件 SHA256 为 `bee8ad0c30c927cba759269aa3e0a2e2bb25616e71fe390639fa762ed9d60c45`。

## 实际诊断与教师状态

初次零模型 MuJoCo/EGL 在历史同一相机、标记资产、控制器及 MOVE_ABOVE 目标上执行。首次诊断种子 11919000 独立于九组正式种子。原 8 秒守卫在 265/1920 个物理步时拒绝延续，退出时急停已接合。另一次诊断姿态设置获取 16 个连续真帧，红色从一个 196 像素连通块变成 15 和 9 像素两块。初次测量登记的 454 个源中出现一项并行变更，同批真实载入模块没有逐一记录。原件和启动器退出保留。

第二次隔离诊断完成了真实登记 PRE 和 16 个当前真 proprio/RGB-D 帧的 v2 预览。原首动作样本窗口在 181/1920 个物理步时安全停机，复制优化后提高到 391/1920。原 8 秒内逐步取样能力尚未满足，正式首组尚未启动，正式完成 0/9。预览、计时及生产 registry 的独立读回见后续报告。 [初次读回](../round-p0-teacher-bounded-readback-20261119/step-report.md) · [冻结来源与真实复测](../round-p0-teacher-v9-diagnostic-source-20261119/step-report.md) · [复制优化与冻结复验](../round-p0-teacher-capture-detach-20261119/step-report.md)

完整本地原件位于忽略目录 `experiments/results/phase9/p0-first-teacher-20261119/`。初次实际诊断结果 SHA256 为 `a1271a912bdd5ae097e0e0e213a66736920bb4ed9c286533a5a0b15894c718ac`。冻结复测结果 SHA256 为 `b01fac2af900faace2431bd29acd98ba82a6fa6e8f2a53475b1610a9bd1ab043`。模型调用、云调用和物理硬件调用均为 0。
