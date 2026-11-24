# 毕业设计交付与离线演示

**研究验收尚未完成。** 11 月 24 日新增四批静态抓放开发试验，并补测门控和运动故障恢复。原论文的实验记录截至 11 月 23 日。下表印本与后续实测可按日期分别引用。[开题指标与新增实验总表](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-proposal-experiment-qualification-20261124/stage-summary.public.md)

G1 后续安装实验复核了 8 个停机姿态，并在 4 个新摆放上对比两种标记安装。新安装在历史停机姿态中可见 7/8，独立抓放两组均为 0/4。各组首拒的实际图像、独立物理结果和三个操作阶段的证据见[标记安装开发实验](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-marker-mount-20261124/step-report.md)。

题目为《面向边缘智能场景的小型机械臂云边协同控制系统的设计》。11 月 24 日的论文长稿共 38 页，七章叙述正文有 33,326 个汉字，整份 Word 有 37,259 个可印汉字。正文计数剔除标题、图表、代码、摘要、书目及附录。Word 的中英文合计字数为 42,499。实验记录截至 11 月 23 日，各章附同一次试验的来源与复算依据。[逐章字数及印本文字核验](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-manuscript-length-20261123/length.public.json)

| 交付 | 用途 |
| --- | --- |
| [论文长稿 PDF](../../../artifacts/thesis_report/graduation-20261123-expanded/云边协同机械臂毕业设计.pdf) · [可编辑 Word](../../../artifacts/thesis_report/graduation-20261123-expanded/云边协同机械臂毕业设计.docx) · [七章稿源](expanded/manuscript.md) | 阅读坐标与误差推导、控制过程、成本与恢复对照、实验分母及失败分析 |
| [11 月 23 日简稿 PDF](../../../artifacts/thesis_report/graduation-20261123/云边协同机械臂毕业设计.pdf) · [原 Word](../../../artifacts/thesis_report/graduation-20261123/云边协同机械臂毕业设计.docx) · [原稿源](manuscript.md) | 复核原 26 页阶段交付的文本与指纹 |
| [可编辑答辩演示](../../../artifacts/thesis_report/graduation-20261123/云边协同机械臂答辩.pptx) | 投影片与逐页讲者备注，列出可以现场核对的数据出处 |
| [抓放开发实例回放](../../../artifacts/thesis_report/graduation-20261123/抓放开发实例回放.gif) · [逐帧来源](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-pickplace-playback-20261123/playback.public.json) | 从历史开发位姿 01 的原始相机选出 107 张画面，沿九个动作查看。抓取与释放的过程无伺服画面，对应位置标有采样间隔。该批独立物理成功 5/20。 |
| [验收指标与证据矩阵](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/requirements-evidence.public.json) | G0–G5、B0–B5 以及 INITIAL、METHOD、FINAL 的目标、实测范围和前置证据 |
| [阶段总结](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/stage-summary.public.md) · [软件回归回执](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/full-validation.public.json) | 复核软件首轮结果、独立串行复验、工程交付及研究验收状态 |
| [Harness 运行说明](../../harness.md) · [开题报告](../../开题报告_集成电路工程_20261024.md) | 系统的正常命令入口和开题指标 |

## 现场演示

从完整研发检出的仓库根目录执行下列命令。第一个命令只需要 Python 3.12 的标准库。它重新读取原始公开报告、各运行的分母和 SHA256，并与交付的证据矩阵逐项比较。

```bash
python3 -m scripts.graduation.demo
```

现场可分别查看以下结果。

| 观察对象 | 可复查的结果 |
| --- | --- |
| 真实 RGB-D 几何 | 三个留出摆放中 SUBPIX 得到 159/162 个有效顶心估计，条件误差 P90 为 6.869 mm。三种视角分别列出成功帧数与误差。[盲评与深度负控](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/perception.public.json) · [三视角画面](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/calibration-views.public.png) |
| 成本与局部恢复 | 两个已发送的逻辑请求在软件账本中计 122 个应用字节。同一释放后故障下，局部修复改写 1 步，完整剩余重规划改写 2 步，两者的待执行列表都没有已完成的 RELEASE。[软件对照](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/decisions.public.json) |
| 固定 TCP 的真实物理控制 | 完整抓放在 5,013 步结束。逐步复算覆盖 0.5 秒抬升后窗的 121 个状态和 1 秒释放后窗的 241 个状态。无接触、不可达、超时、急停和空手放置各执行一次。[六个工况](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/step-report.public.md) |
| r593 图像驱动的首动作 | r2 在第 120 步启动，91 个反馈检查通过。第 848 步的反馈和终止图像都没有辨出标记 ID 7，控制器拒绝继续，安全停止。此段实际运动 728 个物理步，首动作后置检查尚未发生。[实际指令、Shield 决策与图像读回](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-guarded-clock-20261123/vision.public.json) |
| 正式教师 | 仅一个组取得过正式运行身份。11,109 帧、6,240 步后，LIFT 后置的升高与稳定均为 UNKNOWN，其余八组未执行。[正式采集](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase6-20261122/validation.public.json) · [冻结原件再读](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase7-20261123/vision.public.json) |

下两条命令完成可运行的现场演示。第一条从钉住的 Git 对象取出打包源码，在新目录创建干净的虚拟环境并安装 wheel。准备本地 wheelhouse 时，需同时包含 Python 3.12 / 当前平台对应的项目依赖、传递依赖以及 pyproject 的构建依赖。第二条使用安装好的 CLI，在另一个新目录重新执行决策对照、准备场景并读取新清单。命令中的环境变量分别指向已有离线依赖目录、两个尚不存在的输出目录和项目开发解释器。

```bash
python3 scripts/graduation/verify_installation.py --source-checkout . \
  --revision 6416a6cc --wheelhouse "$WHEELHOUSE" --output "$INSTALL_OUT"
PYTHONPATH=src:. "$PROJECT_PY" -m scripts.graduation.demo \
  --cli "$INSTALL_OUT/venv/bin/bigsmall-harness" --output "$DEMO_OUT"
```

有本机封存视觉数据时，在第二条命令末尾加 `--calibration "$SEALED_CALIBRATION"`。该目录需含 `raw/`、`estimates/` 和 `sensitivity/`。程序先核对当时封存的像素估计摘要，再对齐同一步的独立物理状态，比较复算报告的全部字节。无私有数据的检出可运行公开证据演示及新场景准备。若要读已有场景，执行 `bigsmall-harness evidence <episode>`。其输出包括阶段、已验证文件数和清单指纹。开发轮的离线依赖清单及原始 CLI 退出码随安装回执提供。[安装回执](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/installation.public.json)

同一命令还接受 `--physics "$SEALED_FIXED_TCP_RAW"`，可与标定选项同时使用。传入含 `seal.json`、`steps.jsonl` 和原始控制回执的固定 TCP 目录后，程序重新核验六个工况，按真实步号重算完整抓放及两个保持窗。可在新输出目录的 `physics/window-samples.jsonl` 中逐行查看 362 个窗口采样。[物理评分回执](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/physics.public.json)

## 重建论文与核对原件

论文从七章稿源、公开标定图像与数据表生成。构建解释器需要 python-docx，绘图解释器需要 Matplotlib。主机需能调用 Pandoc、LibreOffice、MuPDF 的 mutool，以及 Poppler 的 pdftotext 和 pdfinfo，并具有 Noto Serif CJK SC 和 Noto Sans CJK SC 字体。目录页码在 PDF 首次排版后写回 Word。长稿从同稿的 LibreOffice 统计读出字词与字符数，从实际 PDF 读出页数，更新 Word 文件属性后重新导出。

```bash
"$DOCUMENT_PY" scripts/graduation/build_manuscript.py \
  --manuscript docs/thesis/graduation-20261123/expanded/manuscript.md \
  --plot-python "$PROJECT_PY" --soffice "$SOFFICE" --output "$DOCUMENT_OUT"
```

答辩稿的形状、表格与逐页讲稿保存在可复现构建器中。使用提供 Artifact Tool 的 Node 环境运行 `node scripts/graduation/build_defense.mjs --work <新校样目录> --output <新文件.pptx>`。工具环境变量与入口列在脚本开头。[答辩稿构建器](../../../scripts/graduation/build_defense.mjs)

完整 RGB-D、逐步物理记录、数据库与模型按项目原有边界保存在本机。公开报告提供分配、运行范围、分子、分母和文件摘要。正式研究的新样本、现场硬件，以及学院的成果认定分别需要对应的原件和验收记录。
