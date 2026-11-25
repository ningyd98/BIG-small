# G1 合并测试导入隔离补充计划

模型 `gpt-6.2-astra`，基线 `40f9cf2d`。各输入及 SHA256 见同目录 `plan.json`。

**原证与原因**　交付 JUnit 原字节 SHA256 为 27da31800c4f46ed4ada382abab3319f5b0ddd7ba06951e6afd44f1cf3500e55。合并收集先加载 test_recovery_route_v2 → recovery_route_v2 → recovery_native，后者在 import 层置顶冻结 runtime-source 与 src 并预载包。随后仓库 g1_visibility_selection、g1_visibility_replay、g1_visibility_radial_screen 均报 ImportError。分别运行研究测试 57、仓库 G1 测试 188、独立原生兼容 112 通过，后者单列。

**范围与前置**　核对 baseline、JSON 逐件 SHA、冻结读取回执及原运行的解释器/依赖。保留 JUnit 同字节副本，记录原参数及顺序。test_recovery_route_v2.py 已列于 recovery-readback-v2.public.json，保持其原路径、原字节及两项断言。允许在父轮 round-g1-cv-grasp-validation-20261125 新建一份未冻结的 conftest.py，供普通 pytest 原命令自动发现；该文件只对已封 test_recovery_route_v2.py 的精确绝对路径接管收集。测试证据与步骤报告保存在本补充目录。

**实施**　优先在新 conftest.py 内用 pytest_pycollect_makemodule 接管这一文件，其余文件交还 pytest 正常收集。父进程按原两个 node ID 建项，在冷子进程逐项以同一解释器 python -m pytest --noconftest 调用原文件/节点，运行原 elapsed_windows 函数及原断言，传播退出码和失败内容。合并原命令无须添加 -p、PYTHONPATH 或额外 loader；父进程不 import 冻结研究模块。实现者也可采用等价的真正隔离，只要父进程在两种顺序下导入身份正确且所有封存 SHA 继续匹配。不得复制函数作假验证、屏蔽异常、删用例或把全套用例各自分进程冒充合并。

**验收与交付**　先存研究目录在前的原始 RED 和对照顺序；普通 pytest 原入口在两种顺序均 collect-only 成功且相同 245 个原 node ID、无漏重，再实际完整合并运行 245 项并保留 JUnit；反序亦验收集。核三个模块的 __file__ 实指工作树 scripts/graduation，并核父进程无新增冻结路径/包缓存，子进程原两项均运行；原生兼容 112 保留独立记录。最终复核源/结果 SHA、实测记录及冻结回执，记录软件范围，新增仿真、动作、claim、正式样本均零。若另有根因先另立 Astra 计划。
