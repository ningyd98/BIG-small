# t01 独立冷读场景绑定恢复

规划模型 gpt-6.2-astra。基线 `073ea7d750361b9350a656748f42686a77379fb1`。冻结 442202ab 原 scorer 的第一独立进程退出，原错误为 `payload relation differs on cold RGB-D replay at GRASP/PRE step 1392`。原在线 `APPROACH/POST` 保留同一张图供 `GRASP/PRE`。真实分配场景下检出 ID8 并形成原姿态。原 scorer 的 `read_slot` 退出第一次 `bind_scene` 后才调用 `replay_payload_pixels`。该函数的原观察器依赖这一上下文，默认场景与 t01 新分配场景不同。即使两边 relation 都为 unknown，完整观测字典仍不同。

1. 核对原运行代、原采集封包及失败日志的 SHA256。仅一次 CPU 同帧诊断，用冻结 `frame_from_row` 解码真实 1392 步的 `frames/0167.json`。核对帧 ID、checksum、场景、episode、时钟及原在线所选 ID8。未绑定默认场景和故意错误场景均拒绝；用经过分配、原 receipt、索引和实际 reset 核验的 scene 才能复现原在线读出。上下文退出后必须恢复原默认拒绝。可在同一进程通过该失败见证，无须重跑已封存的全量失败 cold scorer。
2. 新轮仅增加外部恢复 CLI。工作树和冻结树的 scorer 保持原件。用原 `batch_inputs`、`verify_generation`、`checked_case`、`read_slot`、严格全字典比对及签封的原始输入。只临时包装 `replay_payload_pixels`，场景取已验证分配及原生 reset，任何加入点与实际 `receipt`、索引、episode、分配或 generation 不一致先拒绝。调用原函数后恢复原绑定及函数。禁止从待核验 RGB-D 反填绑定，禁止跳过事件或读取旧预测来替代重算。
3. 两个独立新进程运行全冷读，独立 PID、输出目录、原封包和经散列的恢复程序。保留所有技术原件和失败，完整评分科学输出的 SHA256 必须相同，完整观测减免为零。恢复结果另外发布，不覆盖历史失败或写回冻结原评分。报告 t01 原生失败的完整评分，仍计一个训练样本。任一新失配停止并再次立项，无补拍或重派。新增整机、正式、独立正式评分、硬件、远程均为零。

补充 Astra 诊断限定。首次单帧诊断因额外整份 marker Python 字典断言退出，保留原脚本、计划及故障。准许另外一次同帧 CPU 对照，用原已封存的盲读 packet 分别调用原 `matches_online` 核验在线和重算 marker，另录原序列化后首个差异路径及规范摘要。原完整 scorer 的逐帧 payload 全字典等式无豁免。两次完整冷读预算未使用。
