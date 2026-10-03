# 决策与风险

## 已裁定

| 裁定 | 理由与执行边界 |
|---|---|
| 本轮先做 P1=T1/T2；T1 审查后放行 T2 | 来源字段先固定，采集证据才能按统一口径记录。其他阶段仍待执行。 |
| 继续在当前功能分支工作区实施，保留预检镜像 | 现有原型与资料含未提交改动；逐文件审查，禁止混入无关改动。本轮不提交或推送。见[初始 Git 状态](../../../artifacts/research/process/20261003-phase1/initial-git-status.txt)。 |
| MuJoCo 是主实验；不启动真实硬件 | 成功必须由真实模型、真实观测和 actuator/step 共同支持；软件、MOCK、规划与物理分别登记。 |
| 继承历史拒绝结论 | [权威状态](../../current_authoritative_status.md)中的 `PHASE12_REJECTED`、旧 5,580 行和权威论文运行数 0 不因本轮开发改变。 |
| 核心依赖优先于扩展 | T14、Isaac 配对、技能缓存独立登记；资源不足时保留 G0/G1、C1/C2 核心证据。 |
| 2026-10-03 执行决策闭环修订 | 用户要求修改当前路线图；保持T1—T18、G/B编号和已验收状态。T7先补同episode反馈/三值验证，T10—T13再完成候选判断、提交与有界恢复。本次仅文档变更。 |
| Jev思路与provider接入分开 | 有限候选和代码编排纳入核心设计；具体Jev/其他判断模型为可选对照。规则/成本provider先行，远程判断计入云总成本，模型概率不解释为物理成功率。 |
| 完成与恢复必须有后置证据 | 在线完成与独立物理成功共同决定正式成功；独立评价不反馈策略。恢复授权不关闭事件；候选、接受、启动分阶段，dry-run不伪造真实ACK。 |
| 2026-10-03 T6a按100→1000分批验收 | 无模型静态数据工厂及100/1000组四入口通过，T6a为DONE。10000组属于T6b，保持TODO，等待T5/T8。静态标签保持execution_verified=false。 |
| 2026-10-03 T5按新协议版本验收 | 首批20例暴露干扰物-桌面支撑误报、落稳前8mm抬升基线及控制器成功后续动；保留首批旧证据，修复后用源码/规则/资产指纹在独立目录重跑20例并只读重算。当前T5为DONE，仅限离线教师冒烟，不把7/20当正式G1或在线视觉成功率。见[新批验证](../../../artifacts/research/process/20261003-t5-teacher-validation.json)。 |

## 持续风险与触发动作

| 风险 | 当前证据/触发 | 处理与状态 |
|---|---|---|
| 小模型泛化与目标缺失时幻觉 | 原[Qwen3.5探测](../../../artifacts/research/model-probe/summary.md)及[Qwen3-VL候选实测](../../../artifacts/research/process/20261003-t3-vl-candidate/acceptance.md)的0/4失败保留。沿用Qwen3-VL 4B，经normalized_1000协议与RGB-D几何优化后，固定S01双图4/4通过并冻结，T3为DONE；两批独立开发验证29/32合格（23/24有目标定位、6/8目标缺失明确拒绝），两条缺失幻觉均被几何校验阻断、一条有目标误拒绝，三条契约均为0步，all_cases_pass=false | 固定门槛解阻不等于任意场景可靠，显式拒绝与几何阻断分别记录，精确独立计数见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。T7现为DONE且已实现新帧与动作后验证，v2开发smoke为2/20成功、0falsecompletion；最终runtime质量门已通过；任意场景泛化风险仍开放。 |
| 顶抓校准超出批准资产或对象范围 | 显式 `mujoco_upright_box_v1` 仅适用于当前MuJoCo资产及高5–10cm竖直方块；冻结核对scene.xml批准SHA与每次校准证据，默认配置为unconfigured，未配置抓取标定时默认拒绝规划 | 不把表面点称为物体中心，不给任意物体/夹具套用该偏移。现行加载使用[T7重探4/4后的冻结包](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/model-frozen-evidence.json)；旧T3包只对应历史源码，资产、提示、协议或源码变化须重验。T3原验收未执行物理抓放。 |
| RGB/depth/实例图跨 pass 或标定错位 | T2 已有真实三 pass 同状态、100 桌面点最大高度误差 2.728 mm、异常关闭与变化拒绝回归 | 当前静态场景证据已通过独立审查；不替代 T6 场景变化、T7/G1 定位或运动中闭环验收。 |
| T4 资产升级与 T6a 旧数据版本不一致 | T6a 100/1000 组 `SceneSpec.asset_family_hash` 为旧 MJCF SHA `6a793870…`；T4 当前资产 SHA `182fb2bc…`，`apply_scene` 显式拒绝不匹配 | 旧数据保留其原来源与 `DONE` 验收，不改写 manifest。T5 从新资产生成并标新哈希；新资产一致的后续数据集须另起版本生成/验收，不能把旧帧或旧组当成新资产物理结果。风险开放。 |
| T5 只覆盖离线教师和已登记安全几何 | 新批20例中7成功/12失败/1安全；唯一安全例为手指40mm限位约0.11mm短暂过冲，按当前1e-4m容差保守记违规。已检查自碰撞33对非邻接几何；PLACE触桌后末态单指失接触可导致技能GRASP_LOST，失败轨迹保留 | 不为通过当前数据放宽限位或更改在线PLACE；正式协议前独立标定手指位移/机械臂角度容差并冻结版本。T7已接入在线新RGB-D条件验证且开发smoke已复算，最终runtime验收已通过；不能把T5的独立真值反馈给控制器，也不把开发冒烟当正式成功率。风险开放。 |
| 渲染/GPU/磁盘与长作业预算 | T6a100/1000组CLI实测56.56/1332.669秒，两批采样显存观测峰值均155MiB；T8尚无每episode成本 | 最终落盘/日志/终态预算反例已修复复核；GPU/渲染仍串行。采样可能漏过瞬时峰值；T8后估正式运行成本，资源不足保留INCOMPLETE/BLOCKED与失败证据，不外推当前峰值。 |
| 真值/数据分组泄露及晚到结果 | T6a静态来源/内容分组、test禁导出和离线真值隔离已测；100组80/5/5/10、1000组800/50/50/100均通过。T5教师目标显式标为GROUND_TRUTH_TEACHER，在线机器人真实运动路径的无真值读取回归已通过 | T5旧/新规则目录以源码与协议指纹拒绝静默混用；T7已增加在线来源、期限/取消与租约测试，最终454项回归通过；T10/T13及正式池互斥继续按后续任务验收，风险开放。 |
| 无可行 B0 或恢复闭环缺失 | 需 T8/T11/T13 的实测 | 无合格 B0 不声称节省；T13 未闭环则 C2 未完成。当前风险开放。 |
| 观察重置场景、条件代理或误完成 | T7已实现同backend新帧、统一三值条件和在线/独立物理/语义分层；v2同20分配中0falsecompletion | 原重置/代理路径已修复并有回归；最终runtime竞态与发布异常验证已通过，错目标动作及通用语义风险不能仅凭尾评分关闭。T7保持DONE。 |
| 恢复空转、事件提前解决、云边版本分歧 | 恢复授权和验证解决未分层，提交/ACK边界需完善 | T13持久化次数/时间/无进展预算与状态；真实ACK后激活、启动回执后记执行，重启协调。当前风险开放。 |
| 判断provider增添延迟或造成虚假节省 | 未做本项目真实Jev调用或闭环对照 | 先影子后独立协议配对；记录全部远程判断、超时/回退、版本；缺服务BLOCKED，未尝试NOT_RUN。不阻塞主路线。 |

每次裁定改变方法、样本、阈值或冻结产物时，在此追加日期、依据、影响范围与新协议版本；不可追溯修改正式结果。

## 验证环境裁定（2026-10-03）

相同本地 TestClient 测试在受限环境挂起、主机运行 3.20 秒通过。后续异步/EGL测试使用主机执行并保留原始失败日志，不为环境限制更改产品行为；不需要连接外部服务或真实设备。P1的审计代码即使单元测试通过，仍须独立审查反例通过后放行。

## P1 接口约定与剩余边界

- 旧观测没有 scene/episode/calibration 元数据时保持 `None`，表示未绑定研究场景；新帧包含三者。自动补有效掩码和校验和只做格式兼容，不把历史输入变成新研究证据。
- `CapturedFrame.instance_ids` 为 MuJoCo geom ID，背景 −1，仅离线使用。当前块体可直接标注；T6 对一个物体包含多个 geom 的资产必须合并成对象实例。
- 内容校验和包含采集时间、仿真时间和来源。裁剪保留原观测身份，重算内容校验和，不更新为新帧；在线时效检查由入口执行。
- 全仓文档检查仍有既有报告内容模式和待实现脚本引用问题；阶段文档单独核验。完整 vision 包的 3 处 planner mypy 问题留待 T3 触及该模块时处理，阶段定向检查通过不等于全仓通过。

最终源码核对发现并发变化时，保留当前工作区，单独记录差异并补做审查及同范围验证；不把先前通过外推到变化后的源码。当前 SensorFrame 转观测要求真实 captured_at，缺失即拒绝，禁止以转换时刻替代采集时刻；兼容的旧 RGBDObservation JSON 则保留其原有时刻。

## T6a 审查与来源边界（2026-10-03）

当前[独立代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)已关闭范围内实质发现。主/原始观测保存恰三pass状态证据，深度可视化需对应米制深度；来源绑定包括运行时Pose契约。预算覆盖初始元数据、尝试/拒绝日志、split/audit/quality及终态manifest，临时原子写入另受空闲空间检查；不足时保留真实未完成状态，不假报COMPLETE。

近重复筛查是确定性的局部RGB-D方法，不能视为任意语义重复的完备检测。只读真值用于离线标签，不进入在线观测或SFT user内容；负例保留、不因目标不可用而清洗掉困难样本。[100/1000组最终验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)通过，T6a为DONE；当时下一READY仅T3/T4，T5/T7/T8仍须其余依赖齐备，T6b保持TODO。该次T6a验收未训练VLM、未产生教师抓放轨迹、未验证真实模型/正式物理任务；Jev可选对照与G/B口径不变。


## 2026-10-03 T3 小模型优化与限定冻结

本轮裁定沿用已经安装的 Qwen3-VL 4B，不训练、不下载新权重、不更换更大模型。优化内容为简短明确的双图提示、显式 normalized_1000 坐标协议、完整技能序列与受限 RGB-D 顶抓映射；调用仅经 localhost 直连，不走代理。固定 S01 的 320×240 双图实测4/4通过，冻结快照与sidecar发布后只读核验为VERIFIED，T3按预先门槛记DONE。

冻结证据同时绑定模型digest、量化、生成参数及继承参数、每次实际/预期请求与文本SHA、当前源码、批准资产、逐次GPU身份和校准TCP；加载入口为 `scripts/probe_rgbd_model.py --verify-frozen --output artifacts/research/process/20261003-t3-small-model-optimization/probe`。本地可复现核验不构成外部认证。独立场景扩展与负例失败另列，不把几何阻断当作模型显式拒绝；结果以[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)为准，未升级PHYSICS或正式G1。


## 2026-10-04 T7 开发 smoke 与冻结边界

- T7当前为DONE，最终454项回归已通过；T8/T17a为READY，T6b仍TODO。v2同20assignments全部保留，2成功/18失败/0blocked/0falsecompletion，正常2/12、全分配10%，独立复算valid/accepted=true。此为当前MuJoCo直立有色方块开发smoke，不是正式G1。
- v1全部失败、34份source snapshot及22,147样本/105帧/33动作完整保存；v2为34,353样本/154帧/52动作，diagnostic-03成功另列。失败并未因后续修复被删除，详见[T7证据目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/)。
- 新模型冻结在T7目录重探4/4；旧T3/T5绑定不能假充当前source freeze。共享capture合法改变，T5其余11份源码及物理判据未变，12份历史来源归档于[preservation](../../../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)。
- 语义尾评分以版本化有限指令allowlist合取最终结果，UNKNOWN/FAIL不能变成成功，但无法阻止评分前已发生的wrong-object动作；任意自然语言和多目标任务不在当前范围。
- 95runtime/277prerequisite仅为阶段证据，最终454项回归通过，关闭结论已汇总到acceptance.md。真实硬件未运行、10000组未运行、未commit/push；历史PHASE12_REJECTED和权威论文运行数0不变。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
