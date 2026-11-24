# 130 mm 采集准入与现场资格步骤报告

原 d02-01 的分配成功。旧采集入口在取得设备或创建 attempt 前，用离线软件门解释 130 mm 几何门，拒绝了原封存批。此次改动将签发与采集接到同一资格验证，待执行批的门副本、来源、预检和当前注册均须一致。发生原始拒绝时实际新增物理作业为 0。[原始采集拒绝](../round-g1-radial30-contact-20261125/capture-rejection-before-reservation.public.json) · [Astra 计划](plan.md)

## 冻结源和唯一开发机会

复核计划 25 个输入和原 567 份运行时文件。新代以失败代为直接父代，仅开发分配/采集入口和开发装配登记两份源码改变。控制器、Shield、相机、源资产、观测器、五个独立评分源、静态筛查以及父代软件预算均逐项匹配。新入口也进入评分源清单。原批的 4 个文件保持原 SHA，旧批无 attempt、instance 或额外痕迹。新 d02 标签携带父代、原分配、单槽分配、拒绝日志和计划 SHA。固定设备互斥下复核旧批，新批及每次物理 attempt 独占创建。原批和部分中断都保留。[冻结源差异与继承关系](runtime-qualification.public.json)

| 项目 | SHA256 |
| --- | --- |
| 父代 | `2d67f55f990226db232ac8c09ee454d2ae40fabc31b43156ff05f5d069dd372d` |
| 新代 | `5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212` |
| 130 mm 静态门 | `4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178` |
| 新代原生预检 | `1a84ed4bf7a1b8f245afb2fb6fca4639cf827849285b4bd730aa7fa4f16c4589` |
| 两个新盲读封印 | `5d7accf7d9a95e78102c344c82ff5998e6cdbbffb44e4154caa8cf3645473e18` |
| 现场核验及 100 份原件索引 | `d88898793fc0b0e816e934706020fb68420587bbb18925f333b5a9e8645b8764` |

失败试次重新登记为 `train-radial30-contact-d02-02`，沿用 d02 的原摆放和 seed。两个标签共用一次物理机会。新的 d01-01 先决条件只读取该代替代 d02 的双读独立结果。四个新摆放须已有同代独立完整成功，两个历史危险区均有核验，且训练与选择的来源摘要一致。

## 软件验证

默认 pytest 临时目录运行相关七个测试文件，78 项全部通过。缺包反例使用真正的独立副本，在临时目录删除仅 ID8 的受测包，确认拒因是该文件缺失，并复核原包 SHA。多进程竞争同一 attempt 只产生一个胜者；保留的部分写入同样拒绝第二次消费。回归日志 SHA256 为 `9fc36b52de9536aee9d64f16352f1b68c638c8dfc97b0b3c01bbe45a233f342c`。

在隔离冻结代码中调用真实解析器的 `issue-training` 和 `capture`。新批只写入临时夹具。合法 d02 通过原资格、盲读、几何和单槽证据检查，抵达原 collector 的预留回调之前。随后的软件边界中断，0 次 worker 和 0 物理步。另 14 项测试覆盖错门、源或副本 SHA、旧代/旧标签、错组、重复分配、缺先决、改资产或评分源等拒绝。[临时 d02 入口见证](capture-boundary.public.json)

另以明确标识的合成记录验证 d01 和四槽的 7 项行为，包括外代或危险 d02、两个未到历史危险步的情况以及无完整训练成功。符合条件的合成 d01 和合成 e01 各到达一次预留前边界。临时夹具中的四个 e 标识均已随测试目录释放。[合成 d01 与四槽见证](synthetic-evaluation-boundary.public.json)

## 新鲜现场资格

使用原历史资格摆放/seed、顶视相机 `f33940579c533afe`、原解释器和独占 EGL，实测剩余磁盘 69.73 GiB。每个新作业都有独立 owner/lease，四次复位完成后均释放。双码选 7，单码分别选 7 或 8，全遮挡拒绝目标并原地保持一次。完整四类检查为 12、12、12、10 项；11 项负控全部拒绝。0 积分步、0 运动命令，232 项原生导入逐项匹配。919 份正式原件和八条已有账本记录已复核。[原生相机、复位、读回与原件](runtime-qualification.public.json)

两个新独立进程各读四个新 RGB-D 包，得到相同封印。与父代相同复位逐包比较，各检查 10 个评分字段，包括逐码估计、身份、可用性、顶点和 TCP、仿真时间与步数。4 组共 40 项完全相同。新采集帧、源目录和新封印均已独立保存。

## 运行命令

从研发工作树使用下列命令。资格负责人执行前两项，协调人负责后两项。下列命令的分配及真实运动成果另作归档。

```bash
PY=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python
G=5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212
S=4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178
SCREEN=artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/screen-selection.public.json
export MUJOCO_GL=egl PYTHONPATH=.:src
"$PY" -B -m scripts.graduation.g1_visibility_trials prepare --radial-contact "$S"
"$PY" -B -m scripts.graduation.g1_visibility_trials preflight "$G"
B=$("$PY" -B -m scripts.graduation.g1_visibility_trials issue-training "$G" train-radial30-contact-d02-02 d02 --gate "$SCREEN" --gate-sha "$S")
"$PY" -B -m scripts.graduation.g1_visibility_trials capture "$G" train-radial30-contact-d02-02 "$B" d02
```

| 私有操作 | 精确命令 JSON SHA256 | stdout SHA256 | stderr SHA256 |
| --- | --- | --- | --- |
| `prepare` | `89b995cf2bef700eeda04aa1a349e4cc3661e0ac11ff170ce0254e6119a61f82` | `566a34854d23b07e7b3a957b2af871c9676510517d2935dd56c38bf979e2258e` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `preflight` | `ae519d8be1c4dcbe121bd58be1b558e77409f82a79b17927f9f885ac9be12f57` | `c0a8741af23aa1db5b6c468b85472a81307cd2873e783ab8ca439af7b4357be7` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

私有资格复核脚本 `admission30-runtime-audit.py` 的 SHA256 为 `e41fdc1906b1de3d59d5175e94ed5ae4cc06d091f110f8a95c989764298bc374`。
