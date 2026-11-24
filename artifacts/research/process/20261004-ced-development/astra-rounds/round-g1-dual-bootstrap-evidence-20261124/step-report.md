# 三次双标记启动资格验证

两个固定姿态的六张原始图都能解出相应标记。高位平桥第一次实测共 28 个零步控制，6 个正控均在颜色跟踪器建立起始物体轮廓时停止。原跟踪器检查完整外环中每个像素的光学深度，有 5/60 和 5/64 个像素违反严格深度条件。复拍与原包在颜色、深度和有效掩码上完全一致。6 次复拍共出现 30 个失败像素，实例分割将它们全部指向两条高位支撑。仅在诊断渲染中隐藏两条支撑，六次均恢复完整视觉启动。[逐像素因果对照](support-diagnostic-step.md) · [原运行清单与封存](second-generation.preservation.public.json)

第二次保留原高位平桥，在两个必要姿态及四个预登记备用姿态上跑完 76 个零步控制。71 个在原颜色外缘深度检查停止，1 个没有识别到已知标记，4 个按设计拒绝错误登记。三个正控条件均未取得一条完整的在线抓取目标，未发放运动槽。[76 个控制的独立读回](third-generation.independent-outcome.public.json) · [原始资格](third-generation.zero-step-probes.public.json)

第三次采用计划限定的低位 L 形支架，保留原相机、码与印刷板位置、颜色跟踪、动作控制和 SafetyShield。质量 100.78432 g，正向运动学复核了 132 对结构净距，最小保守下界为 52.00 mm。对两个预定姿态分别验证双码可见、仅 ID7 可见和仅 ID8 可见，6/6 从实际 RGB-D 经初始物体识别、登记目标、V2 和伺服产生目标，实测抓取点与真值的距离为 0.77–4.09 mm。两姿态中各 11 项负控按对应原因拒绝，合计 22/22。整轮资格观测的物理步进与运动派发均为 0。[装配验证](bracket-development.public.json) · [同姿态改型前后的外环与目标对照](bracket-qualification.public.json) · [全部正负控逐项结果](../round-g1-first-refusal-dual-marker-20261124/zero-step-probes.public.json) · [独立像素读回和有效装配](../round-g1-first-refusal-dual-marker-20261124/zero-step-readback.public.json)

只有低位支架通过启动资格后，才为四对全新摆放发放运动槽。完整抓放的在线结局与独立物理成功率见主报告。[八槽分配读回](../round-g1-first-refusal-dual-marker-20261124/allocation-readback.public.json) · [G1 主报告](../round-g1-first-refusal-dual-marker-20261124/step-report.md)
