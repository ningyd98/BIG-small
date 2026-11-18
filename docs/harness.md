# BIGsmall Embodied Harness 开发版

2026-11-18 开发验证：已生成可安装 wheel，修复后的真实 Molmo＋Sol 固定场景两次
完整完成；四个新开发 seed 中一次完整完成、两次独立物理成功。安装封装验收与研究
资格分开，合格基线和正式实验仍待完成。实际分母、源码分组、失败与安装包 SHA256
见[本轮报告](../artifacts/research/process/20261118-real-model-harness/report.md)。

H0 首场景为 `S01_NORMAL_STATIC`，任务是把红块放入绿色区域。它使用已登记的
Franka-like MuJoCo 场景、`side_y_plus_id7_75mm_component_v1`、320×240 RGB-D
顶视相机和 OpenCV 视觉伺服。示例相机初始位置为 `[0.35, 0, 1.35]` 米，运行中
继续使用组件原有的相机移动和倾斜策略。seed 默认是 42001，修改固定场景的 seed 不会
改变初始物理摆放。配置 `scene_split="development"` 使用现有开发位姿采样。正式分组
和 held-out 评测入口独立于此开发版。

## H0 契约与首场景清单

| 契约 | 既有实现与运行证据 |
| --- | --- |
| 任务与运行身份 | `HarnessConfig` 固定场景、角色、标记、相机和 seed。入口生成 `scene-assignment.json`，原 worker 创建关联 job 和 episode，绑定配置、场景资产和角色源码。CLI 展开的配置哈希、声明版本和选定源码哈希单独报告。 |
| 观测与证据 | `RGBDObservation` 绑定帧身份、采集时间、标定、RGB 和原始深度，`VisualEvidence`、`ActionEvidenceContract` 和原检查器保留三值条件及原因。Molmo 只接收 RGB，OpenCV 使用对齐的原始深度及标记。缺时效、身份或观测依据时保留 UNKNOWN。 |
| Agent 候选 | `MolmoPointProvider`、`MolmoGroundedPlannerAdapter` 和 `MolmoWorkerPlanner` 复用现有点位绑定、技能意图和原 PlanningPipeline。Sol 固定为 `gpt-6.1-sol`，报告实际 profile/模型身份由原 provider 产生。待决或缺失依据仍按原入口拒绝或停止。 |
| 技能与执行反馈 | `SimulationWorker` 持有执行生命周期和 SQLite CAS。候选经过角色与委托边界，落实到原 SkillExecutor、SafetyShield 和 MuJoCo 控制器。接受、提交、启动、完成与新帧效果保留相应阶段证据。组件路径的动作资格仍为 `UNKNOWN_NOT_GRANTED`。 |
| 环境生命周期 | 原 MuJoCo 路径负责资源、复位、观测、暂停期间的规划重采样、物理推进和清理。物理步长为 1/240 秒。云返回后同一暂停会话采新帧，用真实新身份和采集时间，保留 sim time。租约、截止和原 5 秒帧龄门按既有墙钟语义核对。 |
| 轨迹、成本及离线评价 | 既有结果、规划与控制事件和 `CostLedger` 记录候选、停止、动作、资源及请求，独立物理判定留在离线评价。原件通过 `evidence-manifest.json` 索引。账单或纯推理耗时缺实证时保持 null。 |

原组件预算是每次运行最多 1 次模型加载、4 次定位生成、1 次云请求、0 重试、0 修复，
worker 截止为 120 秒且最多 1 个 attempt。CLI 不自动重启 episode。取消、停止、租约与
CAS 仍由原 worker 检查，SafetyShield 保留原有硬停止。H1 保留规则/成本边缘角色，
协同 dispatch、局部恢复、云端图像回退和硬件派发均关闭。组件诊断允许在其明确的
MuJoCo 范围内通过原控制路径执行技能。

## H1 安装与离线检查

在 Python 3.12 或更高版本的 Linux 清洁环境安装项目 wheel。在源检出目录构建，再从
任意目录安装。验证环境中可记录 `pip freeze` 和 wheel SHA256。

```bash
python3 -m venv /tmp/bigsmall-harness-venv
H1_PY=/tmp/bigsmall-harness-venv/bin/python
H1_CLI=/tmp/bigsmall-harness-venv/bin/bigsmall-harness
H1_WHEELS=$(mktemp -d)
"$H1_PY" -m pip wheel --no-deps --wheel-dir "$H1_WHEELS" .
"$H1_PY" -m pip install "$H1_WHEELS"/big_small-*.whl
cd /tmp
unset PYTHONPATH
"$H1_CLI" --help
"$H1_CLI" validate
"$H1_CLI" doctor
```

`validate` 和 `doctor` 默认读取 wheel 内的
[`s01-component.json`](../src/cloud_edge_robot_arm/harness/s01-component.json)。
这两项可在无源码、无凭据、无模型、无 MuJoCo、无图形环境中运行。可复制示例，
用 `--config` 指定自有 JSON。schema v1 严格校验字段及值，展开后计算配置指纹。
配置只包含场景与策略身份，授权、数据库和模型路径由运行命令显式提供。

`doctor --source-checkout` 另外核对指定项目树、项目版本、选定文件和登记场景字节。
checkout 的 Git HEAD 在可用时记录，选定文件哈希记录实际检查的字节。以下准备命令
通过该 checkout 的原脚本执行 dry-run，保留原始场景、来源与零调用结果。

```bash
H1_SOURCE=/absolute/path/to/BIGsmall
"$H1_CLI" doctor --source-checkout "$H1_SOURCE"
H1_EPISODES=$(mktemp -d)
"$H1_CLI" prepare --source-checkout "$H1_SOURCE" --output "$H1_EPISODES/prepare"
"$H1_CLI" evidence "$H1_EPISODES/prepare"
```

`prepare` 的 `PREPARED` 表示原入口写出准备记录。此模式没有模型调用、渲染或
物理推进。它保持 `physical_success=null` 和 `executed_actions=0`。报告的 `planned_configuration` 和
`planned_configuration_sha256` 描述后续运行意图。`effective_configuration` 取自原
`scene-assignment.json`，表示实际准备的固定场景、seed 和标记。`not_applied`
列出未生效的 development 采样、视觉伺服和相机覆盖。

## 显式 MuJoCo 组件诊断

在已有真实 API 授权、GPU 资源、资产和专用 Molmo 运行环境的条件下，使用以下入口。
原模型资源准入持有共享的独占锁，核对显存、内存、模型卷余量及其他 GPU 进程。
原 provider 验证本地资产清单和权重字节，并以离线模式加载 Molmo。模型原生依赖保留
在其专用环境，只有需要时才通过 `--application-site-packages` 追加应用依赖。
模型资料及原运行约束见[原组件入口说明](research/sol_molmo_single_episode.md)。

```bash
"$H1_CLI" run-simulation \
  --source-checkout "$H1_SOURCE" \
  --native-python /path/to/approved/native/bin/python \
  --model-control-db /path/to/existing/encrypted-model-control.db \
  --profile-id '<existing-enabled-sol-profile>' \
  --model-directory /path/to/local/Molmo2-ER \
  --asset-manifest /path/to/registered-molmo-manifest.json \
  --gpu-lock /path/to/existing/shared-gpu.lock \
  --application-site-packages /path/to/application/site-packages \
  --allow-paid \
  --output "$H1_EPISODES/run"
```

`--allow-paid` 必须为该次命令明确提供。现有加密数据库由原入口只读访问，凭据留在
受控存储。启动仿真的同一原生子进程先运行指定 checkout 中原 R545 overlay 的准入检查，
核对登记的解释器、baseline.pth、依赖来源、版本与哈希，执行 CPU ABI 检查并确认 CUDA
仍未初始化。随后核对已加载项目模块的位置和哈希，再委派给原单场景入口。选择新的
输出目录以保留既有期次，超时也保留已有文件。每个规范输出路径使用固定的相邻锁文件。
锁由封装进程和子进程共同持有，覆盖执行及收尾核验，锁文件跨调用保留。并发冲突在
启动前返回，报告不带其他期次的结果。只有与本次实际 seed、标记、模式和源码身份
对应的原件才作为本次终态。原 worker
120 秒截止保持有效，外部进程看门狗上限为 900 秒，含模型载入时间。

`evidence` 读取原清单，校验所列相对路径对应文件的字节数和 SHA256，输出
`result.json` 中可验证的原阶段和验收状态。PREPARED 要求原场景分配和来源哈希均
有清单绑定。目录与清单内文件须为直接目录与普通文件。清单、报告与运行数据默认
保留本地。准备成功或组件成功返回 0，原路径阻塞返回 3。启动前校验失败为
`NOT_STARTED`。子进程启动后缺少可验证终态时，报告 `INCOMPLETE_UNKNOWN`、
真实子进程退出码、信号、封装退出码、已有阶段文件和 `costs=null`。组件结果看 `execution_scope`、`component_success` 与独立
`physical_success`。组件诊断的原结果继续记 `formal_research=NOT_ACCEPTED` 与
`qualified_groups_added=0`，实机仍未启动。正式验证依照既有动作资格、B0、先导、
冻结及 G/B 门禁执行。

wheel 交付项目 Python 包、CLI 和小型示例，真实场景资产及原脚本来自明确选定的
项目树。Molmo 模型权重、第三方运行时和 SDK、运行数据库、凭据及完整 raw 按既有
交付边界单独管理。源码与证据索引覆盖各自声明的文件范围。
