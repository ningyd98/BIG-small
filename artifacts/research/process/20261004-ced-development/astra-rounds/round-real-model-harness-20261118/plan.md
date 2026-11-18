# Astra 实施计划：真实模型闭环、H0/H1 与剩余证据

实际生成模型 `gpt-6-astra`，2026-11-18，状态 **PLANNED_NOT_EXECUTED**。工作树 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`；分支 `codex/v4-marker-ambiguity-20261115`；基线 `318a546dd3a945bddc076cc06bc3528966a4051a`。四项已有用户授权，不再请求批准；本地交付、公开推送暂缓，raw/数据库/凭据/权重不公开。

输入文件与SHA256见 `plan.json.inputs`（28项）。主仓最新总计划仅引用前138行，原字节保留于 `harness-plan-lines-1-138.txt`，不混用工作树旧版。实施前重核相关SHA；因并行独立工作变化的非因果文件可记录，因果输入变化须复核计划。

## 原始证据与根因

- 20261117 grasp-lift-stop报告明确3/3 worker使用外部模型协议替身；20261118 Molmo/RobotManip报告仅离线定位，使用历史帧时钟，不含在线TTL及完整抓放。当前真实入口已连接Sol/Molmo/原worker，先运行，不预改控制栈。
- H1源码依赖checkout ROOT/src/scripts/assets，包内反向导入scripts资源准入helper，pyproject无console script；需要最小安装层而非新执行引擎。
- UTC原两节点合计600秒门在600.017148秒终止，returncode -15，均TIMEOUT_UNCOMPLETED；两次独立长诊断不抵原门。独立诊断报告LocalEnvelope重复验证CPU爆炸，精确证据及修复边界须补Astra附录后再实施。
- Phase12 adapter硬编码MOCK，draft缺input_mode→默认RGBD；现有拒绝正确。原18条F20无executor，恢复/竞争/exactly-once证据缺失。clean provenance不替代运行证据。

## 可立即执行：真实模型固定场景和新seed

A阶段3次固定S01、seed42001。使用既有round545 Molmo overlay和原CLI，选项为 `--execute --component-diagnostic --visual-servo --marker-family side_y_plus_id7_75mm_component_v1 --seed 42001 --allow-paid`，显式给当前profile、加密DB、模型目录、资产manifest、GPU锁与全新output。相机配置绑定上一成功场景，保留可移动倾斜能力；不要启用cloud-vision-fallback替换本正链定位。第一例有计划外失败即封存并交实际Astra下一轮，不连续试到成功。

B阶段在运行前冻结44101..44104四个development seed，核对与正式/selection/frozen组隔离，使用原 `--scene-split development` 改变实际物体位姿。44104是intended occlusion stress，必须由运行图像确认，不能仅凭标签声称遮挡已发生。共7例可用现有入口直接启动，不需要新增控制接口。根执行者已报告39项预检通过、native overlay身份通过，具体回执在步骤报告绑定。

C阶段另预登记最多3个故障episode，建议seed44111/44112/44113：初始获取后遮挡、LIFT保持掉物、提交前旧帧。先复用现有hook；若缺少外部入口，只增默认关闭、显式component simulator范围的注入接口，绑定episode/step/时刻及实际效果。先协议替身确定性验证，再消费真实模型额度。旧帧原时间和identity保留，TTL不改；掉物/遮挡用实际环境或传感器条件验证，教师状态和评分不回流Agent。故障接口未验证前不得启动此3例。

## H0/H1最小收口

H0映射现有任务/身份、观测/证据、provider、技能/执行反馈、环境生命周期、轨迹/成本六类契约，记录物理时间与墙钟、预算继承/取消/停止边界，注明未验收能力。H1添加安装CLI、配置/资源清单和无凭据离线示例；共享资源准入helper移入包内且保持旧脚本兼容，修复checkout相对资源定位，显式区分包资源和外部模型/场景。复用原run_single_episode→SimulationWorker→SkillExecutor/SafetyShield。不得打包全部scripts、模型、数据库，不能另造控制栈。

清洁环境从wheel安装，离开源码树且unset PYTHONPATH后验证help、离线契约例、资源/来源、退出清理；可选MuJoCo和真实模型能力分别按实际证据声明。相关single-episode、worker、scene-variation、component-safety、servo回归加针对性安装/故障用例即可，不默认重跑整库。

## UTC与Phase12

UTC：先补根因附录，绑定exact函数/热点计数/证据SHA/限定文件再改。每backend定位剖析最多60秒、无API；不可删原case或断言，不可改TTL/门时长，不可缓存绕过当前owner/lease/clock/context验证。修后只跑一次原两个node ID同一进程合计600秒门，留stdout/JUnit/外部wall；不以并行或每节点600秒替代。

Phase12：限定 `Phase11RuntimeAdapter(lifecycle_only=False)`，将显式关键字贯穿 `_run_completed_job`、`_run_recovery_job`、`_run_duplicate_competition_job`、`_draft`，仅opt-in时选择现有LEGACY_PIPELINE用于软件生命周期。新增 `scripts/run_phase12_runtime_lifecycle.py` 使用真实adapter与不变receipt predicates，禁止猴补实际执行；不改主runner/validator，默认MOCK/RGBD仍RGBD_CAMERA_REQUIRED、0 executor。先1例，成立后至多18个独立补充validation行，关联原行ID和新run ID，标记SOFTWARE_LIFECYCLE_ONLY。旧18F20与旧summary不覆盖，不让full profile接受此通道，不宣称物理/研究。真正补原F20物理资格需另轮opt-in MuJoCo方案。

## 预算、资源和停止条件

A3+B4+C最多3，总计最多10 episode/10 load/40 local/10 cloud；每episode原1load/4local/1cloud，0repair、0retry、worker120秒、provider在途1不改；外部watchdog最多900秒含载入，不扩worker期限。失败、拒绝、BLOCKED、超时都保留分母，未用额度不作为重试余额。

现选profile只读预检为profile-4f24f5330ad644ad，真实gpt-6.1-sol且有加密secret；运行前再查，不激活其他profile、不输出secret。Molmo BF16使用原round545运行时和离线校验权重，记录实际解释器/import路径与源SHA。原GPU锁非阻塞独占、foreign compute apps为空、VRAM空闲≥12000MiB、MemAvailable≥8GiB、模型卷余量≥60GiB，不弱化准入。GPU串行。

账单/可靠价格未知记null，遵循现有账户cap，记录tokens/字节/请求及有证据的实际账单；RTT不冒充纯推理时间。UTC修后1次600秒门，Phase12至多1初测+18补充行、0付费API、0full profile；安装环境1个。

## 验证与验收边界

真实抓放必须有实际Molmo+Sol请求/响应、帧与动作关联，在线效果和独立物理判定同时成立；原抬升≥50mm/保持≥0.5秒/释放稳定≥1秒不改。逐例保存候选、拒绝、提交、执行、新帧效果、标记、安全、轨迹、终态与成本。故障须证明注入真实存在、拒绝/停止正确且没有不允许的后续动作。3固定/4新seed不能建立总体成功率。

Phase12补充必须保存真实SQLite恢复attempt≥2及RUNNING→INTERRUPTED→RECOVERY_PENDING→QUEUED，两个不同竞争worker、恰好1次runner调用、终态artifact/hash；默认负对照保留。UTC仅原两backend总≤600秒且全断言通过才记门通过。

软件开发、真实API/仿真、生命周期补充、正式研究、真机分开报告；正式NOT_ACCEPTED、qualified_groups_added=0、真机NOT_STARTED。旧失败/冻结原件不修改。各步骤保留命令、exit code、源/环境hash及原始资料清单，汇入阶段报告。出现新根因/计划外失败/范围扩大时仅暂停相关工作，交实际gpt-6-astra下一轮；其余独立工作继续。

计划写入工具首次使用不可用python返回127，未写文件；改用可用python3完成计划文件写入，不涉及产品修复或实验。
