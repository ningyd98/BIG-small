# OC1 测试输出隔离修复

根审查发现真实 Linux 工厂测试会把新运行结果写到固定的原始报告路径。按 Astra round59 计划，仅给该测试增加 tmp_path 参数，并将共享 artifact 变量改到临时目录；成功和失败分支均沿用该变量。模块源码、断言及其他测试 AST 保持。原始失败、round57 工厂结果、round58 静态证据均保留。

最终版本 root 唯一一次全60测试通过（pytest 0.11 秒、进程 wall 0.285 秒），零跳过；Ruff 与格式检查通过。运行前、finally 和运行后核对70个受保护原件的字节和SHA未变。新 Linux CPU 工厂收据从本次临时目录的唯一文件逐字节复制到 independent-review-round59；旧收据未覆盖。此前两项限定测试和本次60项存在重合，不相加为独立样本。

这关闭测试输出路径缺陷。真实 CLOCK_BOOTTIME 读取只证明本机 CPU 工厂入口及整数时间逻辑；worker/lease/capture 来源资格、实际 suspend/restart、宿主机暂停与 UTC/SI 精度未验证。模型、物理、renderer、decoder、provider、硬件调用均为0。独立源码/19场景探测审查另记其独审报告，不能以本局部报告替代该门。
