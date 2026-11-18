# Astra：当前标记与区域共同视野覆盖

实际`gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED。工作树/commit/输入SHA见JSON。本轮承认上一轮完整camera_views补丁不足：原RED和唯一GREEN均3952步失败，不能把GREEN目录名称当成功。

逐像素证据表明：左视区域有3角点、无未解释像素，但标记UNKNOWN；总览标记OBSERVED但仅[真,假,假,真]2角点；右视标记和4角点有效，却有167个缺色像素未解释，高度相对平面仅−2.177..+1.902mm，其中160个不邻近实测前景。几何拒绝合理，不可改成foreground。全部simtime16.466666666666054，最后joint目标3944，3952后仅两hold与estop。额外capture还令右视62262个depth像素不同、最大差6.184mm，而RGB相同；禁止重采碰运气。

## 有界探查与修复

1. 原失败/新失败和原生响应全部冻结。先预登记8个候选：相对于已注册标记外法线XY投影的0/90/180/270度方位，各相机高度0.80和1.05m、离竖直35度；look-at来自允许的已测标记/区域几何。仅原相机workspace/frustum/marker-margin内候选可渲染，无效槽位记BLOCKED、不补候选。近退化法线/缺少可用几何停止，不能查教师状态补齐。
2. 最多1次零API原生协议重放到3952，冻结独立诊断仿真状态，随后每候选最多1张pairedRGBD，总≤8张；探查后不继续控制。这不是在线恢复，不允许把8张藏进2次重采/100ms预算。每槽保留pose/标定/RGB/depth/hash、原marker与region判定、角点和未解释像素及耗时。记录采集序号和噪声状态；可显式仅在离线分支对各候选恢复相同RNG起点以隔离视角因素，绝不能追选幸运噪声帧。
3. 若无一候选同时通过原marker和region门，本轮停止，下一Astra讨论更大设计；不得扩大扫描或降低3角点等几何门。若有合格候选，才在camera_positioning和component接线实现由允许几何生成的有限候选/确定性排序；使用标记朝向与投影边距、区域角点相对已测持物/已知机器人几何的预计遮挡作proposal排序，固定tie-break，不硬编码seed/世界点、不用instance mask/真实物体pose/成功标签或renderer预看选线上相机。
4. 在已接受观测/技能边界预计算有限候选；恢复时最多2个不同备选。最近已接受几何可建议视角，绝不能证明当前安全；新帧必须独立通过原全量标记/区域/时效/标定/安全校验。当前本体关节/TCP与注册机器人几何仅用于proposal。候选计算、换相机、采集/归档、视觉、IK全部仍计原100ms；相机动作不推进物理、不发joint。
5. 有针对性负例和泛化契约测试通过后，最多1次从原场景开始的完整零API协议GREEN，不能带入离线探查状态或额外帧。必须8动作和独立物理成功、无安全违规。随后才恢复fixed02/03及44101..44104共原剩余6真实例；再失败即下一实际Astra。

## 范围与验证

允许camera_positioning有限proposal、component接线、servo必要provider/audit接线、对应测试和离线诊断。servo_region判定、颜色/深度/角点/前景阈值、marker准入、TTL、相机workspace/margin、2次备选、100ms、worker120s、SafetyShield、成功评分全不改。

测试覆盖刚体平移/旋转下proposal一致性、非有限/越界/frustum/marker-margin拒绝、无teacher字段、最近几何只提案、旧帧/错标定/无效深度/少于3角点/未解释孔洞仍拒绝；两次耗尽和100ms超时STOP；相机切换前后同physics状态且无joint。完整replay仍网络和模型载入硬阻断，严格使用原4Molmo/1Sol文本及输入绑定。

规划0GPU/API。实施最多1次状态重建+8张离线候选渲染（探查wall≤120s）+1次完整GREEN；每进程外层≤900s，worker120s不改，GPU/renderer原锁和准入保持。真实剩余额度6cloud/24local/6load，0自动重试，原3故障额度不得补失败。

分母分别记账：真实fixed01失败和已花1cloud/4local永久保留于原7例；旧协议RED/GREEN两次失败保留，新状态重建仅诊断、新完整GREEN仅1次分配；8候选槽含BLOCKED/拒绝，不能称8个任务成功率。全部源版本分层，formalNOT_ACCEPTED、qualified_groups_added=0、真机NOT_STARTED。任何新根因、无合格候选、需要扩大预算/几何或意外回归失败均交下一轮实际Astra，不弱化门解决。
