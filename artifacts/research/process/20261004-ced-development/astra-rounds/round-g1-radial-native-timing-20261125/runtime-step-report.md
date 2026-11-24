# 径向性能构建与真实预算拒绝

候选在同机同帧的 675 对样本上，预计原生反馈耗时 P95 为 **81.796 ms**，超过 80 ms 预算，预计最大值 83.898 ms。历史 d02 原顺序的 615 对 P95 为 58.110 ms；第 1080、1088 步额外 60 对的 P95 为 83.786 ms。测量结果包含这两个预先指定的尾部状态。控制器原有 100 ms 实时时限继续生效。[同帧配对预算](paired-budget.public.json) · [原生窗口分段](native-window-segments.public.json)

受限入口以已通过四类零步资质的 115 mm 装配 `36f9658b…` 为父代，为候选保留相机、模型物性、控制器、Shield、独立评分程序及完整源表。软件分别校验两份独立门槛的内容 SHA256。预算依据全组 P95、最大值及像素两个门槛作出判断。实际将已通过语义检验的 release 交给同一资格函数，得到原文 `unreleased radial timing candidate: same-frame window budget has not qualified`。46 个计划输入、110 个语义证据、9 个预算输入均重新核对摘要。[入口拒绝及已存在 7 代清单检查](runtime-refusal.public.json)

像素计时使用父代 565 项源码的隔离副本，逐文件检查后仅网格代码内容发生变化。独立的 778 张、8 个首拒、4 正 16 负、三个 d02 全轨迹以及 22 个姿态各两种像素输入一并通过语义核验。四项初始软件 RED 随记录保留，最终 104 个回归通过。[候选像素计时](pixel-timing-summary.public.json) · [语义结果](replay-release.public.json) · [软件 RED](runtime-expected-red.stdout) · [最终软件回归](runtime-final-software.stdout)

**本轮运行分母**　新增可运动构建 0，新代真实资格预检 0，历史训练签发 0，四个新摆放 0，正式 0，实机 0。两个预定训练标签均未占用。基线零步回调诊断另有独立记录。[基线回调](baseline-callback.public.json)
