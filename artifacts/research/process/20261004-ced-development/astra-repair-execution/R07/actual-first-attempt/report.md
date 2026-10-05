# R07 首组真实故障教师与独立原件复算

**首组来源 PASS_SCOPED_ACTUAL_SOURCE，1/200 已执行。** `recovery-0001 / attempt-1` 唯一执行退出0；严格原件复算与原结果相同，原PROVEN记录未改写。其余199组未执行，机会标签生产仍未实施，G4及正式研究未验收。

## 实际发生与资源

使用冻结协议 `66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724` 的原分配场景，120步settle后注入注册的TARGET_MOTION（20mm/s、1秒、direction_y=+1），再执行原九动作教师。真实注入位移为 **19.102003mm**。7047物理步、7048原始状态、7047逐步执行器记录和9个教师动作均保留；无provider调用或隐式重试。

独立物理结果SUCCESS：抬升91.853706mm、连续保持0.629167模拟秒、放置稳定2.150000模拟秒；安全检查限注册33对，结果SCOPED_NO_VIOLATION。实际fault start为0.500000004模拟秒，终态29.362500235模拟秒，fault到终态 **28.862500231模拟秒**。

GNU time实测整个子进程wall **17.45秒**、peakRSS **410528KiB**、退出0。首组fault及终态均在该子进程内，整个进程wall是本组fault→终态wall的保守上界；模拟秒与wall秒分别报告。当前生产器的逐步Rcap检查仍使用模拟域、外部watchdog为1800秒，不能据本组或CPU验证声称后续200组统一wall-Rcap已经实现。正式研究须补实际fault起点wall原件与相应守卫。

原始目录共17文件/**101586767字节**，包括result.json；result里的101583657字节是在写result之前统计，两者并不矛盾。全部原始文件仍本地，Git交付的报告、hash及协议不等于完整raw远端包。全分母保持200、已执行1、未执行199，不能以首组成功率作为G4。

## 独立读取范围

root使用既有严格 `_recovery` 读取真实六份source载荷，重算物理、注入、逐步控制/指令及九动作join；没有调用新生产器、backend、renderer、模型或授时。核对原协议6payload、23执行source（活动生产器的原版本从immutable source-package核对）、所有17raw、唯一allocation及原result payload SHA，合计48个限定输入before/after不变。结果的全部proof字段经JSON数组表示规范化后与原result逐字段完全相同。

独立读取器最终退出0，内部wall2.361232秒，GNU time整个读取子进程wall2.62秒、peakRSS239916KiB。首次读取的assert误把Python tuple形式的33对碰撞清单与JSON数组直接比较，退出1；原脚本及日志按`independent-recompute-first*`保留。仅修正表示比较，没有改评价器、阈值、原proof或actual数据；该失败不是物理评价不一致。

原件、唯一分配、commands/actuators/故障及全部失败保全详见 [机器复算记录](independent-actual-review.json)、[只读复算脚本](independent-recompute.py) 和原终端/resource日志。新实际执行次数0，复算不产生新的独立场景组。

## 后续修复与不升级项

末尾guard重复加入recovery_start已由原件及稳定tail CPU边界反例确认；首组在修复前后都低于60，不重标原result。最小补修与共享原allocation namespace的successor方案见 [duration-fix报告](../producer/duration-fix/report.md)。旧冻结包保持字节且正确拒绝新源码；后续执行必须先完成successor独审及wall-Rcap来源检查，不重建seed、不删除已消费attempt1。

本组采用注册320×240/noise0的离线教师域，不是native默认noise0.001域；没有在线恢复权限、Max角色验收、native clock/geometry、完整机会标签或正式G1/G4/INITIAL/METHOD/FINAL升级。
