# Astra：真实模型搬运区域观测失败的限定计划

实际模型`gpt-6-astra`，2026-11-18，**PLANNED_NOT_FIXED**。工作树`/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`；当前commit和输入SHA见`plan.json`。与UTC独立分轮，不互相替代证据。规划阶段只读原件、查看归档RGB，没有运行GPU/模型/实验。

## 原始失败

`native/fixed-01`实际4次Molmo2-ER＋1次gpt-6.1-sol，规划成功；目标原生归一化[573,460]→像素[183,110]，关联[180,119]；区域[404,306]→[129,73]。第5动作MOVE_TO_REGION从3112到3952物理步，840步后STOP：`servo region geometry unavailable: region_missing_color_not_explained_by_foreground`。抬升0.1056172488m、保持3.1875s、放置稳定0s，physical_success=false，绝非完整抓放。

原result、component/episode、planning两阶段、全部Molmo请求与Sol原字节、初始/最终关键paired帧均SHA绑定。fixed-01永久保留FAILED和已消费1cloud/4local；不重试、不换seed、不重新宣称3/3。

## 已有证据和待验证根因

- step05在3272步总览区域边缘检查失败后切左侧并继续；3952步左侧标记不可用，切右侧后区域证据失败。归档仅`sample-0105`和`sample-0105-view-01`，同一sim_time16.466666666666054。
- `_transport_camera_position`生成总览、左、右三个候选。`servo_sample`给MOVE_TO_REGION传`camera_views[1:]`，丢掉总览。`update_with_camera_views`本来允许最多两次换视角并会排除初始视角，故这次只用一个替代后无候选。
- 窄修复假设是恢复已有总览候选可在不增加预算的条件下获取合格当前帧；还未证明。不同真实定位点改变了轨迹/视角条件；不能因为旧stub区域像素可能129,72就把真实点人为吸附到旧点。
- 最终右帧的缺色像素可能是实质缺证据、前景/平面混色、投影栅格或其它几何。RGB肉眼不能证明深度支持；不授权放宽任何几何谓词。

## 实施步骤

1. 重新核对原件与因果源SHA。建立零模型/零网络协议重放：4个Molmo原文和1个Sol原响应完全使用归档值，协议边界绑定到新场景实际RGB/phrase，并核对初始和云后RGB与原输入一致。SQLite、MuJoCo、OpenCV、worker、controller、SafetyShield仍实际执行。标记`MODEL_PROTOCOL_REPLAY_NOT_REAL_MODEL`。先原源码RED复现同一步、同类可见性拒绝；若不复现，停止猜测修复并回实际Astra。
2. 对归档最终paired帧及tracker初始参考做离线逐像素诊断：投影四边形、当前色彩/平面支持、三角点以上锚点、缺失mask、valid-depth、worldZ/像素footprint、高前景/低侧壁/混合边缘，列出不满足条件的像素RGB/depth/高度/标定与计数。标签仅可离线解释，不进Agent。原右帧必须继续被原严格几何拒绝；不能通过补绿mask/忽略孔洞让它变通过。
3. 最小改动`sol_molmo_components.py`候选接线：MOVE_TO_REGION可使用已经生成的完整`camera_views`，保持既定优先序、过滤当前视角、最多2个替代、同一sample期限。优先一致地传完整候选而非增加新相机策略。只在当前失败后重新采集总览；旧总览图像/区域中心不能替代当前证据。每个新视角独立通过现有update、几何、标记、TTL、标定和SafetyShield后才发下一关节目标。
4. 增加直接覆盖候选接线的测试，跑原生点完整零API GREEN和负例：两侧失败总览新帧有效则继续；全部无效则停止；相同视角去重；最多2次换视角；失败采样与恢复间物理步不推进、无新目标；非可恢复身份/朝向/深度/时间错误立即停止。原stale/future/gap/calibration、coplanar/background/invalid/detached-hole/two-corners/marker反例不变。GREEN须真实MuJoCo独立物理完整抓放通过，仍只算协议重放开发证据。
5. 上述正反例通过后，恢复原剩余6个真实episode：fixed-02、fixed-03、44101..44104 development。每例仍1cloud/4local、0repair/0retry、worker120s。fixed-01失败不重跑不替换；最终按原7例分母及实际源码版本分层报告，修后子集单列，不称原批3/3。

## 范围、预算与前提

允许component候选接线、针对性测试和派生诊断报告；servo/servo_region如需仅加不改变判定的诊断。几何谓词、相机位置/标记安全界、tracker身份关联、TTL、sample期限、2次换视角上限、SafetyShield全保持。`camera_positioning.py`本轮只读。恢复总览仍失败或需要更改几何/相机策略时，本轮立即收口事实，下一轮实际Astra再计划。

计划阶段0GPU/0API。实施零API原RED最多1次、修后完整GREEN最多1次，0模型载入/生成/网络，worker120s、外层900s含准备；负例以现有CPU/模拟测试运行。MuJoCo渲染所需GL/GPU锁按原规则准入，与模型运行串行。不得因名为零API而跳过GPU资源约束。离线旧帧可以显式历史采集时刻计算，但不称在线TTL验证、不修改原timestamp。

真实剩余额度6cloud/24local/6load；原3个故障额度仍单列保留，不能补本失败或当重试余额。起始场景/相机[0.35,0,1.35]/75mm既定标记/资产hash固定。H1纯搬移准入helper和唯一import若并行发生，记录diff/hash并确认无逻辑改变即可，不误判为本几何根因；components/servo/tracker/asset变化则须重核计划。

## 验收和停止

完成仅指明确范围的软件修复与新证据；正式NOT_ACCEPTED、qualified_groups_added=0、真机NOT_STARTED。原始失败/原字节/旧协议替身结果均保留。步骤报告保存命令、版本、重放来源、像素诊断、几何拒绝负例、动作停止/独立物理证据和真实剩余预算。

RED不复现、总览仍不合格、新根因、范围扩大或计划外回归失败即暂停相关修复，交实际Astra下一轮。UTC、H1、Phase12独立工作可继续。
