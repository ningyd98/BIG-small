# 完整文件下载记录 — 2026-10-03

范围依据：用户先前要求“精选集先用”，本轮要求“完整下载”。下载三个新增来源的完整选定文件，保留校验与来源记录；不把完整小包等同于 TB 级全库。

- IndustryShapes：完整 source index/schema；下载 classic test 实际存在的全部真实 RGB/depth 配对，缺失项独立记录。
- MicroAGI01：最小完整 uncut MCAP（69,082,845 B）及来源/许可/任务索引。
- VINS-RGBD：最小完整 Handheld/Normal.bag（505,031,296 B）。
- 复用物理 enp7s0/TLS/allowlist/全局账本，最多 4 workers；全局 250 GiB、保留磁盘 50 GiB。
- 本轮不改应用 reader，不宣称完整原库、机器人动作或硬件验证。

- 完成：Industry完整索引137,313,312B及source schema/card全部SHA通过。
- 完成：Micro完整69,082,845B MCAP与source/license/task_mapping全部上游SHA通过；58 chunks CRC和summary CRC全部PASS，108 RGB+108 uint16 depth。
- 来源缺口：Industry索引923 classic/test，完整分页仅能组成370对（740文件、260,594,428B），553项单独quarantine；原镜像不是完整真实test。
- 进行中：VINS完整505,031,296B包；随后下载全部370 Industry配对。

- 完成：VINS首次传输505,031,296B；本地SHA记录，完整2,924 bz2 chunks/26,197消息及全部索引校验PASS，974 RGB+973标准aligned数值depth。包内无CameraInfo。
- 完成：Industry媒体740文件260,594,428B全下并上游SHA通过，正在执行370帧全量解码/mask和预览QA。

- 完成：Industry 370帧/740文件/771实例全部PNG、上游SHA与mask验收PASS，6场景预览已目视。
- 本轮完成：748原始文件共972,121,479B（927.09MiB），747上游SHA已验，VINS一件本地SHA+完整结构已验。所有选定任务无partial；来源缺口保留，不升级原库或应用reader。
