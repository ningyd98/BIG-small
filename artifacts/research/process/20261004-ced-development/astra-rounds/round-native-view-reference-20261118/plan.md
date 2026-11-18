# Astra：相机候选方位基准修正

实际`gpt-6-astra`，PLANNED_NOT_FIXED。只读前提报告证实75mm side_y_plus为水平标记，attachment旋转I，直立法线XY=0；3944步实测法线XYnorm0.024649，方位−49°..+36°，不能作为稳定方位。物体中心到标记的注册偏移XY为[0,.14]m，实测世界方位89.12°..91.82°。前轮因前提触发正确暂停：重建0、渲染0、协议/网络/模型0。

仅替代[前轮计划](../round-native-current-view-coverage-20261118/plan.md)的方位基准，原计划冻结：按既有约定从当前已接受标记旋转与注册旋转求object-to-world，作用于完整注册中心→marker偏移t=[0,.14,.03505]m后取worldXY并归一化（保留安装高度的真实旋转贡献，不用不稳定法线或猜测world+Y）。逐frame绑定observation/checksum/SHA、原始测量旋转、object旋转、offset、norm、方位和候选顺序。要求注册资产/偏移合法、有限正交旋转，注册水平偏移非零且worldXYnorm≥注册水平norm一半（本组件0.07m）；不满足则停止，不改原marker准入。最近已接受几何仅可提案，不能替代新帧授权。

核对6项SHA后补方位刚体变换/非法偏移/退化/绑定测试，沿用四正交×0.80/1.05m、35°共8槽、各1帧、1次重建和1次完整replay。未消费额度不刷新、不新增：线上最多2次重采、sample+IK100ms、worker120s，几何/TTL/SafetyShield不变。原真实失败与旧两次replay失败保留，剩余6真实额度仅在继承的完整正反验证后恢复。此轮只修改proposal依据，不证明运行成功。
