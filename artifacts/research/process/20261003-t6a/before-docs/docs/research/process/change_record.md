# 变更记录

本记录区分文档工作与产品实现。当前过程文档已创建，T1 已完成，T2 已实现并通过独立审查。下列文件依据实际工作区差异登记，不能根据计划中的 Files 栏倒推“已变更”。

| 日期/任务 | 已确认变更 | 验证与证据 | 待回填 |
|---|---|---|---|
| 2026-10-03 / 过程文档 | 新建本目录的 README、阶段进度、执行日志、验证矩阵、决策风险、变更记录、交接文档 | 文档链接和状态审阅；不计为 T1/T2 验收 | 已接入文档索引并同步权威状态 |
| P1 / T1 | 新增 research/models.py、provenance.py 与15项行为测试；历史 verifier draft 显式 LEGACY_PIPELINE；新增 evidence_inventory.md | 合并35项回归及ruff/mypy通过；三项审查发现修复后关闭，见执行日志 | 已验收；未产生正式物理实验结果 |
| P1 / T2 | 修改 vision/observations.py、capture.py、simulation/models.py、simulation/mujoco/camera.py、backend.py；扩展观测测试，新增 test_rgbd_capture_session.py 和 verify_rgbd_capture.py | 同状态采集、元数据完整性、renderer 复用与异常释放；局部25项、合并88项回归及定向静态检查通过；真实平面最大误差2.728 mm | 独立审查通过；config.py 已满足尺寸要求，本任务未再修改 |
| 2026-10-03 / 路线闭环修订 | 更新主执行计划、研究设计、docs/roadmap.md及阶段进度/验证矩阵/决策风险/交接/本记录/执行日志；补同episode反馈、三值验证、有限候选、有界恢复与ACK/启动语义 | 只做文档与依赖一致性检查，实际检查结果见执行日志；不新增产品测试或物理验收 | 产品实现均待后续任务；G/B编号、正式样本与T1/T2状态不变；Jev为可选对照 |

后续阶段每项增加一行：任务与提交前后工作区范围、改动文件及原因、运行命令和退出码、原始产物/哈希、SOFTWARE/REAL_CAPTURE/REAL_VLM/PHYSICS 证据层级、未满足项。历史用户改动与本轮改动分列；不在此复制完整 diff，也不改开题报告 Word/Markdown。

新增研究代码与本轮相机/观测修改基于启动时的文件前镜像核对；初始工作区已有机器人资产、API、UI、运行时和 RGB-D 原型修改，见[初始清单](../../../artifacts/research/process/20261003-phase1/initial-git-status.txt)。这些先前修改不算作本批交付量，也未统一提交。README、文档索引、项目状态、路线图和权威状态已接入本过程文档入口。

收尾发现并保留了四文件的并发增强（缺采集时刻拒绝、载荷边界、采集开始计时、标定变化拒绝），编写来源未确认；已另存差异并通过局部复审及88项合并复验。首次审查版本源码摘要与补丁另存备查。

## 2026-10-03 T2 增补差异

[本轮补丁](../../../artifacts/research/process/20261003-phase1/t2-resume/continuation.patch)仅包含六个相对恢复起点发生变化的文件：observations.py、MuJoCo camera.py、两份 RGB-D 测试、model_control/service.py 的一行中文说明及 assets/manifest.yaml 的场景 hash/version。前四项修复缺时间戳、异常载荷、采集时间、跨 pass 标定和分辨率边界；后两项关闭较大回归发现的既有集成问题。[验收报告](../../../artifacts/research/process/20261003-phase1/t2-resume/acceptance.json)记录 123 项最终通过、实采与测试边界。原 P1 文档/产物的并行更新予以保留，不归入本轮代码差异；未提交 Git。
