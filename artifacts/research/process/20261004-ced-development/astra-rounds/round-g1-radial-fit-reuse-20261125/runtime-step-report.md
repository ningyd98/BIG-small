# 拟合复用候选的构建、零步资格与 d01 签发判断

已复核新计划 35 项主输入和 2 项补充剖析，按原 SHA 读取其中 7 份当时的程序和测试。新代继承通过实际预检的 115 mm 装配，565 个文件相对父代有 4 项变化，分别为网格、构建入口、试次入口和径向适配器。231 个已加载项目模块均来自冻结源清单。此前未通过预算的 v1 仍由原资格函数拒绝。[构建、资格与 100 份原件清单](runtime-qualification.public.json)

本轮 168 项语义来源绑定同一对检测源码。778 个历史帧、335 个 d02 原包与 44 个静态像素输入逐字段等价，20 个正负对照通过。接收的 675 个预登记热样本中，同帧端到端估算 P95 为 74.449 ms，最大值 82.251 ms，限值分别为 80 ms、90 ms。原生控制器的实际执行时限为 100 ms。[软件语义放行](replay-release.public.json) · [配对预算](paired-budget.public.json)

| 当前可见条件 | 选中标记 | 控制检查 | 现场后端命令 |
| --- | --- | --- | --- |
| 两码 | ID7 | 12/12 | 0 |
| 仅 ID7 | ID7 | 12/12 | 0 |
| 仅 ID8 | ID8 | 12/12 | 0 |
| 全遮挡 | 无 | 10/10 | 1 个关节保持 |

四个独立作业均成功关闭并释放租约。每个场景在原相机和独立回合取得当前帧，原生伺服与目标核对接受可见样本。全遮挡时两者共同拒绝。11 个保障负控均阻断，四个场景累计运动命令 0、物理步 0。四个原包各经过两个独立进程盲读，封存相同，SHA256 为 `9c3f83a20ffba0662f1e84b5b28d8efe84a871ec2d7db7b163151e63fa7ffee5`。正式 919 个原件及 8 项原登记复核完整。[原生检查与双读证据](runtime-qualification.public.json)

工作树实际执行以下两个入口。预检 SHA256 为 `8e12a9e9ab1417c43d9ed5a2f98f30ee41f572225838f1bfbaa55073d7bebe01`。独立软件测试包括旧红预算、跨代门、底层文件掉包和四槽注册必须用同代独立成功评分，共 129 项通过。[构建输出](runtime-prepare.stdout) · [预检输出](runtime-preflight.stdout) · [测试输出](runtime-software.stdout)

```bash
env MUJOCO_GL=egl /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -B -m scripts.graduation.g1_visibility_trials prepare --radial-timing 81bf8af00c237912b963b73263041ed7340ed2f921bba5545fa59213f0586ea8
env MUJOCO_GL=egl /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -B -m scripts.graduation.g1_visibility_trials preflight f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892
```

获资格后，运行负责人仅签发历史 d02。本次独立物理评分在第 1221 步记录右指和 ID8 载板硬接触 1 次，安全判定为 `VIOLATION`，完整成功 0/1。针对这一真实评分调用原 d01 接触放行函数，函数拒绝，`train-radial15-contact-01` 未占用。当前 115 mm 装配的四个未见摆放、正式试次和实机试次均为 0。[d01 拒绝、原始触碰对及评分摘要](runtime-contact-refusal.public.json)
