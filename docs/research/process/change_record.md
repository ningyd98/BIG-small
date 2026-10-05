# 变更记录

## 整体计划更新（2026-10-04）

新增云、边、端设计与整体执行计划；同步顶层plan/roadmap/README、原设计/执行计划继承入口、权威状态及过程文档。新增T3b/T7b、拆分T8a/T8b和T12a/T12b，保留T1—T18与G/B编号。近期不锁边缘型号；固定机会/故障可恢复性和B0周期筛选前移，模型选型后置。此次未修改产品代码/配置、未运行新模型或实验，文档校验单独记入阶段总结。

## 2026-10-04 全部后续研发接续

本批保留启动时未提交改动，在本地 `research/20261004-continuation` 分支新增研究账本、网络/时钟、先导/冻结 CLI、周期监督与数据工作台。周期监督改为专用判断协议，版本/观测绑定且在原子动作边界应用；目标运动通过真实外力/步进实现。五项独立审查发现及修复见[记录](../../../artifacts/research/process/20261004-t8-foundation/review-findings.md)。

T17a 后端8项、前端30项和真实E2E3项通过并独立验收；研究及旧闭环合并518项通过，最后摘要标记修复另有58项补测通过（有重叠）。全仓检查的既有失败和中止记录分别登记。T8第一批120例仅作诊断，第二批排除旧池并归档479份来源，120新开发组全部结束，5成功、静态4/40，物理/帧/成本复核一致；冻结拒绝，协议未发布。后续摘要新增tcap_derivable、freeze_ready不冒称独立验收，final progress与summary同步；旧批原始产物保留。具体命令、各步结论与产物汇入[阶段总结](continuation_20261004.md)。

用户提出 Max/4B/OpenCV 三层架构，已评估角色分工、公平对照和当前闭环不足；没有据此更换冻结模型、调用新的付费服务或改变正式门槛。未commit/push。

本记录区分文档工作与产品实现。T1/T2/T6a/T3/T4/T5 已在各自限定范围验收为 `DONE`；T3仅固定S01与当前资产的静态几何门槛，截至2026-10-04，T7为 `DONE`，已实施并完成v2开发smoke复算，最终454项回归通过；T8/T17a 为 `READY`，T6b仍为 `TODO`。下列文件依据实际工作区差异登记，不能根据计划中的 Files 栏倒推“已变更”。

| 日期/任务 | 已确认变更 | 验证与证据 | 待回填 |
|---|---|---|---|
| 2026-10-03 / 过程文档 | 新建本目录的 README、阶段进度、执行日志、验证矩阵、决策风险、变更记录、交接文档 | 文档链接和状态审阅；不计为 T1/T2 验收 | 已接入文档索引并同步权威状态 |
| P1 / T1 | 新增 research/models.py、provenance.py 与15项行为测试；历史 verifier draft 显式 LEGACY_PIPELINE；新增 evidence_inventory.md | 合并35项回归及ruff/mypy通过；三项审查发现修复后关闭，见执行日志 | 已验收；未产生正式物理实验结果 |
| P1 / T2 | 修改 vision/observations.py、capture.py、simulation/models.py、simulation/mujoco/camera.py、backend.py；扩展观测测试，新增 test_rgbd_capture_session.py 和 verify_rgbd_capture.py | 同状态采集、元数据完整性、renderer 复用与异常释放；局部25项、合并88项回归及定向静态检查通过；真实平面最大误差2.728 mm | 独立审查通过；config.py 已满足尺寸要求，本任务未再修改 |
| 2026-10-03 / 路线闭环修订 | 更新主执行计划、研究设计、docs/roadmap.md及阶段进度/验证矩阵/决策风险/交接/本记录/执行日志；补同episode反馈、三值验证、有限候选、有界恢复与ACK/启动语义 | 只做文档与依赖一致性检查，实际检查结果见执行日志；不新增产品测试或物理验收 | 产品实现均待后续任务；G/B编号、正式样本与T1/T2状态不变；Jev为可选对照 |

后续阶段每项增加一行：任务与提交前后工作区范围、改动文件及原因、运行命令和退出码、原始产物/哈希、SOFTWARE/REAL_CAPTURE/REAL_VLM/PHYSICS 证据层级、未满足项。历史用户改动与本轮改动分列；不在此复制完整 diff，也不改开题报告 Word/Markdown。

新增研究代码与本轮相机/观测修改基于启动时的文件前镜像核对；初始工作区已有机器人资产、API、UI、运行时和 RGB-D 原型修改，见[初始清单](../../../artifacts/research/process/20261003-phase1/initial-git-status.txt)。这些先前修改不算作本批交付量，也未统一提交。README、文档索引、项目状态、路线图和权威状态已接入本过程文档入口。

收尾发现并保留了四文件的并发增强（缺采集时刻拒绝、载荷边界、采集开始计时、标定变化拒绝），编写来源未确认；已另存差异并通过局部复审及88项合并复验。首次审查版本源码摘要与补丁另存备查。

## 2026-10-03 T2 增补差异

[本轮补丁](../../../artifacts/research/process/20261003-phase1/t2-resume/continuation.patch)仅包含六个相对恢复起点发生变化的文件：observations.py、MuJoCo camera.py、两份 RGB-D 测试、model_control/service.py 的一行中文说明及 assets/manifest.yaml 的场景 hash/version。前四项修复缺时间戳、异常载荷、采集时间、跨 pass 标定和分辨率边界；后两项关闭较大回归发现的既有集成问题。[验收报告](../../../artifacts/research/process/20261003-phase1/t2-resume/acceptance.json)记录 123 项最终通过、实采与测试边界。原 P1 文档/产物的并行更新予以保留，不归入本轮代码差异；未提交 Git。

## 2026-10-03 T6a 实施与分批验收

- 新增 `datasets/rgbd/` 的共享 models、scene_sampler、离线 capture、labels、writer、quality、splitter、generator、exporters 及包入口，新增 `vision/offline_reader.py`；扩展连续采集会话的场景应用及 MuJoCo backend 的数据场景准备入口。冻结文件以[源码摘要](../../../artifacts/research/process/20261003-t6a/frozen-source-hashes.json)为准，不把旧工作区 RGB-D/API/UI 改动归入本批。
- 新增 generate/validate/export/replay 四个脚本、100/1000/10000 三个 YAML 和五份 dataset 测试。实现来源/组隔离、raw扰动对应、原子发布/恢复、5倍尝试上限、磁盘/取消状态、禁止test导出及保留时间戳的离线重建。
- 审查发现的转动稳定性、旋转桌面边界、三pass证据、深度可视化一致性、完整来源依赖、最终落盘与尝试日志预算均已修复并复核；[最终独立代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)为PASS。数据124项、旧路径123项回归及定向Ruff/mypy（18文件）通过。
- 真实100组完成，35正/65负，独立80/5/5/10划分；1000组完成，301正/699负，独立800/50/50/100划分。两批generate/validate/export/replay通过，T6a为DONE，T6b为TODO且未运行。[最终验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)逐项保留证据；当时下一READY仅T3/T4，T5/T7/T8仍须其余依赖齐备。未提交/推送，原P1/T2及Jev路线修订历史保持独立。

## 2026-10-03 T4 控制器 v2 与 T5 离线教师

- 扩展 MuJoCo backend 的逐物理步只读观察和接触白名单；新增独立 episode evaluator、`TrajectoryFrame`、离线教师、轨迹生成与只读校验 CLI、20例配置及对应行为测试。离线捕获初始夹爪设为打开，避免教师起点与真实执行状态不一致。
- 修复成功运动后残余关节目标继续驱动的问题，加入一次有界载荷补偿；保持原速度、加速度、5 mm/5°与超时门槛。真实 T4 v2 六类验收6/6通过，无额外持位的失败对照保留，见[控制器因果复验](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)。
- 独立评价修复静态干扰物-桌面支撑误报和落稳前抬升基线；非有限自碰撞距离与缺失逐步证据均拒绝通过。恢复校验绑定配置、资产、教师/评分/控制器源码 SHA；只读校验重算场景身份、帧链、结果与安全标签。旧批保持诊断用途，新批另建目录。
- `datasets/rgbd-teacher-smoke-v2` 发布20/20例、104动作帧、56,994物理样本，7成功/12失败/1安全违规，仅7例 `execution_verified=true`。固定正控成功、无接触负控失败；全部逐条重评通过，见[T5验收](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)及[只读校验](../../../artifacts/research/process/20261003-t5-teacher-validation.json)。跨阶段251项回归和最终17项教师回归、定向Ruff/mypy及独立复审通过。
- 同步 README、权威状态、路线图、项目状态和过程文档的当前任务状态；历史快照保留时点。T5 仅完成离线冒烟，T7仍等待T3，T6b等待T8预算；本阶段未提交或推送。


## 2026-10-03 T3 小模型协议与几何优化

- 沿用本机已安装的Qwen3-VL 4B，修改双图消息、显式坐标协议、模型快照和严格技能序列；新增受限RGB-D顶抓映射。默认抓取配置保持unconfigured，只有显式配置与批准资产匹配时启用；未配置抓取标定时默认拒绝规划。未训练、未下载新权重、未更换更大模型，模型请求仅经localhost直连且不走代理。
- 强化探针的原像素离线评分、逐次GPU/digest与校准TCP门槛；记录实际/预期请求、完整角色文本、继承及显式参数，冻结sidecar绑定源码/资产与内容SHA。新增只读冻结包复核入口；落盘失败不得返回PASS。独立场景CLI按预定分配逐例记录正例、显式拒绝和几何阻断，不在模型输入中使用离线实例真值。
- 固定S01、320×240 normalized_1000双图真实探针4/4通过，[冻结快照](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen.json)、[sidecar](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen-evidence.json)及[报告](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/probe-report.json)已发布，`--verify-frozen`为VERIFIED。225项相关回归和6个source文件mypy通过，独立审查无阻断项；最终定向检查及逐例证据见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。
- T3仅当前资产中高5–10cm竖直方块的静态模型/几何门槛验收为DONE，未执行物理动作。两批独立开发验证29/32合格：23/24有目标定位、6/8目标缺失明确拒绝；两条缺失幻觉几何阻断、一条有目标误拒绝，均0步契约。32个唯一scene/RGB，无error/missing/duplicate，all_cases_pass=false；保留失败且不调阈值。原两候选0/4失败产物未覆盖。该次T3验收时T7升级为READY但尚未实现/验收，T8/T6b保持TODO；未提交、未推送、未启动真实硬件。


## 2026-10-04 T7 已实施范围与收尾

- 新增vision执行/独立评价、三值conditions、verification_router、runtime_events、冻结模型读取/有界请求、有限S01语义尾评分；扩展capture借用ownership、研究SafetyShield workspace/安全上升例外、runtime作业和HTTP/WS共模型factory。新增独立dataset_job及草稿job_type/dataset_config校验，复用原数据generator。默认RGBD/VISUAL_PLANNING不声明物理任务成功。
- 同episode执行、新帧、temporal颜色身份、前景遮挡证据、边界RGB-depth污染剔除、partial动作记录、initial estop、最短deadline与0.6秒lift视觉保持已实现，未改T4/T5控制器/技能/物理评分门槛。可选HOME明确NOT_EXECUTED；预算为2/0/3/120。
- 模型在[T7新目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)重探4/4后冻结。仅共享vision/capture.py改变历史T3/T5source绑定；T5其余11份源码及物理判据未变，12份历史source已按[preservation](../../../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)归档，旧证据未改写。
- v1全20失败及34份源码快照保留；v2同20assignments全保留，2成功/18失败/0blocked/0falsecompletion，正常2/12、全分配10%。[v2独立复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)为valid/accepted=true，34,353样本/154帧/52动作；diagnostic-03另有在线与物理成功。限当前MuJoCo直立有色方块开发smoke，非正式G1。
- 更新使用说明与12份入口/过程/计划文档的实际状态。95runtime/277prerequisite为阶段测试，最终454项回归通过，T7仍DONE；T8/T17a为READY，T6b仍TODO。未运行10000组或真实硬件，未commit/push。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
