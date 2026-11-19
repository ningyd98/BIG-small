# 开发预登记历史数据的两种真实索引

第二次 freeze 完整处理已知畸形夹具后，试图打开 fresh-gripper-v3/samples.jsonl，并在写入预登记/BEGIN 前以 FileNotFoundError 退出。已实查七个历史目录。三个普通 RGB-D 数据集的 samples.jsonl 为 rgbd.dataset.v1，100、100、1000 条。四个教师数据集的 manifest.json 为 rgbd.trajectory.manifest.v1，assignments 数分别 42、20、20、20。四组的 seed 与 scene.seed 均存在且相等，distinct seed 分别 41、19、19、19；每组各有一次合法 seed 重复，并非缺一条历史 assignment。

1. 修复仅限 development_plan.py 的历史索引读取、相关测试和派生回执。按七个具名目录及来源合同绑定真实格式，普通样本按实际 JSONL 逐行，教师按真实 manifest 与 assignments 逐项。复用已有 schema/scene 解析和哈希规则；验证版本、行/assignment、来源与内容摘要、seed、group 和目标世界位置 scene.scene_parameters.target.position（有限数值与原单位）。保留每个原始记录唯一身份及评估分母，另外对碰撞检测的 seed/位姿集合去重；不能因成员共享 seed/几何/文件名而删除整行，失败/部分的真实 assignment 也进入历史。原坏 fixture 仍仅精确指纹例外。
2. 对已登记 schema 中同一语义的可选字段、别名、嵌套场景按实际来源分型，在同轮用已有原件和测试适配。多个权威字段并存须一致；忽略与目标无关的 camera/destination/distractor 坐标，禁止把任意数字猜作 seed/位姿。用真实记录的版本/角色选择场景。不存在的文件、不认识的来源/版本、损坏值、冲突行、未知格式以及缺失必填 seed 或无法定位目标均拒绝。若某历史协议本来没有 seed，先从原绑定的场景/assignment/episode 及哈希中寻找；协议确实无 seed 时，记录为不适用并以完整、可重建且同坐标系的物理位姿证明独立性，公开实际适用的分母，不能声称比较了不存在的 seed。若来源应有数值 seed 但遗失，几何不重叠不能证明 seed 不重叠；保留 UNKNOWN，定位原件后继续。
3. 保留两次先前失败及脚本原字节。先用七类真实输入复核 1200 个普通样本、102 个教师 assignment 的分母与逐源摘要，同时列出可用 seed/位姿及重复；加入缺文件、伪版本、错行/坏 seed 或 NaN、正例拒绝相同 seed/目标位置、教师合法重复、排除相似非目标字段的控制。按实际全部历史重新运行：20 个全新 seed 和已方案定义的位姿与每个适用来源无冲突；保留历史原件向量与两个重复例外的分层。正式绑定不因补读历史改变，原有一次 BEGIN 与付费授权继续适用。
