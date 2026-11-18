# Astra：仿真PLACE非平面标记深度的有界重观测

实际`gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED；因果输入SHA见JSON。规划仅只读，0GPU/API。

4336帧被原2mm门正确拒绝：中心3×3中位深度0.8121455908m，距四角SVD平面2.040551mm；四角自身最大残差0.159635mm。此前4328中心残差0.946512mm且该次恢复89.98ms；4336区域4角点有效。169项CPU通过属上版。最后joint4331，4336后两hold和estop，无新joint。不能据超出40.551μm便归因为噪声或放宽阈值。

## 明确选择与安全取舍

允许**仅显式component MuJoCo的PLACE**新增默认关闭策略：精确`marker_depth_not_planar`可请求不同相机的新帧。它改变的是何时最终STOP：在物理暂停、无新joint的最多两次备选/100ms内延后裁定。坏帧仍UNKNOWN且不产出可用pose；每个新帧仍必须独立通过原2mm、身份/尺寸/朝向、区域、TTL和SafetyShield才继续。此仿真等待不授予真机语义。默认路径、其它技能、初始构造/目标标记绑定失败仍立即STOP；不把全局marker rejection都改成可恢复。

## 实施与正反例

1. 重核原件，新增RED证明当前没有此显式策略；原4336 archived detector必须继续UNKNOWN，4328保持有效，原默认STOP保留为正控制。
2. 仅servo增加严格bool、defaultFalse的调用级/实例级策略，component已验证MuJoCo/role/asset的PLACE显式传入。匹配唯一精确错误，不用泛化startswith，也不设“接近2mm可恢复”的新宽限。复用既有候选排序，不改相机grid/评分/控制器/轨迹。
3. `_validate`先通过，测量拒绝时不得提交`_last/_accepted_marker/_last_target/accepted records`或更新proposal。只能使用本技能最近完整通过的4328帧及其observation/checksum/registration/calibration、允许FK提案；UNKNOWN pose不能参与。新相机独立标定与外参一致，新帧时效继续原门，旧图不能作当前证据。
4. 最多两次不同相机、每视角一次，期间物理步不推进、无joint；重复ID/相同视角不得重复采样碰碰运气。保存每个拒绝帧/原因及proposal来源，全部坏或deadline到期STOP。100ms必须包括proposal、换视角、采集归档、完整视觉和IK，不延长。
5. CPU负例覆盖default关闭、非PLACE/非component不获策略、持续非平面、marker过但region不过、身份/episode/source/标定/时间/朝向/invalid-depth错误、相同view/ID、坏pose/cache污染、物理推进/新joint及100ms超时。非精确planarity错误仍原样STOP，2mm边界与真实归档拒绝原样验。
6. 负例通过后只授权**1次**从初始场景开始的完整零API协议重放（原4Molmo/1Sol文本、模型/网络硬阻断），无额外冻结重建/离线grid/自动重试。必须8动作、独立物理成功、每次原2view/100ms及全量安全门成立，才可解冻原6真实额度。再有新失败交下一实际Astra。

## 边界与记账

pose_markers/servo_region阈值与判定、噪声、live RNG、TTL、worker120s、SafetyShield、controller/endpoint全不改。唯一完整重放使用EGL及原GPU锁独占，外层900s不扩worker。原native1FAILED/已耗1cloud4local及全部3952/4328/4336失败重放保存；新增这1次不论成败都留分母。原6cloud24local仍冻结、不追加，故障额度不作重试。软件重放不冒真实模型，formalNOT_ACCEPTED、qualified_groups_added0、真机NOT_STARTED。任何安全绑定无法证明、需要扩大错误分类/视角/阈值/期限或新失败即下一轮。
