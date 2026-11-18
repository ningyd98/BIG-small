# Astra：RETREAT clearance 的严格深度重观测

实际 `gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED。输入及原件 SHA256 见 plan.json；本轮规划 0 GPU/API。

唯一上一轮重放完成 PLACE/RELEASE，独立物理 SUCCESS（lift 0.105617m、hold 3.1875s、placed_stable 4.508333s、无安全违规），但 worker/component FAILED：空夹爪 RETREAT-clearance 在6518因 marker_depth_not_planar STOP。6510 sample69中心残差−0.401877mm有效；6518 sample70中位深度0.905639648m、中心残差2.248470mm、四角最大0.116521mm，区域仍有效。6518只有两次hold和estop。185 CPU通过属于上一版；物理成功不能改记worker完成。

代码显示RETREAT终点冻结且不用marker修正，但servo每帧仍先测marker。现opt-in只准PLACE，proposal只为MOVE/PLACE刷新，故当前STOP符合策略。没有证据可直接移除marker依赖；本轮选择保留验证链，将严格不同视角重观测**仅扩至显式component MuJoCo空夹爪垂直clearance**。横向RETREAT/default/其它深度或身份错误不扩。坏帧继续UNKNOWN，绝不按“噪声”接受2.248mm。

1. 重核SHA，先存CPU RED及原sample69/70严格检测结果；原默认STOP作为正控制。无须重建物理场景。
2. servo严格bool/defaultFalse策略可接受已注册RETREAT；component新调用必须同时核验当前task/step的VerticalClearancePath、冻结垂直终点、open且无holding、现有simulation/asset准入。不能只凭名称后缀。后续横向段仍关闭。
3. 为该显式clearance刷新现有解析候选，复用不变grid/ranking。只在本技能完整通过的当前sample和SafetyShield之后生成；绑定observation/checksum/calibration/registration及允许FK，技能开始重置。缺最近完整帧即STOP；不能借PLACE pose或坏帧。
4. 新视角各独立通过原2mm、身份/时间/标定/朝向/有效深度与SafetyShield。RETREAT原update不测region，因此恢复帧须额外独立验证原strict region支持后才提交接受；禁止以旧proposal角点代替当前证据。终点、工具姿态、控制器不变。
5. 原最多2次不同视角、每视角1帧、总100ms（含归档/proposal/safety/IK）不变；重采间物理步/时钟不推进，无joint。持续坏/重复view或ID/时间或身份错误/region或shield失败/超时均STOP。完整正反例见JSON。
6. CPU正反例通过后，仅1次完整零API协议重放，EGL+原共享GPU锁独占、模型网络硬阻断；0额外冻结重建/grid/GPU RED。原8技能及clearance和横向两段、终帧效果及独立物理和worker完成必须全部验证；不能只断言动作数8，因为拆段会增加动作条数。

原120s worker、外层900s、2mm/TTL/安全/正式门全不变，H1/P12/UTC不动。新重放不论成败计分母1，全部旧失败保留。原6cloud24local继续冻结；新失败或需扩至横向RETREAT则下一实际Astra，不能用物理SUCCESS解冻。formal NOT_ACCEPTED，qualified_groups_added=0，真机NOT_STARTED。
