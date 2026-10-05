# R01：完整采集、原件核验与逐帧姿态负例

唯一采集 session75370 和离线读取 session60356 均已终态退出0。固定修复版采集器完成4806物理步、743条原控制命令、9个原教师动作；4807次逐步采集全部保存，0采集失败。固定读取器核对整个原journal、动作身份、完整120 settling/9动作/两次dwell配方、全部帧原件及其分母后，完整性为 VERIFIED。最大模拟采样间隔0.004166666700001542秒，小于原0.005秒门。实际采集耗时915.764513714秒；离线CLI未记录完整进程wall/peakRSS，不能用文件时间或此前估计冒充实测。

这关闭了本轮完整采集和离线执行路径，**没有关闭全程姿态可观测性或连续证明**。逐帧解码为4618 OBSERVED、189 UNKNOWN，共4807帧；每帧stability_status仍为UNKNOWN，几何及角速度校准界不可用。原始失败、未知帧和旧失败attempt均保留，没有补帧、重跑、插值或降低判据。

## 负例定位

189个UNKNOWN分为186个 `known_marker_not_observed` 与3个 `registered_marker_size_inconsistent`（steps870、871、878）。共43个连续未知段，最长step876–994为119帧；前后可观测帧step875与995相隔约0.500000004模拟秒。相机采样间隔合格不代表姿态观测间隔合格。按原journal半开动作跨度重新关联：

| 原动作 | 物理步范围（左开右闭） | 帧数 | OBSERVED | UNKNOWN |
|---|---:|---:|---:|---:|
| MOVE_ABOVE | 120–745 | 625 | 612 | 13 |
| APPROACH | 745–1295 | 550 | 426 | 124 |
| GRASP | 1295–1534 | 239 | 239 | 0 |
| LIFT | 1534–2229 | 695 | 693 | 2 |
| OBSERVE（抬升后） | 2229–2349 | 120 | 120 | 0 |
| MOVE_TO_REGION | 2349–3554 | 1205 | 1165 | 40 |
| PLACE | 3554–4279 | 725 | 715 | 10 |
| RELEASE | 4279–4518 | 239 | 239 | 0 |
| OBSERVE（释放后） | 4518–4806 | 288 | 288 | 0 |

reset/settling的step0–120共121帧全部OBSERVED。原初始及九个动作后边界帧可见，没有覆盖这些动作中的瞬态。

从8份原RGB导出字节及其原帧SHA进行只读视检，[step900](diagnosis/raw-rgb/step-0000900.png)明确存在夹爪遮挡标记左侧。step629的白边接近手臂轮廓；17像素初始边长对零散未识别的栅格效应仍是待验证假设，不能把所有186帧都断言成同一原因。三个尺寸异常保留原拒绝，不调大容差。[图片来源](diagnosis/selected-image-pins.json)与[完整未知帧清单](unknown-frame-inventory.csv)可检查。

## 独立物理评分与来源范围

Root另从保存的4807项 PhysicalSample调用现有 `evaluate_evidence`，原evaluation_start_step=120，不构造backend、不步进、不解码。重算与保存的独立物理outcome一致：SUCCESS、抬升0.10389920812730212米、保持0.7625000060999572秒、放置稳定2.1541666839007974秒，SCOPED_NO_VIOLATION。它是排除开发场景的原完整物理评分，不能替代在线证据、G1统计门或姿态稳定证书。

输入仍是outboard-v3开发资产、640×480、noise0、自定义协议与同一development component，不能作为新的独立校准组或默认320×240／noise.001正式域资格。source_authenticity=UNKNOWN，native admission未提升；独立UTC、RESET应用发布、至少9支持组、三消费者与Max真实角色仍未验收。本轮provider和hardware调用为0。

[读取器原结果](offline/offline-verification.json)与[局部机器报告](report.json)保存分母、43段和全部物理评分；[raw清单](raw-inventory.json)列4829文件、519937924字节及逐文件SHA。完整519.9MB输入保存在本地workspace，不在本步派生报告Git提交中；远端仅有代码、清单、派生结果及选定原RGB，不能宣称远端单独具备全raw复现包。取得完整原件后，可用固定读取器对原attempt执行 `--output NEW_DIRECTORY --decode` 重算，原件不改写。

本轮读取器源与fixed protocol仍沿第54步已审SHA。[Root分析来源](diagnosis/analysis-source.py)是本次成功分析脚本的原字节副本；首次派生脚本误读动作字段physics_step、在写报告前停止，改用原start_step/end_step后重新分析，见[初始派生错误记录](diagnosis/analysis-schema-initial.json)。这没有重启实际实验或改动任何输入。

下一步是新独立标记设计的有界实采预览，覆盖全部189负例和预登记健康控制；缺完整qpos的旧帧不能混拼成counterfactual物理状态。新资产／新协议只在审查后使用，旧资产、decoder和全部未知原件保持。完整新代次验证及R2/R3后续证据分别报告。
