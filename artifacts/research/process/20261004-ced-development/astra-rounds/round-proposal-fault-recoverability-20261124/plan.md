# T8a 开发恢复资格实测

基线 004f9c837ce10fea4a3db6097c3f9abb5909d139。设计第5节要求真实注入、起止时间、教师实际动作、独立恢复及安全评价；正式200组的已完成度与在线G4方法效应分别记录。未发现200组完整证据。旧开发 g-b5c050eaad3b86539df2065da588fe32 一个已证明，5368状态、9动作；R07 锁池首组 g-77a8915dc8c2eb94596a37633248a6d8 有独立 PROVEN，7048 状态、9动作、实移19.102 mm，result明确199未运行。不同池不相加。运行前重读这两份六文件原件，用冻结 row/fault/rules 调原独立 _recovery 校验；版本差异记录原审计、当前读回各自结果。

## 一次性开发分配与实跑

复用已排除在未来正式样本外的第一份开发 assignment.json 原场景资产、质量、接触、位置、seed和视觉（不使用 R07 正式锁池继续分配）。在新私有 mkdtemp 中独占分配四个实例，共用源场景，形成两组有向干预，各跑 T5 NORMAL 和自带 NO_CONTACT 反例各一次，方向先 +1 后 −1；每方向次序交错，每个实例仅一次。新 episode、唯一审计身份；保留该场景原 scene/group 哈希，不把它包装为四个新独立场景。若需区分冷热，记录启动顺序和每次 reset 差异。分母2个 NORMAL、2个反例、1个独立场景。该选择检验换向及无接触对独立资格的影响，不能从单场景估计跨场景率。

新建 scripts/graduation/proposal_fault_recoverability.py 提供 allocate/capture/score 或等价命令。优先复用 protocol_generation._run_physical 的真实实现；可在现有函数增加默认 NORMAL 的只供本机开发调用的可选 case 参数，正式调用与 CLI 保持原默认和原来源锁。也可用独立薄适配调用现有 MuJoCoCaptureSession、run_teacher_episode、write_recovery_source 与 _recovery，避免修改正式生产器。配置从 R07 的已绑定执行 plan 取 config/budgets，场景替换为上述已有开发 row，保留其场景种子/现场 binding。按原安全范围和预算执行：320×240 顶视、原控制器、1/240 物理步（实际值按 config）、settle120；backend.inject_fault(TARGET_MOTION, speed=.02,duration=1,direction_y=±1)；真实 FINISHED 后才调用原九动作 NORMAL 或原 NO_CONTACT。真值仅 T5 既定离线教师、独立物理评价使用。T5 自己返回什么就记录什么，不补写动作。所有轨迹从 reset0 连续登记、封存每个 PRE actuator、实际命令与半开动作范围、RGBD/缺帧、故障始末和终点。实际跑前核对plan.json SHA、EGL及磁盘；复用原每实例 reserve10GiB、retained2GiB、wall1800s、故障起算60s。实例可串行，读回与其他实验独立并行。本轮无新 v10/正式 claim、模型/实机调用。

## 评分和退出条件

从封存六文件独立重算事件方向/时间、带符号位移及≥5mm、教师开始时刻、连续步/actuator/command、每一动作及不可重复 RELEASE 实际命令的数量与序号，安全33对自碰撞、急停及现行终点；按独立判定 lift≥50mm保持≥0.5s、释放后在区内稳定≥1s，记录耗时与失败惩罚60s。独立 _recovery 对不完整或非受支持九动作会拒绝，另从全轨迹计算物理失败/安全以区分审计拒绝和实际结果。不得把 NO_CONTACT 当成 G4 完整重规划或其耗时基线。报告方向、每个样本、NORMAL 的完整资格分子/2、反例误获资格数/2；重复组仅作配对开发证据。预期 RED 覆盖源/方向错配、缺步/actuator、反例无法获证。若两组都失败同样报告，不按结果改初态/阈值；新根因另轮修复。输出真实分配与密封摘要、历史重审、逐实例指标和步骤报告，raw留私有环境，G4正式仍未测。后续须独立注册200组、方法冻结和共同正式方法授权，分别检验≥80%和对完整重规划耗时下降≥30%。
