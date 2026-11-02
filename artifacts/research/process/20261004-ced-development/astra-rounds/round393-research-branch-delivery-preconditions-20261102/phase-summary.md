# 2026-11-02 测试输入与版本登记一致性阶段总结

用户要求先恢复测试输入与版本登记的一致性，使关键场景执行到原定目标。本轮已完成 T3 夹具、线程连接归属、标记登记、仓库外负例及场景资产登记的限定修复；浏览器 Mock 草稿输入合同已恢复，但默认套件仍有 19 项失败或错误。没有进行新的全仓重跑，不能将以下针对性通过数合并为全流程通过。正式研究仍为 `formal_accepted=false`。

## 已完成的恢复及实际验证

| 范围 | 问题与修改 | 实际验证与边界 |
|---|---|---|
| T3 输入合同 R376 | queued helper 原先创建空 manifest；现在保存完整 ExperimentManifest 快照并隔离嵌套变更 | 新合同 3 项通过；原来失败的 confirm_timeout、prior_bound、公共 memory/SQLite 读取目标分别运行。commit_close 的下一层线程错误单独保留并交 R381 |
| T3 故障诊断归属 R380 | 终态故障钩子应持有正确 patch owner，避免作用域泄漏 | 短合同 3 项、manifest 3 项通过；原 confirm_timeout 一次完整通过，外层 247.127 秒，675 资源、23 份未确认资料保留，accepted=false |
| T3 commit_close R381 | 真实 COMMIT 后用主线程 reader 查询，提前触发 SQLite 线程归属错误 | 仅改为当前线程创建并关闭独立观察连接；新合同 2 项、共享短回归 6 项通过。原长目标一次通过，外层 241.577 秒，678 资源、23 份未确认资料，实际关闭同一 writer 后原生 closed-database 异常到达，完整公共断言通过 |
| 标记 R378/R391 | 冻结 v1 绑定旧来源；outside_root 负例在持久 basetemp 下实际落在仓库内 | 新 v2 只改登记 id 与已审来源 SHA，literal 登记 SHA 固定；旧 v1 不改。真实仓库外普通文件负例修正后，两模块 52 项通过，独立 pose/evidence/assets 23 项通过，所需 75 项全部通过 |
| 资产 R379 | manifest 仍登记旧 scene SHA | 只更新 SHA 和版本为 phase9.reference.v3。真实 registry 正例及两种负例 3 项通过；原真实 MuJoCo 加载/复位、80 步物理推进、160 步 FK 三项通过。scene 及三个 marker XML 全部原字节不变 |

T3 原五个失败目标均已有完整断言通过的针对性证据，分属 R376/R380/R381 的实际运行；本轮没有重新跑九项整体套件。上述通过是软件或软件仿真范围，未增加云模型、真机或正式研究验收。各轮独审分别批准限定范围，原 RED、计划外失败及冻结原件均保留。

标记新登记 SHA256 为 `d009cd6b06b1a429b6c67429c6d4da4c8ea9c4bc0e5f50a81cab237e1d54f8e9`，仍为 DEVELOPMENT_ONLY。旧 v1、新 payload、crosshash、来源/几何/边界拒绝均保持严格，不能升级 UNKNOWN、完整范围或稳定性证据。场景 SHA256 为 `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`；资产版本更新记录当前既有 XML，没有修改模型来迎合清单。

## 浏览器已到达和未到达的位置

R377 仅给默认 Mock 草稿加 `input_mode: "LEGACY_PIPELINE"`；产品 RGBD 默认值、校验、各测试覆盖字段、原等待、断言和跳过均不变。受限 socket 预检拒绝没有启动行为；按原计划在工具批准上下文中只运行一次默认套件，原 1200 秒预算未重置。默认运行外层 454.782 秒，研究页面独立运行一次 22.440 秒；源不漂移、所属进程回收及端口释放均通过。

| 原始测试集合 | 本次结果 | 与旧诊断的关系 |
|---|---|---|
| 默认 40 项 | 20 PASS / 17 ERROR / 2 FAILURE / 1 原有 SKIP | 旧 18 项未通过中 E2E05、E2E22 恢复，其余 16 项仍未达目标；另有 3 项原先通过的 RGBD 本次未达目标。不能说只剩旧问题或默认已绿 |
| 其中 console 37 项 | 20 PASS / 16 ERROR / 1 SKIP | LEGACY 提交已接收，后续排队/执行/等待目标仍有缺口 |
| 其中 RGBD 3 项 | 1 ERROR / 2 FAILURE | 分别未等到 SUCCEEDED、未到 visual-planning 提交、未到 cancel 请求；不能称后三者已经执行失败 |
| 研究页面 3 项 | 3 PASS | SOFTWARE_ONLY；600 groups、4200 assigned/BLOCKED、NOT_RUN、formal=false，页面与导出相等，模型请求 0、物理动作 0 |

浏览器输入合同修复已有两项原失败恢复及正确 LEGACY 接收证据，但尚未让所有关键浏览器场景走到目标位置。这一部分为明确的部分完成，不以研究页 fixture 通过代替默认端到端通过。

## R390 离线诊断：下一阻塞点的证据范围

R390/R392 先经实际 Astra 计划与独立静态审查，唯一隔离离线分析退出 0，内部 0.084775 秒；63 输入、10 份关闭 trace 与原 DB 元组字节保持。只对取证副本进行有上限的只读 SQLite 查询，没有服务、产品测试、在线探针或代码修复。副本记录为 14 job、2 attempt、79 event、2 lease；最终独审批准准确的离线证据范围。

PCSC `sim-619c21103d71` 在记录中的约 1.503 秒后成功。随后的 ETEAC `sim-6364857a907b` 为 RUNNING/attempt 1，开始 10:59:36.009520、更新 11:06:46.974494 UTC；记录跨度 430.964974 秒，配置预算为 30 秒，完成时间、attempt ended 与 lease release 均为空。其余选定任务包含三个 MuJoCo capture，均 QUEUED/attempt 0。

结合 dispatcher 同步轮询 worker 的源码，现有证据支持“ETEAC 同步执行未记录完成/返回，后续任务未领取”。没有实时线程栈或返回探针，内部停点 UNKNOWN，死锁与性能根因 NOT_PROVEN；不能断言卡在 runner.run、清理或某把锁。30 秒配置并未证明异步中断或包含排队的端到端 SLA，队列字段也不等于精确排名。不能通过直接放大等待或改并发掩盖此缺口。

下一修复优先取得 ETEAC 完成/返回位置的证据，再分别判断后续 capture 调度与目标可达性。新的主动探针、产品修复、重跑或策略修改必须先由实际 gpt-6-astra 制定下一轮计划；本轮没有这些行为的新增额度。

## 仍然开放的范围

1. 默认浏览器 19 项失败或错误及上述 ETEAC 未完成问题；三个 RGBD 尚未领取，实际渲染、规划、取消的目标验收未成立。
2. 旧全流程唯一 Python 4732 节点仍保留原终态：1845 通过、54 失败、17 未完成、2743 阶段停止前未轮到、71 未运行、2 排除。64 历史失败、18 历史未完成、11 限定恢复另记。针对性修复不是重算该全仓分母的依据。
3. 旧 4 项中文 checker、运行等待与覆盖缺口及静态债务未修复；此前 Ruff 1137、mypy 539 是历史检查结果，本轮没有重计。
4. UTC 边界软件修复及 5 短、2 长通过证据保留；长场景原合计 4711.366 秒仍超过原 600 秒门，本轮没有重跑或证明实际主机 UTC 跳变和性能验收。
5. selection/foundation、完整 power 前置、INITIAL 独立资源预算、真实 Max、九组独立校准、合格 B0、风险/方法/功效/FINAL 等仍依原门推进；开发回放与软件页面不代替正式研究。

## 检查点、交付范围与证据入口

R389 已重新核对用户授权检查点 fdb2e94：此前 R376/R380、temporal 候选与两个测试已在检查点提交，不回退或重复交付。R393 只在同 SHA、空暂存区及保护输入保持的前置下，将 HEAD 元数据重绑已有研发分支；不移动 main，不替换工作区文件。交付前逐文件独审，提交与推送的实际结果在操作后另记，本文不预先宣称成功。

本次精选交付仅含限定测试/登记/manifest/文档及小型计划、审查、终态与派生证据。完整 raw、运行数据库、forensic-copy、trace、大型导出、重复源码/帧/模型原件和两个 dirty gitlink 留在本地。清单和 SHA256 不能替代完整输入包；历史绝对路径和本地依赖仍限制远端 clean-clone 全复现。提交后生成的原生 Git 回执单独留在本地，不冒称已包含在前一提交中。

- [R376 输入修复](../round376-t3-test-input-contract-20261101/terminal-handoff.json)、[R380 钩子归属](../round380-t3-diagnostic-hook-restoration-20261101/phase-step-report.md)、[R381 完整断言](../round381-t3-commit-close-thread-affinity-20261101/acceptance.json)。
- [R377 逐项结果及旧失败映射](../round377-browser-draft-input-contract-20261101/acceptance.json)、[实际执行来源索引](../round377-browser-draft-input-contract-20261101/execution-source-index.json)。
- [R378 登记版本](../round378-marker-registration-version-consistency-20261101/phase-step-report.md)、[R391 的 75 项验收](../round391-marker-outside-root-fixture-20261102/acceptance.json)、[R379 的 6 项验收](../round379-scene-asset-manifest-consistency-20261101/acceptance.json)。
- [R390 离线诊断](../round390-browser-queue-target-reachability-20261102/step-report.md)、[R392 静态问题收尾](../round392-offline-sqlite-readonly-uri-20261102/final-closure.md)、[R393 实际 Astra 交付计划](plan.md)。
