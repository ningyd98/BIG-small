# 4 例控制器失败的独立物理复现

原 V3 的 3 例手指硬限位失败和 1 例 IK 失败均已复现。每例初始状态、动作前状态、成功动作后状态，以及失败后调用原 `safe_stop` 的最终物理状态哈希和物理步数，都与冻结记录一致。结果与逐步数据摘要见 [controller-prefix-summary.json](evidence/controller-prefix-summary.json)，完整本地原始文件索引见 [controller-prefix-raw-index.json](evidence/controller-prefix-raw-index.json)。

这次验证是冻结运动前缀的诊断：把原 `resolved_step` 明确作为离线教师输入，调用原控制器执行原 MOVE_ABOVE / APPROACH，逐物理步记录 qpos、qvel、ctrl 和接触，并保留原硬限位检查。原规划、契约、shield 和 worker 没有重新执行，因此结果不能冒充完整端到端安全准入、抓取成功率或新 seed 泛化。没有改变 MSAA、轨迹或限位，没有调用新模型；网络拦截器记录的尝试为 0。单例外层 180 秒、内层 180 秒及 16000 步 cap 均未触发。

|案例|原失败及复现步数|失败步的右指反馈|手指指令|记录到的接触|
|---|---|---|---|---|
|development-043003|HARD_FINGER_LIMIT，1189|40.116769988 mm|左、右均 39 mm|失败步右指接触物体|
|held-out-044009|HARD_FINGER_LIMIT，1198|40.101536331 mm|左、右均 39 mm|1196 步右指接触物体；1197 步仅桌面/物体接触；1198 步左指接触物体|
|held-out-044011|HARD_FINGER_LIMIT，1777|40.101495575 mm|左、右均 39 mm|失败步右指接触物体|
|development-043008|CONTROLLER_FAILURE:UNREACHABLE，120；动作推进 0 步|无动作期物理样本|未执行运动|不作接触因果判断|

手指的模型范围仍为 0–40 mm，原硬停止线仍为 40.1 mm。这些记录确认：命令值保持 39 mm 时，实际右指反馈仍会越过停止线；不能再仅凭命令值在范围内就排除动态超调。接触与越限在这些前缀中同时出现，但本次没有改变接触条件、轨迹或增益作因果对照，不能认定接触是唯一根因，也不能据此放宽硬限位。

IK 失败的原目标为 `(0.4094091377, -0.3748416029, 0.16)` m，位置误差 `0.3214812268` m、姿态误差 `98.722364°`，与原记录一致。结论仅是当前控制器在该初值下返回 UNREACHABLE；尚未证明所有合法初值和路径都无解。

入口 [replay_controller_prefix.py](replay_controller_prefix.py) 的 SHA256 为 `7f892dc9bdce9b15f7f5dea340b7de289b2fb4ed7dee05ef04463fb33d93cf56`。运行前后核对了 1062 个当前源码/配置/资产文件的哈希；冻结 V3 清单和所用观测、场景、episode 的哈希也逐项核对。完整逐步日志、回执和进程状态共 17 个文件、3386377 字节，保存在忽略目录 `raw-local/controller-prefix-01/`；提交的摘要和索引不是完整远端复现包。

此前 [frozen-failure-diagnosis.md](frozen-failure-diagnosis.md) 仅只读检查冻结图像和回执，未推进物理，其“手指逐步数据缺失”描述适用于该阶段。本次新增物理诊断补足了该证据，保留前一阶段文件原样。9 例深度几何失败的 MSAA 因果归因仍未确认。下一步若获准修改轨迹，应以这些原始反馈和接触前缀作配对对照，同时保留原停止线；新模型端到端和新 seed 实验另行计数。
