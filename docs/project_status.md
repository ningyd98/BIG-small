# 项目状态

## 2026-11-26　三项研究目标的证据核对

| 目标 | 目前可核验的结果 |
| --- | --- |
| 受控桌面中正确识别且深度有效的目标，三维定位 P90 ≤ 10 mm | 正式固定摆放批次通过此数值门限。原单标 2.676 mm（376/384 帧有效），低位双标 2.765 mm（386/394 帧有效）。正式像素和物理评分均由冻结输入逐字节复现。 |
| 标称静态单步独立抓放成功率 ≥ 90% | 原正式批两臂各 0/4，较新的完整开发批 0/2。静态抓放、抬升诊断、开爪静态复采和多步扰动分别记录。 |
| 同等任务质量且成功率不降低，远程请求相对固定周期减少 ≥ 30% | 当前合格的固定周期基线及正式配对结果缺失。分配预检复现 120 组 × 4 周期，480 个均未执行。现行源码的角色探针等待图像外发和付费授权。 |

[正式定位与抓放计分](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-formal-paired-20261124/step-report.md) · [t01 前缀与 27 条制停分支冷读](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-t01-joint-stop-readback-20261126/step-report.md) · [B0 前置复验](../artifacts/research/process/20261004-ced-development/astra-rounds/round-b0-current-role-probe-20261126/step-report.md)


当前有载门对封存 t01 第 1640 步给出 CLEAR。源台有载制停界下左右指尖离桌保守下界约 12.62 mm，16 个原包络各通过登记体积检查。t02 原轨迹在当前门中首个拒绝为第 1512 步缺少有界工件姿态，第 2112 步仍有未登记近面。两例共复验 85 个封存角色，新增曝光、积分和整机各零次。[^g1-volume]

[^g1-volume]: [当前有载门与独立冷读](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-lift-registered-volume-20261126/step-report.md)


G1 完整训练的整套守护准入仍缺证据，t01 新训练停在分配前。保持工具位姿扫描 70 个登记静态姿态后，B 的 ID7 最多多见 32–34 个面点，遮挡侧仍为 0 个合格深度边缘列，最清晰格仍与旋转后的 ID28 相容。t02 的两侧理想深度列均为 14，实际原图的姿态拒绝须继续按光学证据定位。[^g1-posture]

[^g1-posture]: [t01 派发前审查](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-t01-native-training-20261126/step-report.md) · [静态几何对照](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-fixed-tcp-id7-geometry-20261126/step-report.md)

在同一固定工具位姿的 IK 分支上，九个 B 释放状态各自向两侧延拓到 60° 名义关节弧长。正向 48° 至 60° 的七个公共检查点均让可见码格只兼容原 ID7。全 549 个登记状态的遮挡侧仍无合格的理想深度列，双侧释放资格未建立。[^g1-branch]

[^g1-branch]: [固定 TCP 分支几何筛查](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-fixed-tcp-branch-visibility-20261126/step-report.md)

九张 B 基准原生 RGB-D 逐像素复现，+48°、+60° 两组各九张均只检出 ID8，遮挡侧没有合格边沿，未获得 RELEASE 姿态、支撑及双侧净空证书。[^g1-branch-native]

[^g1-branch-native]: [固定 TCP 分支原生复采](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-fixed-tcp-branch-native-20261126/step-report.md)

t02 第 1512 步保持同一归档曝光、命令及历史，两个只代入独立物理姿态的反事实均恢复 `held`，完整净空读回均为 `CLEAR`。原光学分支仍为姿态缺失。第 2112 步的未登记近面未改变。此次仅用 12 次机器人参考深度投影核对拒绝链条，整机及正式分母未增加。[^g1-t02-oracle]

[^g1-t02-oracle]: [t02 首拒反事实及封存摘要](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-t02-pose-oracle-20261126/step-report.md)

t02 第 1512 步唯一有注册深度及印刷支持的邻列，在两个像素中心之间的度量残差跨度下界为 5.164 mm，超出原允许的 3.800 mm。两侧 16 个原 RGB 锚点的点估计仅供诊断，未签发新证书。[^g1-t02-bracket]

[^g1-t02-bracket]: [深度区间冷读与独立标签比较](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-t02-depth-bracket-20261126/step-report.md)

对六条已披露轨迹及 t02 原抬升做四列 RGB 缩减冷读，2,502 个裁剪中 548 个超出原包络。唯一一个非目标自然匹配也超出。所有超界均涉及 X/Z 轴之间的俯仰项，现有固定平面估计未获姿态资格。[^g1-t02-reduced]

[^g1-t02-reduced]: [四列 RGB 跨轨迹验证](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-rgb-edge-reduced-20261126/step-report.md)

使用原保留锚点的同平面实测深度重拟合后，2,504 个冻结配对均落在原诊断包络内，549 个俯仰越界全部恢复。t02 第 1512 步角点误差为 0.273 mm。自然匹配只有一条非目标轨迹，仍缺更多独立开发样本。本轮未新增场景曝光或实际抓放。[^g1-t02-plane]

[^g1-t02-plane]: [配对平面重拟合](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-rgb-edge-plane-refit-20261126/step-report.md)

G2 软件已同时保留原逻辑云指标和远程派发指标。派发前注入丢包计零，已派发的超时和重试逐次计入。正式结论仍需合格的固定周期基线与实际配对成功结果。[^g2-dispatch]

[^g2-dispatch]: [远程派发归属验证](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g2-transport-dispatch-20261126/step-report.md) · [原始收发文件与尝试身份读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g2-original-wire-identity-20261126/step-report.md)

## 2026-11-24　G1 正式抓放失败的逐帧归因

复看正式批的 778 帧后，六次失标均定位到夹指或手掌侵入标记白边附近的姿态。逐部件隐藏的静态复拍均能恢复识别。另两次能读出双码，但 ID8 的偏航估计误差约 5°，经安装偏距放大后触发抓取点一致性检查。四个摆放的正式完整抓放成功仍为两组各 0/4。[阶段总结](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-formal-failure-observation-20261124/stage-summary.md) · [逐帧慢放](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-formal-failure-observation-20261124/eight-stops.gif)

## 2026-11-24　G1 单标与低位双标的四对正式仿真

在登记提交 `8d946b58` 推送后，四个新摆放完成 8 次独立 MuJoCo 运行，每个组合各运行一次。进入接近阶段的次数为原单标 0/4、低位双标 2/4。另两次双标在上方移动时停机，两个标记各自估计的抓取点相距 13.391 mm 和 10.664 mm，超过登记的 10 mm 上限。按独立物理评分，两组完整抓放成功均为 0/4。778 帧经两个进程独立读回，有效帧中物体顶面中心的三维定位误差 P90 分别为 2.676 mm 和 2.765 mm。G1 的 90% 成功率指标仍未达到，正式教师 v10 本轮消耗 0 次。[正式配对报告](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-formal-paired-20261124/step-report.md)

## 2026-11-24　G1 首拒归因与低位双标抓放

8 个历史试次的最后有效姿态均能从 +X、+Y 两侧定位。8 步后的首拒姿态有 4 个仅 +X 可用、4 个仅 +Y 可用；同姿隐藏手与双指，8 个失标侧均恢复识别。低位双标和原 +Y 单标随后在四对新摆放中各独立运行一次，双标有 3/4 进入接近，单标为 0/4。双标在接近时有 65/67 帧可用，两次失去两码，一次左夹指碰到 ID7 载板并触发硬停止。两臂独立完整抓放均为 0/4，G1 的 90% 指标仍未达到。正式仿真新增 0 次。[首拒证据与逐组抓放结果](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-first-refusal-dual-marker-20261124/step-report.md)

## 2026-11-24　G1 标记安装与静态抓放

同一顶视相机下，在 8 个历史停机姿态中，将标记从方块 +Y 侧移到 +X 侧，可用抓取点从 0/8 增至 7/8。两种安装随后在四个全新摆放中各运行一次，独立物理抓放成功均为 0/4，8 次都在首个上方移动动作失标停机。原安装与 +X 安装全程可定位帧的物顶误差 P90 分别为 3.111 mm 和 2.445 mm。G1 静态抓放的 90% 开题指标尚未达到。本轮新增正式运行 0 次。[逐组结果与阶段诊断](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-marker-mount-20261124/step-report.md)

单独从历史固定 TCP 成功轨迹恢复 7 个名义场景姿态，接近阶段两种安装均在 3 个姿态中有 2 个可用，闭爪与抬升均为 3/3。8 个新试次都在接近前停止，后三阶段尚无新摆放的在线观测。[逐帧来源与姿态核验](../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-marker-mount-20261124/phase-reconstruction.public.json)

## 2026-11-24　开题指标与补做实验

静态抓放在 13 个新增开发摆放上独立复位运行 22 次。按分配计，完整通过在线动作与独立物理评价的有 0 次。另做了 4 次固定动作时效实验和 4 次故障恢复实验。v10 正式教师仍只有首组运行过，9 个登记组中合格 0 组。G1 至 G4 均未取得开题验收所需的结果。[逐项实测、分母与缺口](../artifacts/research/process/20261004-ced-development/astra-rounds/round-proposal-experiment-qualification-20261124/stage-summary.public.md)

## 2026-11-24　毕业论文篇幅与印本

七章论文长稿已按 3–5 万字要求扩展。正文叙述 33,326 个汉字，Word 的中英文合计 42,499 字词，PDF 共 38 页。可从同一入口取得两种格式、逐章字数、最初的 26 页稿和研究原始结论。[论文与复现入口](thesis/graduation-20261123/README.md)

## 2026-11-23 毕业设计工程与研究进展

面向边缘智能场景的小型机械臂云边协同系统已提供可安装的 Harness、可复算的演示、七章论文和答辩稿。离线安装在新的 Python 环境内通过配置、准备和原件读回，篡改一个字节和重复使用输出目录均触发拒绝。[毕业设计与运行入口](thesis/graduation-20261123/README.md)

本轮在 MuJoCo 中完成 6 个开发摆放、54 个独立重置、324 帧 RGB-D 采集。三组留出摆放的 SUBPIX 顶心估计有效 159/162，条件三维误差 P90 为 6.869 mm，最大为 10.991 mm。软件对照中，同一故障下局部修复改写 1 个待执行步骤，完整剩余重规划改写 2 个，两条路径重启后重放都没有新增网关调用。[视觉盲评](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/perception.public.json) · [决策与恢复对照](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/decisions.public.json)

固定 TCP 的开发抓放在 5,013 个物理步完成。独立读回保留全部 5,014 个状态，抬升后半秒和释放后一秒两个规定窗口分别有 121/121 和 241/241 个采样满足条件，另有五个保护反例通过。全仓软件选择的 7,682 项中，首轮 7,235 通过、366 失败、50 错误、31 跳过；相对历史新出现的五项失败在同源码串行复验时均通过。[物理正反例](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/physics.public.json) · [回归范围和逐批次结果](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/full-validation.public.json)

原 v10 正式首组的 LIFT 后置判定保留为 UNKNOWN，余下八组未运行。历史同版 20 个新开发位姿独立物理成功 5 次。正式 B0 筛选及其后的对比试验仍待满足资格前置。[正式首组记录](../artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase6-20261122/validation.public.json) · [各项指标的验收状态](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/requirements-evidence.public.json)

新的 r593 开发实例通过首动作的真实条件检查和 SafetyShield，在第 120 至 848 步完成 728 步运动。第 840 步仍能识别标记 ID 7，第 848 步的反馈和终止图像均无法识别它。伺服回报拒绝，安全停止成功，后续七个动作未派发。[r2 逐步、图像与控制回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-guarded-clock-20261123/vision.public.json)

## 2026-11-21 教师状态检查修复与复测

同一开发位姿 `11920067` 的首动作从 **150.403 秒降至 128.739 秒**，少用 **21.665 秒（14.4%）**。修复的是单次检查内重复的作业查询、冻结协议解析和同一 worker 的只读建连。动作窗内的 31,238 次活动检查全部保留，检查本身及其 SQLite 读取由 78.719 秒降至 50.771 秒。软件负控验证了取消、租约到期及急停仍在原检查点拒绝。 [修复与实测](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-checks-20261121/step-report.md)

两个独立实例的 2,040 步控制载荷及步后状态全部对齐，3,385 帧的 RGB、深度、掩码和实例文件逐帧一致。控制和保持都到达原终点，POST 仍因超过原 8 秒墙钟门限返回 `STEP_TIMEOUT`，后续七个动作未派发。正式合格组 **0/9**，B0 selection 等待首个合格组。本轮各项原件已校验并持久留存。 [物理对照](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-checks-20261121/physical-comparison.json) · [复测回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-checks-20261121/retest-measurement.json)

本轮扣除全部活动检查后，其余工作仍用 77.967 秒。采集端 36 帧先导测得两处重复计算，按全窗帧数理想外推约 6.28 秒。后续原 8 秒资格开发需同时量化渲染、编码和证据复制的成本。 [未决耗时与负载](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-checks-20261121/feasibility.md) · [采集端离线配对](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-check-repair-20261121/residual-pilot.md)

## 2026-11-21 教师动作实测

教师首动作 `MOVE_ABOVE` 已在新的 MuJoCo/EGL 开发实例中完成 1,920 个物理步。从 PRE 到 POST 的实际墙钟为 **150.403 秒**。控制器在 45.621 秒内用 725 步到达目标，保持再用 103.913 秒、1,195 步。终点位置条件通过，实际用时超过原 8 秒门限，安全盾返回 `STEP_TIMEOUT`，后续七个动作未运行。正式教师资格仍为 **0/9**，B0 selection 继续等待首个合格组。 [本轮轨迹与停止位置](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/step-report.md)

独立读回两遍均核对了 3,385 帧、8,813 次渲染及最终急停命令。本轮一次运行，零重试、零任务模型调用。原动作窗内有 31,238 次活动状态检查。这些检查扣除 SQLite 后占 46.546 秒，SQLite 读取占 32.172 秒，两项合计 78.719 秒，占动作墙钟的 52.34%。同位姿的修复复测见本页上方。 [独立物理读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/independent-physical-readback.md) · [计时分解](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing.md)

## 2026-11-20 项目组状态

BIGsmall Embodied Harness 已交付 H0/H1 工程开发版，冻结首场景契约并通过清洁环境安装、七条 CLI 正常路径和两条保护拒绝检查。历史四位姿冻结于 `5103e7f4`，本轮新增开发位姿冻结于已含 worker 异常留痕的 `4bdb64eb`。教师单组入口与采集优化另在研发分支 `research/harness-candidate-20261118` 交付。云端负责规划，边缘按规则和成本约束判断，端侧用 OpenCV/RGB-D 观测，沿用可见姿态标记、顶视相机、现有控制器与安全盾。边缘模型选型后置。 [现行计划](plan.md) · [公开交付范围](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/public-delivery.md)

冻结版首次整库收集 7,259 项，7,225 通过、33 跳过、1 项 dispatcher 清理错误，原判定为 `passed=false`。同版在原测试夹具下独占复验该节点通过，退出 0。 [回归、安装与固定场景回放](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/regression-and-install.md)

### 四个同版本 MuJoCo 开发位姿

四例各运行一次，组件完整执行 **1/4**，独立物理成功 **1/4**，物理记录中检出安全违规 **0/4**。本批实际有 3 次付费云请求（GPT-6.1-Sol）、14 次本地生成（Molmo2-ER）、4 次加载、0 次重试，账单金额未知（`null`）。 [四例报告](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-four-fresh-positions-20261118/final-batch-report.md) · [逐槽机器回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-four-fresh-positions-20261118/final-batch-summary.json)

| 位姿 | 结果与原因 |
| --- | --- |
| `2026111801` | 放置阶段第 5400 步，采样与逆运动学耗时 100.041 ms，超过原 100 ms 门，触发保护停止，未形成稳定放置。 |
| `2026111802` | 全部动作执行完成，两段退避结束，终帧观测到已登记标记。独立物理复算确认稳定放置 9.475 秒。 |
| `2026111803` | MOVE_ABOVE 初始化停止，尝试 1 次、执行 0 次。在线 worker 只记录 `ValueError`。冻结帧和同版构造器离线复算显示，规划抓取点与标记配准估计相差 30.882 mm，超过原 10 mm 身份门。 [初始化前缀复核](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-fresh-1803-initialization-prefix-20261118/step-report.md) |
| `2026111804` | 压力位姿的两个本地点位均返回。现有归档复算的目标顶面高度跨度为 8.027 mm，超过原 8.000 mm 门。初始规划请求更多观测，云请求和动作均为 0。 |

历史开发位姿四例仍为组件完成 1/4、独立物理成功 2/4。含这四例的跨版本历史七例分别为 3/7 和 4/7。 [历史七例独立复算](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/native-seven-verification.md)

### 三例归档复核与 worker 修复

三例全部从 `5103e7f4` 的冻结 RGB-D、标记和执行原件重建，零新增模型调用。九份确定性结果经独立复算逐字节一致。 [输入与完整读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/step-report-v2.md)

| 位姿 | 找到的首个差异及处置 |
| --- | --- |
| 1803 | 原指点 (173,120) 通过 3×3 颜色检查，距登记顶心 6.237 像素。反投影后已出现 30.848 mm 的 TCP 横向差，全三维差 30.882 mm。1802 的关联将偏差从 8.836 像素降到 0.329 像素，最终 3.059 mm。两条路径均复现相同的刚体配准，物理成因为 `UNKNOWN`。 [登记叠图](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/derived-v2/1803-1802-registered-identity.png) |
| 1801 | 两例各有 143 个单主视图接受样本。1801 两次启用备选视图时，视觉处理 47.664 ms、捕获归档 29.716 ms、移机 10.153 ms，最终 100.041 ms 触发保护。最近系统采样在 4.155 秒后，1/5/15 分钟负载为 1.26/1.97/4.08。身份、时间、顺序和安全检查需同步完成。大文件异步写入仍需证明哈希登记可恢复、有界回压与落盘完整性。 [视图与分项耗时](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/derived-v2/1801-place-timing.json) |
| 1804 | 205 个支持像素中，147 个核心像素跨度 4.845 mm，203 个顶面像素跨度 8.0266 mm，原门限为 8.000 mm。两个极值都在有 RGB-D 过渡的边界。表面起伏、混合像素或遮挡的物理归因仍为 `UNKNOWN`。 [极值与 5×5 深度邻域](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/1804-extrema-neighborhood-depth.png) |

worker 自产品提交 `4bdb64eb` 起，把脱敏后的异常类型、消息、堆栈和阶段写入 episode。原停止条件沿用。定向回归 34/35，余下一项成功路径在同源独占复验通过，原 113.520 ms 超限记录保留。 [异常原件与回归](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-worker-exception-20261119/step-report.md) · [同源独占结果](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-worker-types-exclusive-deadline-20261119/step-report.md)

### 修复后开发批次

在首个 BEGIN 前公开冻结 20 个新位姿（15 个常规、5 个遮挡压力位姿）和同一 1802 位姿的两次独立复测。全部分配使用产品 `4bdb64eb` 和清洁安装包 `96ff9e22`。20 个新 seed 与历史、教师及 B0 六池核对互斥，固定复测单列。每个分配最多一次云请求、四次本地生成，零重试。 [逐例预登记](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/development/preallocation/allocation.json) · [启动前冻结](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/development/live-freeze-public.json)

22 个分配均已按顺序结束，每个分配有唯一的开始和终态回执。新位姿的两项指标由不同原件独立核对，分别以全部 20 例为分母。 [逐例结果与费用](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-hard-limit-prefix-resume-20261120/final-batch-report.md)

| 验证口径 | 20 个新位姿 | 固定 1802 位姿的两次复测 |
| --- | --- | --- |
| 九个组件动作完整执行 | 5/20，25.0%，95% Wilson 区间 11.2%–46.9% | 2/2 |
| 独立物理判定稳定放置 | 5/20，25.0%，95% Wilson 区间 11.2%–46.9% | 2/2，两次均稳定 9.475 秒 |
| 冻结 Harness 三层均正常返回 | 3/20 | 2/2 |
| 独立物理读回发现安全违规 | 1/20 | 0/2 |

原严格审计直接读回 17/20 个新位姿。第 11、19 例的原结果超出冻结版 8 MiB 读入上限，原包装均为 `INCOMPLETE_UNKNOWN`。从完整原件补充读回，二者均完成九个动作并稳定放置。第 18 例的动作和独立物理两项均失败，右指越过含容差上限 0.158 mm，已触发急停。其原包装退出保留，单独复核动作前缀和安全事件。预登记的全样本严格评分缺三份原严格审计；表中两个区间使用补充原件在内的完整 20 例。按原场景分层，常规可见位姿为 5/15，预登记的机械臂遮挡压力位姿为 0/5，其中 4 例止于初始规划，1 例止于身份核验。15 个失败中有 6 个初始规划拒绝、6 个视觉伺服拒绝、2 个初始化异常、1 个硬指限位。两次固定复测单列，样本量不足以估计整体运行方差。 [第 18 例安全原件核对](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/development/live-18-finger-safety-diagnosis.json) · [大结果文件读回修复](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-large-result-reader-20261119/step-report.md)

新位姿实发 14 次云请求和 68 次本地生成，共 9,339 个云端 token。两次固定复测另计 2 次云请求、8 次本地生成和 1,324 个云端 token。全批共 22 次模型加载，零重试；16 条付费请求均可与供应商用量核对，账单金额及币种待回执。

### 教师、B0 和交付环境

教师按预登记实际释放首组 `native-p0-20261119-0001` 一次。PRE 通过，首动作 MOVE_ABOVE 在 740 个物理步后执行返回，随后保持 1,180 步。POST 读到 332.829 秒，超过原 8 秒限额，触发急停。独立生产 reader 重建 3,373/3,373 帧，验收完整动作 0/8，首组部分采集，后八组未启动，资格 0/9，联合误差界为空。诊断阶段的采集复制优化曾在原 8 秒内将同姿态进度从 181 提至 391/1920 步。 [真实首组与独立读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-first-actual-v9-teacher-20261119/step-report.md) · [采集复制优化](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-capture-detach-20261119/step-report.md)

另用独立新 seed、真实 worker、SQLite 租约与 EGL 相机测量 8 秒开发短窗。99/1,920 个首动作物理步在窗内完成，独立 reader 核对 242/242 帧。动作窗 1,331 次 SQLite 快照共 1.345 秒，117 次窗内完整采集的 owner 区间共 3.042 秒，两个统计有重叠。末次采集在截止前获准，截止后 29.226 ms 被原检查点拒绝，随后保持并急停。原件记录到第 219 步，停后生效步的独立物理状态未知。开发短窗零模型调用。正式组沿用原 8 秒和逐步采集要求。 [独立读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-checkpoint-egl-development-20261120/independent-readback.md) · [窗口和负载](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-checkpoint-egl-development-20261120/step-report.md)

对开发短窗的 242 个归档 RGB-D 帧另做 CPU 配对。四轮里，PNG 压缩级别从 6 调到 1，使这一段记录写出路径的累计墙钟从每轮 2.319–2.331 秒降到 1.747–1.757 秒，降幅 24.28%–24.87%。完整原件体积增加 0.99%。968 对的像素、深度、标定和身份均等值，PNG 字节及依赖摘要发生变化。单看与 8 秒窗对应的 117 帧，四次离线写出各节省 0.273–0.283 秒。离线跨接口复核中，两端同用级别 6 或同用级别 1 均通过全部 242 帧。两份显式采集经原会话回放。两种混配以及把同一物理步的两个采集互换，均遭原反馈和 PRE 消费者拒绝。该对照选定了两端一致的编码策略，11 月 21 日的完整动作实测见本页顶部。 [逐帧 CPU 对照](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-action-window-next-20261120/step-report.md) · [两端编码与 PRE 反馈复核](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-action-window-next-20261120/cross-interface-readback.md) · [后续开发方案](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-action-window-next-20261120/next-development.md)

B0 配置已经绑定 3,260 个互斥分配和名义角色探针。探针 4/4 实发成功，零重试，共 3,073 tokens。协议准备入口现可直接导入这六池。持久目录中的逐项读回确认 3,260 行、2,400 个候选与 200 个恢复调度对应同一池锁。原 reader 判定完整性、拓扑通过，当前池的实证仍是恢复 0/200、机会 0/2,400。历史的 1/200 恢复及三份与本池精确匹配 0/3,260 的旧协议单列。正式 selection 等待教师资格，`selection_evidence` 和 `protocol_evidence` 仍待真实原件。用户已授权 B0 及新增开发批次的付费次数和金额无上限，实际账单金额及币种待供应商回执。 [B0 台账](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/b0/step-report.md) · [冻结池及协议独立读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-protocol-frozen-pools-20261120/step-report.md)

文档治理的 25 项问题已清零，8 项治理测试通过。三套历史冻结检出和安装包已迁至私有持久目录，原入口验证通过。主工作区 `config.py` 的一行改动已单独备份并恢复至 Git 基点。本轮先在研发分支交付，选定合入提交并完成同版回归及相对公开 main 的完整范围复审后，再合入 main。 [文档治理回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/governance/step-report.md) · [冻结迁移及 main 决定](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-freeze-directory-mode-20261119/step-report.md)

## 2026-10-04 历史分阶段开发状态

当前权威状态入口为 [current_authoritative_status.md](current_authoritative_status.md)。Phase 11 仿真工作台已接受，Phase 11.1 异步运行时已接受，Phase 11.2 Model Control Center 和 Simulation AI Console 已接受。Phase 12 是最终实验评估、论文证据整理和项目软件/仿真封板阶段。Phase 10 仍保持 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`、`PHASE10_2B_CONSOLE_ACCEPTED` 和 `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`；这些状态都没有发送真实硬件执行命令。

2026-10-04，T5夹爪修复已迁移到默认运行入口、模型工厂、启动环境、研究配置和任务语义证据。当前使用v2标定与[共用冻结包](../artifacts/research/process/20261004-gripper-project-migration/model-probe/model-frozen.json)；下文T3/T7冻结和在线指标属于历史验收时点。旧模型配置及原实验仍保留在各证据目录，不以新资产覆写。

当前按 [RGB-D 代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)完成 T1/T2/T3/T6a/T4/T5：100/1000组静态数据、当前资产6/6类真实 MuJoCo 物理技能、20例离线教师各有独立验收。T3 的本地 Qwen3-VL 4B 经归一化坐标协议和顶抓几何适配，固定场景4/4通过并冻结；独立开发场景及拒答失败见[T3 验收](../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)，不代表在线抓取成功。T7 为 `DONE`：同 episode 真实闭环、三值验证、预算和独立数据作业已实现，v2 同 20 assignments 全保留，2 成功/18 失败/0 blocked/0 false completion（正常 2/12，全分配 10%）。[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对 34,353 样本、154 帧、52 动作，valid/accepted 均为 true；只限当前 MuJoCo 直立有色方块的开发 smoke，不是正式 G1。最终454项回归及30个源文件Ruff/mypy通过；T8/T17a 为 `READY`，T6b 保持 `TODO`。最新进度、变更、验证和交接见[过程文档](research/process/README.md)。目前没有新正式研究结果。

下表保留历史能力口径；MuJoCo 环境或旧运行时验收不能替代新 RGB-D 物理抓放验收。历史 full 已运行且 `PHASE12_REJECTED`，当前权威论文运行数为 0。

## 历史能力总表（截至 2026-10-04）

| 能力域 | 状态 | 验证入口 | 证据 | 运行环境 | 硬件声明 |
| --- | --- | --- | --- | --- | --- |
| 核心运行时 | 已验收 | `scripts/verify_phase6_2.py` | Phase 6.2 报告 | CI 可运行 | 不涉及硬件 |
| PCSC / ETEAC / AUTO | 已验收 | `scripts/verify_phase8_2.py` | Phase 8.2 产物 | CI 可运行 | 不涉及硬件 |
| MuJoCo | 已验收 | `scripts/verify_phase9.py` | `artifacts/phase9` | 本地仿真 | 不涉及硬件 |
| ROS 2 / MoveIt safety | 已验收 | `scripts/verify_phase9_1.py` | `artifacts/phase9_1` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| Isaac Sim | 已验收 | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | Isaac 主机 | 不涉及硬件 |
| 跨后端对比 | 已验收 | `scripts/run_phase9_2_cross_backend.py` | `artifacts/phase9_2/cross_backend` | MuJoCo + Isaac | 不涉及硬件 |
| Synthetic Dry-Run | 已验收 | `scripts/verify_phase10_1.py` | `artifacts/phase10/phase10_1` | CI 可运行 | 不涉及硬件 |
| MoveIt Runtime Dry-Run | 已验收 | `scripts/verify_phase10_moveit_dry_run.py` | `artifacts/phase10/moveit_dry_run` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| 仓库文档治理 | Phase 10.2A-R 后已验收 | `scripts/check_docs.py` | 文档和 CI 检查 | CI 可运行 | 不涉及硬件 |
| Simulation Workbench | Phase 11 已实现 | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | CI 可运行，完整 E2E 需浏览器 | 不涉及硬件 |
| Simulation Runtime | Phase 11.1 已实现 | `scripts/verify_phase11_1_simulation_runtime.py --ci` / `--mujoco` / `--full` | `artifacts/phase11_1/verification` 和 `artifacts/phase11_1/runtime` | CI 跑 Mock 异步和恢复；MuJoCo runtime 需仿真环境 | 不涉及硬件 |
| Model Control Center | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | CI 使用 fake provider/fake Ollama | 不涉及硬件 |
| Simulation AI Console | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | planner dry-run，`dispatch=false` | 不涉及硬件 |
| Local Model Runtime | 尚未接受 | `scripts/verify_phase11_2_model_control.py --ollama` | 无 accepted evidence | 需要本地 Ollama 和已安装模型 | 不涉及硬件 |
| Phase 12 Final Evaluation | smoke pipeline ready；Phase 12.2 clean validation accepted；Ubuntu full 已运行但 PHASE12_REJECTED | `scripts/verify_phase12.py --smoke|--validation|--full` | `artifacts/phase12`、`artifacts/phase12_1/validation`、`artifacts/phase12_2/validation`、`artifacts/phase12_2_clean/validation`；完整新快照见权威状态 | 旧软件运行与公平物理评测分别验收 | 不涉及硬件 |
| 真实机械臂只读 | framework 已验收，真实设备未开始 | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake 模式 CI 可运行，hardware 模式现场专用 | 尚未声明真实只读验证 |
| 真实机械臂运动 | 未开始 | 无 | 无 | 现场设备 | 尚未声明运动验证 |

## 历史状态说明（截至 2026-10-04）

Phase 9.1 当时的结果是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，原因是 Isaac 和跨后端验证受环境限制。Phase 9.2 后续补齐 Isaac smoke、benchmark 和跨后端验证，形成 `PHASE9_2_ACCEPTED`。

Phase 10.2A 不改变 Phase 9.2 的结论，只补强 dry-run 证据和仓库治理。Phase 10.2B 增加控制台，Phase 10.2C 只完成 Level 0 fake/framework。真实机械臂验证仍是 `NOT_STARTED`。

Phase 11 从真实机械臂接入转向仿真工作台。`scenario_registry()` 和 `ExperimentConfig` 成为前后端实验配置的权威来源，Dashboard 不直接连接 MuJoCo、Isaac、ROS、MoveIt 或真实控制器。

Phase 11.1 解决 Phase 11 的同步运行限制：API 创建任务后立即返回 `QUEUED`，后台 worker 通过 SQLite lease 执行 allowlisted runner，并持久化 run、batch、event、metric、attempt、artifact 和 WebSocket replay sequence。MuJoCo READY 只表示环境可用；MuJoCo runtime accepted 必须通过 M11-01 至 M11-10。

Phase 11.2 增加模型控制中心和仿真 AI 控制台。OpenAI-compatible profile 和 Ollama 管理均通过安全后端 API；API key 不写入 artifact，真实 Ollama runtime 尚未接受，`installed_model_count=0`。

Phase 12 冻结 RQ1-RQ7 和 F01-F20，输出最终实验、统计、图表、表格、论文素材和答辩包。Baseline `7b4c9af` 的 90 条 smoke 记录是 `SYNTHETIC_PIPELINE_SAMPLE`，只能声明 `PHASE12_EXPERIMENT_SUITE_READY` 和 `PHASE12_THESIS_ASSET_PIPELINE_READY`，不能替代 validation 或 full。Phase 12.1 validation 从 actual software runners 产生 evidence；最早的 `artifacts/phase12_2/validation` provenance 为 `worktree_clean=false`，保留为 gap 证据。当前权威 validation evidence 是 `artifacts/phase12_2_clean/validation`：540 条 validation 记录中 466 条 runtime-completed，74 条在 runtime 前因 Isaac、MoveIt 或未配置模型环境阻塞，verifier 输出 `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` 和 `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`。只有 full profile 能声明 `PHASE12_FINAL_EVALUATION_ACCEPTED` 和 `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`。

## 2026-10-04 历史阻塞项

- 仓库内没有已授权的真实控制器配置。
- 还没有读取过现场急停或控制器状态。
- Level 0 真实硬件验收没有真实设备证据。
- 没有做过真实机械臂运动测试；MuJoCo 的 T4/T5 物理仿真已单独验收。

## 2026-10-04 历史下一阶段安排

T7 最终 runtime 竞态修复与454项回归已通过，T8/T17a 已 READY，下一步按依赖实施。现行模型使用 [T7 重探 4/4 后的新冻结目录](../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)；历史 T3/T5 source freeze 不冒充现行源码，共享 capture 改动与 T5 12 份旧来源归档见 [preservation 清单](../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)。T8 先导、T6b 的 10000 组及教师整合尚未运行；95 runtime/277 prerequisite 测试只是阶段记录，最终合并回归为454 passed。随后开发两个优化方法并进行冻结评测。历史 Phase 12 保留为证据追溯。不得绕过后端直接控制硬件，也不能把仿真结论写成真实机械臂结论；真机相关开发保持冻结。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
