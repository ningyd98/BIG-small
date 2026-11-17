# MiniCPM-RobotManip 能否替代 Molmo2-ER：BIGsmall 离线实测

测试时间：2026-11-17 至 2026-11-18（北京时间）。本轮结论：**保留 Molmo2-ER 作为当前定位后端。** MiniCPM-RobotManip 的官方入口在本机跑通，但它返回连续动作序列。用同一检查点内置的视觉语言模型尝试复刻当前二维定位接口，8 个查询都没有给出可用坐标或缺失声明。

| 项目 | Molmo2-ER 原生定位 | RobotManip 内置 VLM，文本定位探索 |
| --- | ---: | ---: |
| 可见查询：坐标落在原始实例掩膜 | 4/6 | 0/6 |
| 缺失查询：返回明确缺失 | 2/2 | 0/2 |
| 无效格式 | 0/8 | 8/8 |
| 顶视点对：通过现有 RGB-D 和 OpenCV 初始定位，并核验落在对应实例 | 2/2 | 0/2（没有有效点对） |

三张 320×240 MuJoCo 归档 RGB 分别为固定顶视、seed 43001 的变化场景顶视、持物斜视。每张询问红块顶部与绿色放置区，另有蓝块和黄色放置区两条缺失查询。两边的 RGB 字节和任务短语一致，按各自接口组织提示，均为贪心生成。实例标签只用于评分，深度只用于现有几何检查。判定采用项目的 0–1000 坐标转像素约定，直接核对原始掩膜。Molmo 的两个原始偏差为 3.0 和 3.16 像素；其中固定顶视红块由现有局部关联找回。斜视仅评原始二维命中。顶视几何沿用项目已有的历史回放时钟（采集时刻 +100 ms），因此通过的是离线初始定位，不检验在线帧时效或之后的跟踪。

RobotManip 使用 [官方 Python 推理入口](https://github.com/OpenBMB/MiniCPM-Robot/blob/f666593066641d2c0cef06bc17bfb1e954547674/MiniCPM-RobotManip/vla_infer.py) 和 [固定版本权重](https://huggingface.co/openbmb/MiniCPM-RobotManip/tree/29cb257541e9f96f493abe21174f8892e5dffe3f)。用同三帧、同一条抓放指令、官方默认零状态和 embodiment ID 0，3/3 产生有限的 `float32[30,80]` 序列；CUDA 同步计时约 0.605、0.141、0.139 秒。本轮只保存序列及哈希，没有将这些数值解释成 Panda 的命令。官方的[评测接口](https://github.com/OpenBMB/MiniCPM-Robot/blob/f666593066641d2c0cef06bc17bfb1e954547674/MiniCPM-RobotManip/evaluation/README.md)按机器人动作约定映射向量；默认 ID 和零状态仅作推理探测。定位探索直接调用同一检查点的 MiniCPM-V 4.6 子模型，要求仅返回 `[x,y]` 或 `ABSENT`。最终配置用检查点的双结束符，8 条全部正常结束，输出仍是短句或无关文本。例如，固定顶视上红块、绿区和不存在的蓝块三个查询均返回 “Pick up the left block and move it to the left tray.”。没有将这种答复计为拒答或误报点。

硬件为 RTX 4070 Ti SUPER。现有 Molmo BF16 运行时使用 Torch 2.6.0+cu124、Transformers 4.57.1；8 条点位请求墙钟中位数 0.803 秒，PyTorch 峰值分配约 9.85 GiB。RobotManip 使用 Python 3.12.3、Torch 2.6.0+cu124、Transformers 5.7.0、Diffusers 0.38.0，视觉语言部分 BF16、动作头 FP32；整次候选探测的 PyTorch 峰值分配约 3.44 GiB。首次载入在本机旧环境误触发非官方必需的 bitsandbytes/Triton 编译，因缺少 Python 头文件停止；重跑用同一套依赖的隔离环境，未暴露该可选量化包。未改检查点或官方推理代码。探索性调用首次沿用内置 VLM 单结束符导致到达 96 token 上限；修正为检查点配置后重新生成全组，评分采用修正后的结果。

证据：[逐条答案和计时](answers.json)、[逐帧评分与输入指纹](score.json)、[候选检查点清单](checkpoint-verification.json)、[来源和证据哈希](integrity.json)。完整本地日志、旧结束符诊断、Molmo 原生请求记录和动作数组保存在 `experiments/results/phase9/minicpm-robotmanip-eval-20261118/`。

本轮没有替换默认后端、运行闭环抓放或连接真机。若纳入具身 Harness，把 RobotManip 作为独立 VLA 策略候选，明确 Panda 状态与动作映射后，用相同场景和随机种子比较完整抓放、拒绝执行和故障停止；当前 Molmo＋OpenCV 路径作为对照。

复跑使用 [replay/](replay/) 下的脚本，本地前置条件为 `score.json` 中的归档、通过校验的两套权重、官方代码固定提交和 GPU 锁。按顺序运行：

1. 用项目 round545 记载的 `molmoer-r505` Python 执行 `replay/run_molmo.py <新输出目录>`。
2. 用独立的 MiniCPM 运行时执行 `replay/run_robotmanip.py <新输出目录> <官方仓库的 MiniCPM-RobotManip 目录>`。本次在不包含 bitsandbytes 的独立 venv 中复用 `.venv-minicpm` 的其它包，另装 Diffusers 0.38.0。两个 GPU 步骤均设置 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1`，逐个获取项目 GPU 锁。
3. 用项目应用 Python 及 `PYTHONPATH=<工作树>/src` 执行 `replay/score.py <新评分文件> <Molmo 结果目录>/results.json <RobotManip 结果目录>/results.json`。
