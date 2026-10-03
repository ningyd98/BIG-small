# RoboMIND 官方小样例实际验收

状态：**REJECTED_RGB_ONLY**。魔搭官方 ZIP 已直连下载并通过上游 SHA256 验证，大小 180,163,745 字节（约 172 MiB），保留原归档及完整提取副本。网络严格绑定 `enp7s0`，用指定数字 DNS，TLS 验证开启，允许 `modelscope.cn` 与中国 CDN 域名 `cdn-lfs-cn-1.modelscope.cn`，没有代理或系统隧道回退。

实际包含一个任务的两条 600 帧真实轨迹，`sim=false`。有三个 RGB 相机流及机器人状态，但**没有任何深度数据集**；它只能作为 RGB 机器人演示辅助样例，不能纳入 RGBD 数据集验收。RGB 首帧为 640×480、uint8；关节维度为 8，末端位姿维度为 6。原始时间戳、样例相机标定均未提供，不虚构。

精选固定版本：`b6ccc32d861713fdf786b9f237a1bcfb51a1063b`，上游 SHA256：`dc4ee040d8604b00612af18b7133b269cd936919c9dca7c65c80fc5916ae7604`，许可 Apache-2.0。完整样例已安全提取在 `/home/ningyd/datasets/BIGsmall/inspections/robomind_curated/modelscope/b6ccc32d861713fdf786b9f237a1bcfb51a1063b`，不创建 RGBD 发布完成标记。

正式归档入口增加了 ZIP 支持：完整成员 CRC、路径与特殊文件检查、展开及磁盘额度、选择性流式解压、摘要绑定和原子发布。档案测试 35 项通过（新增 11 项先失败）；Ruff 与 mypy 通过。没有修改原完整数据配置或 RoboMIND RGBD reader。
