# Astra：PLACE复用当前视角排序

实际`gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED。输入SHA见JSON。本轮读取实际新paired帧、源码和159 passed/3 deselected旧回归；未运行GPU/API。

根因已核实为两处接线限制：`ranked_proposal`每技能重置None，只在MOVE_TO_REGION已接受帧后刷新；`prioritize`又只对首帧marker unavailable启用排序。PLACE首次错误是region_color_boundary_depth_unresolved，而且后续错误不会再次调用attempt0的prioritize，因此继续旧总览→左→右，无新候选。新重放已经通过3952并在4192完成MOVE，却在PLACE4328失败（最后有效4320，6动作，放置稳定0）。总览边界深度未解析、左丢标、右179缺色像素不满足前景，全部继续拒绝，不改像素门。4328后仅换相机、两hold及estop，无新joint。

## 最小实施

1. 先新增RED覆盖真实接线：PLACE已接受帧不刷新proposal、区域首错绕过解析候选。旧完整重放失败已足够作原始RED，不再为复现消耗一轮完整运行。
2. 仅在component把现有刷新条件扩为MOVE_TO_REGION与PLACE，并让现有prioritize对servo已经列明的可恢复区域错误也生效。保持既有首候选→解析排序候选→其余顺序及去重。每次proposal来自本技能最近**完整接受**帧的marker/observation/checksum/registration/calibration与允许机器人FK；失败帧、跨技能旧cache、教师对象pose/instance mask不能提供授权。无合格proposal仍原样停止。
3. 参数化MOVE/PLACE及现有4种可恢复原因，验证真实callback接线、首旧候选后排序第二候选、最多两次、全坏STOP。非法depth/identity/orientation/stale/calibration仍立即停止；旧region反例不变。相机grid/方位/高度/评分算法、PLACE初始总览切换、控制器/轨迹端点均不改。
4. 如需诊断，最多1次零API恢复4328，冻结独立离线物理状态；先从4320已接受frame与允许FK解析列出候选顺序，再只渲染最多2个不同有效排序候选，各1帧。不开新grid、不重复随机深度、不继续运动；所有拒绝也归档。若没有严格marker+region共同合格视角或出现新根因，停交下一Astra，不通过完整重放碰运气。
5. 相关负例通过后，仅1次新完整原生协议重放（原4Molmo/1Sol文本，模型/网络硬阻断），从初始场景跑8技能并独立物理成功，所有新帧、安全、两次/100ms门都通过才恢复原剩余6真实quota。新完整重放再失败即下一Astra。

## 预算与边界

本轮规划0GPU/API。实施最多1次4328状态重建+2离线帧+1完整协议重放，0真实模型/API；实际在线仍最多2重采、包含proposal/采集归档/视觉/IK的100ms，worker120s/外层900s。renderer必须EGL和原GPU锁独占；CPU回归保留原GL deselection，若含GL必须同样准入。

原native1FAILED/已花1cloud4local、旧3952两次replayFAILED、最近4328 PLACEFAILED全留；旧8槽5BLOCKED/2markerUNKNOWN/1VALID不改，新≤2槽单列且不作任务成功率。6cloud24local剩余额度未动、不新增、不重试。所有几何/TTL/SafetyShield/评分/控制器/轨迹保持；formalNOT_ACCEPTED、qualified_groups_added0、真机NOT_STARTED。需要不同grid/排序算法/边界pixel规则或突破2次/100ms等范围即下一实际Astra。
