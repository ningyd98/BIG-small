# 教师首个 MOVE_ABOVE 的实测分项耗时

新开发登记 `native-dev-whole-action-20261120-0001`（seed 11920067、两个编码点均为 PNG 1）实测原 Shield PRE 至 POST 为 **150.403384 秒**。真实控制器返回、保持至第 2040 步和终端采集均有原件。原 POST 8 秒门判定 `STEP_TIMEOUT`，墙钟为限值的 **18.80 倍**。测量完整，动作未通过，资格贡献为 0。 [Astra 计划](plan.md) [两次一致的独立计时读回](action-timing-readback.json)

## 动作阶段

| 原件边界 | 实测墙钟（秒） |
| --- | ---: |
| 首 PRE 起点至准入完成 | 0.694106 |
| PRE 准入完成至 dispatch | 0.119519 |
| dispatch 至实际 executor 返回，物理步 120→845 | 45.621115 |
| executor 返回至 recorder 返回 | 0.002019 |
| recorder 返回至 HOLD 开始 | 0.002612 |
| HOLD，物理步 845→2040 | 103.912846 |
| HOLD 结束至终端采集开始 | 0.002554 |
| 终端采集，`acquisition-3385` | 0.034008 |
| 终端采集返回至原 POST context | 0.014604 |
| **首 PRE 至原 POST context** | **150.403384** |

独立 reader 逐一匹配了动作的 1,920 条原生 `mj_step` operation ID。计时 owner 样本与原 guard 按 sequence 和 checkpoint 字段匹配，单调时间均落在同线程 guard span 内。有 21,164 次真实 `ALLOWED` 检查发生在 PRE 加 8 秒以后，最后一个计时检查为 guard sequence 23,517。原 guard 的物理、采集和 owner 检查继续执行，原 POST 仍用同一个 PRE 时钟锚作判定。 [读回程序及结果](read_whole_action_timing.py) [机器结果](action-timing-readback.json)

首个已插桩准备点至 PRE 为 8.594874 秒，包含准备阶段观测到的调用，进程启动前段未插桩。POST context 至动作体退出为 0.767367 秒，动作体退出至原记录的清退完成为 4.284931 秒。这些区间在表内动作墙钟之外。计时原件在 freeze 完成前生成，清退总墙钟由生命周期回执的同钟边界给出，缺少完整的封存和关闭调用分项。 [边界及清退时间](action-timing-readback.json)

## 同一线程互斥分项

从原始嵌套单调纳秒区间复算每个阶段。每一时刻归入最内层 span，外层只保留扣除子区间后的时间，区间空白计入剩余。下表各行互斥，合计 150,403,383,894 纳秒。落在调用体内的时钟开销保留在实测值里。 [分项与样本数](action-timing-readback.json)

| PRE→POST 分项 | 秒 | 占比 |
| --- | ---: | ---: |
| Owner 与 guard 的非 SQLite 部分 | 55.813597 | 37.11% |
| SQLite 检查上下文 | 32.172435 | 21.39% |
| 相机准备、实际 render/返回、校验、转换和拷贝 | 16.330110 | 10.86% |
| RawV3 文件封装、同步写入、metadata、索引和哈希 | 15.257420 | 10.14% |
| 后端边界构造和 detach | 12.626102 | 8.39% |
| 原始帧和会话返回两端编码 | 11.302026 | 7.51% |
| 控制、物理步与 backend/recorder 边界残余 | 3.710203 | 2.47% |
| 无更细探针的其余墙钟 | 3.191491 | 2.12% |

Owner/guard 包含对租约身份、任务截止、RSS、后端配置和物理资源的检查，也包含事件 token/bracket 的生成与守卫回调。各项在该部分内部未再区分。SQLite 是真实检查上下文，未拆单条 SQL 或磁盘 I/O。PRE 至 POST 内，SQLite 与 owner_check 各有 31,238 个 span，完全落窗及与窗正时长相交的计数一致。计时原件的全记录各有 32,704 个 span。生产诊断按 PRE 后至清退起点计 31,240 次 SQLite 检查，边界晚于 POST context。RGB、深度、实例三个 `render()` 返回区间分别为 4.143740、2.336154、2.406996 秒，合计 8.886891 秒，包含 GPU 渲染和取回。相机输出数组的显式拷贝为 0.124812 秒。文件同步打开、写入、flush 和关闭共 1.100042 秒，未测物理磁盘同步。RawV3 帧编码为 11.298543 秒，显式会话编码为 0.003483 秒，均包含 RGB-D 转换及封装。原生 `mj_step` 调用自身为 0.139669 秒。后台线程、CUDA/EGL 内部阶段和进程抢占缺少独立探针。 [原始标签与互斥纳秒](action-timing-readback.json)

## 扰动与复核

计时原件为 35,268,384 字节，236,252 个单线程 span 和 12 个阶段标记。单 span 两次读钟，共 472,504 次 span 时钟采样。探针先留内存，进入清退才由原 recorder 写一次计时原件并纳入原限额和 inventory。原副作用执行顺序和采样密度不变。 [计时代码读回](read_whole_action_timing.py) [计时原件大小及 SHA256](action-timing-readback.json)

同一 CPU 进程用三个固定归档帧（逐步、隐式缓存和显式三类）做 30 对交替开关探针的回放。每对使用同一图像、深度、mask，按 1 档执行两次真实 observation 编码，以及一次临时 JSON 写入和 flush，输出哈希一致。每组三帧的墙钟中位差为 +0.141 毫秒，范围 −1.100 至 +1.303 毫秒。12 对空载嵌套探针每次留存 8,000 spans，开启时墙钟中位增加 8.521 毫秒，约 1.065 微秒/span。离线回放不包含真实 EGL、SQLite、owner 或活跃 capture session，故保留插桩实测值，不依据这些样本修正 150.403384 秒。 [配对明细及固定帧哈希](action-timing-probe-benchmark.json) [回放程序](benchmark_action_timing_probe.py)

两次独立进程输出逐字节一致，SHA256 为 `4012915b35fc6a1a7e8fdf6f173e373a94375cd0a2b8eced1c1f8dcab8decbf3`。原件的内存负控分别移除 HOLD 结束标记、将原 POST 时钟平移 1 毫秒、替换一条原生物理 operation ID，reader 均拒绝，现场字节保持原 SHA256。定向软件测试 3 项、相邻回归 95 项通过，基线比对无新增 mypy 报告。 [原件负控](action-timing-negative-readback.json) [定向 RED](action-timing-red.public.txt) [reader RED](action-timing-reader-red.public.txt) [定向验证](action-timing-green.txt) [相邻回归](action-timing-adjacent-regression.txt) [mypy 基线](action-timing-mypy-baseline.txt) [mypy 实施源](action-timing-mypy-current.txt)

以下文件名相对于该次本地 `release/run/`。计时 reader 对用到的原件逐项核长度和 SHA256，计时 inventory 与生命周期记录相连。

| 原件 | SHA256 |
| --- | --- |
| `collection-result.json` | `f9bf717b670bc1aefb63f4f366792c2d0bbb638bf2d016e2007bd94cfc95557f` |
| `originals/inventory.json` | `bf9bf9437e219cd755aa46b058a17f6d48975fb44c5bb60a5038a70cc665b53d` |
| `originals/whole-action-timing.json` | `5471cb99a0460cae362bb8f4e58bf7a47bac49032d013abdeff4dc909f937e5d` |
| `originals/partial-originals.json` | `73b149dda6500439623c598ba461f4b76b0ab27446e56dd856c00024cbc53125` |
| `originals/active-checks.json` | `d828604d9fae9d8af588eaeee1c1350cdab4b3fd407afcecea61ac2211f55cf7` |
| `originals/shield/step-1-pre-input.json` | `6fdf7920d9ef946d13102e50695196b7b2dbf80f5bdce18e84f4b71689479481` |
| `originals/shield/step-1-post-input.json` | `9a117a1df56b2db539573aa0b938551894ed0e468d78b7c96a1f114933a71ff1` |
| `originals/shield/step-1-post-result.json` | `72d0d80f99858befc52aeaf2952f5c28d7f9e3e63e90a12d5195eba590621540` |
