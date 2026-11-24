# 首拒姿态采集的相机管理命令审计

gpt-6.2-astra 于 2026-11-24 制定，基线 3cc65630133bba0315907965b224e086c97950a4。父计划的姿态、时序、计数、种子、阈值、分配与条件规则全部继续适用。

冻结失败。首次循环已写出24张源图及第一种安装的16张正常、16张隐藏手部图与32份分割，再因 static capture advanced or dispatched 停止。91项失败原件逐一核实，未生成采集 seal。原目录 cross、原捕获脚本的失败副本、异常与清单保留，完整指纹见 plan.json。该次到此为止，不能接着补另一半或计入决策。

根因。restore_and_capture 在每一个姿态调用 set_camera_position(nominal)，随后才 restore，进行 mj_forward、capture_with_instances 并校验相机，返回 (frame, mask, labels, state_hash) 与 FK 残差。set_camera_position 返回 None，设置固定世界相机的位置，可选参数 look_at_m 在本路径未传入，内部调用 mj_camlight，记一条 accepted camera_position。backend.command_records 返回完整记录深拷贝；原断言把这个相机管理事件也判作运动。get_sim_time 读取 data.time，它会随源姿态复原而改变；total_physics_steps 才是实际积分步数。set_camera_position 记录的 sim_time_s 属于恢复该姿态之前的时钟。

只修新的开发采集入口、其专项测试与必要读回路径绑定。旧 g1_mount_screen、backend、静态实验设置和前轮冻结文件只读，校验本轮父计划408项输入。将新采集的原路径限制精确绑定到 cross-verified，批次发放、采集和读回都引用同一实际 seal。

对两套新建的单侧 backend 分别证实初始化后控制计数为零，命令日志空。每次进入 restore_and_capture 前记录 backend episode identity（未创建时按真实值保留）、物理步计数、原 sim_time、command_seq/日志起点和世界固定 rgbd 相机的位姿/朝向/FOV。核对结束后新增记录恰一条，相对现场 episode、一基连续序号、physics_step=0、sim_time_s 等于本次调用前的现场 sim_time，type=camera_position、accepted 严格为 true、reason=development_camera_translation、after_emergency_stop 严格为 false、position_m=[0.35,0,1.4]、无 look_at_m 或其他命令参数。保存实际完整记录与角色/种子、顺序、各次前后计数。全程真实物理步始终0，每种安装16条相机管理记录，手部隐藏重拍没有新增事件。逐帧实测内外参、标定版本、位置、相机朝向与名义值及父计划一致，正常/去手共状态，FK 和原图复现仍执行既定阈值。将记录和每个检查的结果绑定到封存，任何额外、跳号、非法位置、旋转、时钟错绑、拒绝或运动命令、实际 step 均失败；不清空或筛掉不认识的记录。

先用真实记录形状的纯软件正负控覆盖 0/16/多一条、错误命令、错位/朝向、时钟或物理步、错序和身份，以及同姿隐藏拍摄未发命令；保留预计 RED。通过后独占 EGL，仅在全新 cross-verified 原子创建一次，照原种子重新完整采集24源图+32正常+32去手=88张、64份配对分割。旧的片段贡献0。独立从全部归档记录和图像核查相机、零步、零运动、计数、两侧及盲封存，继承父计划128项离线移位和原有互补触发条件。复核失败清单与冻结原件 SHA；在步骤报告区分初次失败和本次真实静态运行。独立工作可继续，正式/硬件/任务模型均为0，新运动限于父计划条件满足后的已分配开发试次。新根因或超范围失败另行制订 Astra 计划。
