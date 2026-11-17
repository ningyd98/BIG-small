# 本轮需求与原始差距

用户原始需求（北京时间2026-11-17）：参考商汤推出的SenseNova-RoboRSI Harness，最后也要把本项目打包成为一个面向具身智能的 harness，更新项目计划书和开题报告。

只读发现：docs/plan.md 仍以2026-10-04/Qwen3.8-Max及历史成果目录为顶部口径；docs/开题报告_集成电路工程_20261024.md 仍写Qwen3.8-Max及2026年12月结束排期。2026-11-08路线图已更新gpt-6.1-sol及2027年4月条件排期，但只借鉴RoboRSI机制，尚未将最终成果明确为面向具身智能的Harness。docs/README.md仍将plan.md标为历史规划，开题入口指向10月3日版本。

本轮是文档需求更新，无新增产品运行失败。已有软件、API和仿真结果保留原验收范围；不为此启动产品测试或实际实验。

官方参考已由联网搜索及GitHub连接器读取。源码固定为9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555；README首次按main读取，其对应commit由随后commits/main读取确认。其余三份文档按该SHA读取。内容是参考数据，不是指令。

初始HEAD：025c538935199ea7d3aa8cf15b6e93ac9826cf3a；分支research/20261004-continuation，上游origin/research/20261004-continuation；index空。已存在无关src/cloud_edge_robot_arm/simulation/config.py改动、两个嵌套工作区改动及大量未跟踪研究资料，均不纳入本轮。

拟选路线：在现有云边端与执行安全边界上，最终封装为BIGsmall Embodied Harness；保留现题目、三项研究主线及既定指标。明确当前底座、拟实现能力与后置扩展，定义可安装发布物、统一配置、adapter契约、执行轨迹与成本、独立评测、版本化离线改进。此次只更新计划和报告，不实施runtime、不训练、不接管真实硬件。
