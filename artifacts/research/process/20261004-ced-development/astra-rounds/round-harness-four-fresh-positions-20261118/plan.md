# 已冻结候选的四个全新开发位姿真实运行方案

本轮由 GPT-6.2 Astra 制定，GPT-6.2 Sol 实施。用户本次授权新增四个 MuJoCo development 槽位。父轮及模型提示修复轮的零调用约束维持；这里的额度独立登记。实际执行的云模型仍为 gpt-6.1-sol，本地为 Molmo2-ER，端侧视觉、相机、可见标记、控制与 SafetyShield 沿用现行配置。每槽最多 1 次付费云请求、4 次本地生成启动、1 次加载、0 重试或修复，总量至多 4/16。历史七个试次、预留三次故障额度及新四例分别核算。

## 预登记

按结果出现前选定的连续日期编号，在候选生产 sample_component_scene 上实际生成。四个完整姿态及程序来源见 preallocation.json，SHA256 b68f756ff5570fc6886c5f8e50771a549eb73464bb539e3716a957ed1e116ec8。坐标单位 m，yaw 单位 rad。

| 固定顺序 | 标签 | 初始 xyz | yaw |
| --- | --- | --- | --- |
| 2026111801 | VISIBLE_POSE | (0.451011, 0.010505, 0.035) | 0.108222 |
| 2026111802 | VISIBLE_POSE | (0.452166, 0.036969, 0.035) | 0.082859 |
| 2026111803 | VISIBLE_POSE | (0.405785, −0.030443, 0.035) | 0.008477 |
| 2026111804 | ARM_OCCLUSION_STRESS | (0.372371, −0.389269, 0.035) | −0.136472 |

主仓与五个历史检出的 experiments、results 及 artifacts/research/process 中共核对 296 份 scene-assignment、scene-application、preallocation 原件，84 个显式 xyz/yaw 记录，四个 seed 和四组位姿均无命中。压力标签表示预设条件，遮挡程度须从实际观测另行判断。运行前重复核对新增的已执行/已分配记录，排除本次预登记自身；发现真实碰撞时保留本轮并停止派发，不更换 seed 规避结果。

## 放行与冻结

1. 先完成父轮旧四例字节绑定离线诊断及规定的冻结版本验证，保存实际日志与候选 commit、tree、产品源码逐文件 SHA、角色/配置、R545 overlay 与专用环境、依赖、场景资产、模型清单、装好 wheel SHA。绑定修复须有真实旧回答正例和篡改负例。冻结候选的相关 CPU/EGL 回归、独占协议回放及清洁安装检查实际通过；完整测试收集与分区如实报告。若时间或归档误判出现，核对证据并按新问题制订窄方案，禁止把先前不同代码绿色回执挂在当前版本上。冻结后不再边跑边改。原件需显式提供的可选验证按真实环境与协议执行，不能填报为通过。
2. 将四个 config 从同一已验证包的 s01-component.json 派生，仅变更 seed 和 scene_split=development；逐个调用已安装 CLI 的 validate，按生产采样器比对完整 preallocation 条目。doctor --source-checkout、prepare 和 dry evidence 可在独立新目录执行，prepare 的 planned/effective 差异以实际记录为准；不占真实槽位。由本次明确付费授权、可用加密 profile、原模型/资产 manifest、相容原生解释器/R545 成功、已核实的候选导入和独占 GPU 值守共同授权真实 launch。现有原生启动 receipt 仅供定位本机资源；阶段报告只记来源身份/必要摘要，不输出密钥或数据库内容。原主机既有归档单成功槽约 541 MiB，按四例及复核临时空间检查剩余空间。实际 100 ms / 120 s 门要在共享 GPU/EGL 和重负载验证完成后独占运行。
3. 自有新根建议 experiments/results/phase9/harness-four-fresh-20261118，分 configs、receipts、native/fresh-<seed>、verification。使用现有原子输出占用，预先保留不可覆盖的槽开始回执，右侧记录启动、退出、信号、绑定阶段、成本以及最终状态；仅对尚未启动的指定槽位按原顺序继续。将最终产品 SHA 与预登记哈希写入独立 freeze-receipt；新提交即便只添加证据也需验证产品 tree 不变。本计划内研究代码/验证器可处理四例并生成派生结果，禁止改变控制、阈值、相机策略、模型参数或原件。

## 实际执行与事后核验

4. 在已安装 wheel 的仓外环境串行运行 **bigsmall-harness run-simulation --config <单槽配置> --source-checkout <冻结候选> --native-python <已登记解释器> --application-site-packages <已验证依赖> --model-control-db <原加密库> --profile-id <原启用云配置> --model-directory <已登记录权重> --asset-manifest <登记清单> --gpu-lock <原共享锁> --allow-paid --output <唯一新目录>**。采用原 overlay/锁/原 worker 和相机。单槽正常保护停止或初始规划拒绝是本轮可出现的有效终态，按原计划继续下个独立槽。超额、释放锁异常、身份/资费不明、源码漂移或软件异常先停止依赖该条件的后续派发并留证。禁止重复调用同一个槽，即使未见 provider 返回；未知资源消耗保留 null，累计按最保守额度记占用。
5. 新验证器从本轮预登记读取四个槽，从本轮 freeze-receipt 读取**实际同一份**代码和角色源指纹。复用 Harness verify_evidence、原物理 evaluate_evidence 与已有命令连续性/帧/安全检查逻辑；历史 verify_native.py 内置 11 月 18 日旧七个 id、冻结组 pre/post 和旧 base_commit，其面向旧批次的 main/硬编码 sources 不能直接判新试次。可用单独小型脚本或在新研究归档适配输入，不改旧脚本/旧结果。正反测试必须验证未知 ID、错 seed/split/实际姿态、错 freeze/角色 SHA、缺索引/替换帧以及调用额度越界均拒绝。失败前缀只核对实际可见命令区间，阈值照旧；规范的 0 动作/0 云案例可通过证据完整性核验，同时保留其任务失败。
6. 每个槽核对配置、真实 scene-assignment 与 component/scene-application 的 requested/applied xyz/yaw（容差依现有生产物理检查；列出各值/差值）、worker job/episode、结果索引及 source-hashes、role-binding。独立从 physical-evidence 重算抬升、持有、稳定放置、安全违规；另报动作及两段退避、终帧标记、时限、worker/component、实际模型请求与原始 usage、可验证的网络/资源计数、账单未知 null。若有合法启动前阻塞、零动作、未知或归档不全，分别记录实际到达阶段，保持原定分母 4。
7. 报告新的同版本完成 x/4、独立物理 y/4、按情况的保护停止/成本/未运行数，同历史 1/4 与 2/4 分开。开发四例及其安全停止不能授予静态/泛化或 B0 资格；真实机械臂不派发。保留所有原失败、新失败、原始模型回执、帧、数据库与控制记录在本地，汇入阶段总结。结果无预定成功数量；本次工程验证的验收是身份、约束、分母、可审计证据与诚实的不能判定项。
8. 用户新授权允许范围复核后推送到已确认 PUBLIC 的 origin。先核对公开目标/upstream、将推送的**全部父提交和其历史新增对象**及本轮明确路径、与远端差异；禁止出库的模型/SDK/密钥/数据库/full raw、大型本地归档及含敏感内容的日志均覆盖检查。已安全且必要的源码、计划、测试与小型派生证据可提交；对确实敏感的可达历史对象停在本地，保留既有提交并单独报告。成功推送按原流程核对本地、上游、远端 SHA。该授权更新未来交付条件，历史暂缓推送记录保留。
