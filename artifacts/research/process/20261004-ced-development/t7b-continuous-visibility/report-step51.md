# 步骤51：真实逐步采集失败与动作参照实现

完整逐步采集脚本的三项P2已经在CPU独审关闭，32项必要来源/408064字节及对应归档冻结后，root执行了唯一一次attempt。实际稳定等待到step10时，采集前后data_arrays整体hash改变，保护立即拒绝。终态10物理步，模拟时长0.041666667秒，原120步settling未完成；0教师动作、0运动命令、0模型/硬件调用。1次setup、1次bootstrap及11次逐步camera调用均保留，共13次；逐步10份观测保存、1次失败，原最大gap0.005秒不变，成功前缀最大模拟gap0.0041666667秒。未覆盖、重跑或补位该attempt，整体FAILED/INCOMPLETE。

原21份采集文件/2031712字节已冻结逐文件hash，离线派生文件另保留。严格离线decoder只读取原RGBD与登记，step0..9十个已保存帧均OBSERVED；总采集分母仍11，最后没有合格保存帧。0.0375秒成功前缀不证明完整动作内连续可见或角速度。见[失败独审](independent-actual-failure-review.md)、[完整失败审计](independent-actual-failure-audit.json)、[原始清单](attempt-1-file-hashes.json)、[部分前缀解码](partial-pose-prefix.json)。

日志只定位到data_arrays aggregate差异；model arrays/options、控制器、RNG、cache/camera identity、command_count、step/time及双pass physics hash相同。尚不能认定根因或假阳性。新的逐数组/渲染phase诊断准备中，与原attempt分开登记，不借诊断替换失败或删掉保护。

真实日志另揭示离线核验器与fake fixture的ACTUATOR步号误用：真实执行器登记即将执行的步n，原核验器读取n-1。保留原执行核验器和原PASS审查；只读CPU反例在内存修正一处lookup后，成功前缀九条错关联消失，整体仍11allocated/10saved/1failed、INCOMPLETE。见[原始失败审查](independent-actual-failure-review.md)与[真实前缀反例](fix-round-2/independent-actuator-replay.json)。后续新reader须冻结修正，不能修改旧源抹去实测发现。

并行完成[动作参照模块](../../../../../src/cloud_edge_robot_arm/vision/native_references.py)及[局部实现报告](../t7b-native-calibration-source/task1-implementation-report.json)。重新运行原resolved_step与真实SkillRegistry，绑定当前契约/步骤、grounding/TCP、编译payload、role/context/source和完整original/resolved/owner时长；公开标量不认证owner receipt。固定世界TCP坐标与OBJECT_CONTACT语义区分明确，没有motion/error界、VALID或准入；消费者尚未改变。29新测试与含既有范围的93CPU回归通过；root独立29通过，另补MOVE_ABOVE/RETREAT实际registry参数转发与重哈希端点拒绝。见[独立参照审查](../t7b-native-calibration-source/task1-independent-review.md)。独立探针两次fixture错误保留，不作合格模块RED或物理次数。

本采集与上一轮outboard场景相同，是明确排除的开发衍生component；新名字不构成新独立校准组。见[开发来源关系](development-lineage.json)。该开发失败和前缀都不供校准、selection、test或正式统计。主线T12/18、T13并行，独立真实基本几何/完整动作窗口来源、连续/contact支持、风险、实际Max及INITIAL/METHOD/FINAL继续实施；边缘型号后置，formal_accepted=false。每一步经验证后按用户授权提交推送，并保留所有失败与排除。
