# R439 最终软件验证首轮原件

最终回归 224 PASS、6 FAIL、2 deselected；pytest 67.73 s，supervisor 68.56162695 s，rc1，reaped=true，未发现 source drift 或遗留进程。Ruff 22 项，mypy 33 项，format 检查通过。此轮没有真实 MuJoCo 初始化、physics 或 render，也没有云/模型调用。

失败分为：冻结 Mapping 未转换为 JSON 可写副本（Shield 与 grounding 证据）；新 TaskContract 使用了队列缩写 PCSC 而非合同枚举（两项注册衔接测试停在真实编译前）；两项测试把 fixture 原有命令及 worker 实际终态归类写错。另有静态导入、闭包绑定和真实类型收窄问题。未修改原始失败输出。

R446 的合成像素衔接测试尚未真正到达目标位置，不能声称验证通过。实际采集阶段尚未放行。已交实际 gpt-6-astra 制定 R447 计划；后续证据以独立新目录保存，不覆盖本轮。详情和所有原始输出 SHA256 见同名 JSON。

Astra 源码复核补充：上文对 guard 两条命令的初步解释不准确。`VisualRawRecorderV3.__enter__` 没有发出 hold；实际 `backend.emergency_stop()` 内部先发出 `hold_current_joints`，再发出 `emergency_stop`，两条都是本次退出产生的 COMMAND，且都应属于 TERMINATION。R447 将验证完整二条序列，不删去其中一条。worker 的 BLOCKED_BY_ENV 来源是 `_run_rgbd` 对本次 RuntimeError 的既有分支，不是通用 RuntimeError 终态规则。
