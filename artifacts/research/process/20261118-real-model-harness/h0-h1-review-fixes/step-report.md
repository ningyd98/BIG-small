# H1 审查修复与重新验收

复核了实际 Astra 计划绑定的 18 项输入。旧 H0/H1 报告与原件留存。本轮只改明确的
Harness 启动、配置、证据和对应测试、说明。[实际 Astra 计划](../../20261004-ced-development/astra-rounds/round-harness-lifecycle-review-fixes-20261118/plan.md)
[独立审查](../harness-lifecycle-review.md) [初版证据](../h0-h1/step-report.md)

| 项目 | 原失败与本轮结果 |
| --- | --- |
| 原生准入 | 旧存在性检查放行了已登记的 Molmo r505 和错误的 GroundingPI。新安装的 bootstrap 在同一原生子进程复用原 R545，核对已加载项目模块及原入口，再委派到原脚本。正确与错误解释器各运行一次 CPU `--help`，分别退出 0 和 2，错误解释器未创建期次目录。 |
| 子进程结局 | CPU 子进程写入真实阶段文件后分别退出 7、收到 SIGTERM。两者报告 `INCOMPLETE_UNKNOWN`，保留原退出值 7、−15，封装退出值 7、143，成本为 null，既有阶段文件逐字保留。 |
| 准备配置 | development seed 44101、相机覆盖和视觉伺服保留于 planned 配置和指纹。effective 来自原 dry-run assignment，实际固定场景且这些选项列为未应用。 |
| 证据阶段 | 拒绝 schema-only、缺 status 及缺绑定文件的完整 PREPARED 声明。原执行器实际生成的 FAILED、INTERRUPTED 清单保留状态、错误原因和实际空值。 |
| 布尔配置 | JSON 的数字 1、1.0 被拒绝，正常 true 的规范配置指纹与初版一致。 |

RED 为 10 项失败、19 项通过，另有两个真实解释器的旧准入复现。最终 29 项 Harness
测试加 50 项原 CLI 回归合计 79 项通过，限定 Ruff 通过。格式预查的单项 import 排序
记录保留。[RED](review-red.log) [原生 RED](native-red.log) [最终测试](final-green.log)
[格式预查](format-preflight.log) [最终 Ruff](ruff.log)

新版 wheel 为 1,627,445 字节，SHA256
`aee16cc067fa57db2871e9bf6652608703054f8d3b0e410eec895ecac1ccd7e9`，从共享开发
工作树构建，保留在本地。源码树外、无 PYTHONPATH/PYTHONHOME 或凭据的清洁
Python 3.12.3 环境通过 help、version、validate、doctor、显式 checkout 核对、
prepare、evidence、重复目录拒绝及 pip check。原生准入 CPU 检查使用同一已安装
bootstrap，保持清洁环境与两个原生解释器各自的依赖边界。
[构建](wheel-build.log) [安装](clean-install.log) [实际命令与退出](clean-verification.log)
[依赖](pip-freeze.txt) [校验脚本](clean-verify.py) [文件与源码哈希](verification.json)

正确解释器的 R545 回执确认 CUDA 未初始化、模型载入/生成/付费请求均为 0。错误
解释器在委派前退出。全轮无渲染和动作，无物理成功或新增研究资格。
[正确解释器回执](molmoer-r505.json) [错误解释器回执](groundingpi-r505.json)
[prepare](prepare.json) [原件索引](evidence.json)
