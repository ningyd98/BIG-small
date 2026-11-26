# B03 曝光编码器独立复演补充计划

规划模型 gpt-6.2-astra，基线 762eaa285ee89d2339375e16bc6e8eb98f24f2df。

B/P 实拍与两份盲预测已封存。B 连续原生物理与冻结轨一致。两次冷读都因 `independent encoder reconstruction differs: camera_joint_positions_rad` 停止。读回从最终 qpos/dq 使用 mj_forward 重新求解，而原 camera_encoder_pose 从 RK4 后曝光所见的连杆位置及姿态恢复。两套缓冲属于同一时刻但值不同。原相机双 pass 哈希只覆盖时间、qpos、qvel、act、ctrl，无法反解曝光用的所有旋转和平移。无充分的零积分复原路径。[原 RED](exposure-reducer-red.txt)

1. 绑定两份盲预测和原两次失败、冻结代码、采图登记、采集封包及每个封存成员。复演各一次，按原 render_free 在 reset 前进入 on-demand，确保开头、退出和所有步骤之间相机均未实例化。每 tick 只按封存顺序重放已接受的 target、gripper、hold 及一次 step(1)，核对全原生命令账、控制状态和每步物理及接触。
2. PRE 在同一步 PLACE 末命令后、hold/OPEN 前验证。DWELL 在 OPEN+240…+480 核对每 8 步原曝光。直接从原生 live data 调 camera_encoder_pose，不调用额外 mj_forward。逐槽保持组、原帧、步、时间和曝光身份。用 float64 逐位比较九个相机编码器、原 pass 物理状态哈希和积分态哈希；保留端点、捕获状态摘要、命令对应、覆盖量和失败。隐式图计数另见原采集封包。
3. 将已封存的这一份证据交给两次独立冷读，重验绑定、完整性以及组、时刻、错序、伪 pass、尾数和漏槽负控。继续原严格区间覆盖、姿态界、支撑与稳定性判据。冻结光学预测、原物理、正式封存和采集字节全部保留。差异即止。
4. 最多 B 5660、P 5580，共 11240 个 CPU 复演步。复演额外 EGL、曝光、技能运行、整机、正式、硬件、撤离和远程均为零。不得补采。LIFT 首停和在线资格继续单列。
