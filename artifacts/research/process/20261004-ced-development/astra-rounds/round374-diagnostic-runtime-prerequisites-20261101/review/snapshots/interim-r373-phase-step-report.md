# R373 全流程诊断重跑（进行中）

用户要求：重跑全流程，继续总结问题。实际 Astra 计划见 [plan.md](plan.md)；原始结果位于 `preflight/` 与 `implementation/`。此报告将在全部有界阶段结束后更新，当前不得解释为全流程通过。

## 本轮基线与边界

- HEAD：`8089743604be33ab107853f86894de211f7bf259`。
- 实际验证包含工作区保留的 `local_temporal.py` 性能候选及既有未提交测试；1050 个源文件、11,266,696 字节的基线见 [源清单](preflight/workspace-source-before.json)。因此结果不能单独归给干净 HEAD。
- 一次收集得到 4732 个节点、283 个模块，按 [分配清单](assignment-manifest.json) 互斥分组。原 `coverage-manifest.json` 是保留的过程快照，当前逐节点合并结果以 [R374 派生覆盖清单](../round374-diagnostic-runtime-prerequisites-20261101/reporting/coverage-manifest-live.json)为准。
- 本轮不修产品/测试，不升级依赖，不修改旧 raw、golden、实验数据库或嵌套工作区。全部新运行输出隔离保存。
- 软件、MuJoCo 引擎回归、浏览器软件 fixture、CED 干跑和正式研究分别记账。完整 UTC 两后端已在本轮通过，R371 相关五项短回归也都有本轮新通过记录；仍不代替原时间额度和正式研究验收。

## 已完成的短阶段

| 范围 | 本轮结果 | 解释 |
|---|---|---|
| Python 编译、合同示例、pip check、模型控制秘密扫描 | 通过 | 不代表功能或真实研究通过 |
| Ruff format | 失败：135 个文件待格式化，705 个已符合 | 原始输出保留，未自动格式化 |
| Ruff check | 失败：1137 项，39 个文件 | E501 982、I001 93、B023 32、E702 22、B905 4、F401 3、E731 1 |
| mypy 产品包 | 失败：539 项，18 个文件，检查404个文件 | worker_runtime 188、visual_bootstrap 125、operational_windows 77、visual_supervision 54；尚不能归因于 UTC 修复 |
| 文档检查 | 未通过，18 项命中 | 包括引用/文本扫描问题；扫描命中不自动等同真实秘密泄露 |
| 中文说明检查 | 631 个文件缺少所需说明 | 仓库级维护检查，区别于功能失败 |
| 前端 Vitest | 43 项通过 | 原始 JUnit 已保存 |
| 前端 app/node TypeScript、ESLint、构建 | 全部通过 | Node v22.23.3；构建写入本轮新目录 |
| 前端 Prettier | 11 个文件未通过 | 未改写源文件 |
| selection / foundation / power | 各退出3，分别记录480/120/120条NOT_EXECUTED | selection/foundation未请求执行；power报告前置不足、未运行完整方法先导，assigned_denominator为null；不计实际研究分母或成功 |
| INITIAL | 退出3，拒绝冻结 | 缺少独立编制的完整资源预算；未发布 INITIAL |

## R374 编排恢复与当前进度

原普通组01–04各到900秒上限，分别已通过196、154、181、179个节点；组04另有9个失败。原组05随后运行约30秒，为更换编排而中断，保留156通过、40失败和1个setup-only节点。四个超时与一次主动中断分别记账，原组05没有伪造终态文件。

实际 Astra [R374计划](../round374-diagnostic-runtime-prerequisites-20261101/plan.md)批准新路径环境、一次短诊断与从未启动尾部的限额续跑。旧进程组已按身份核对后停止；新环境下原level0 API节点2.501秒通过。这说明单例可以在新隔离进程完成，不能单独区分旧沙箱与测试顺序的影响。九个writer-binding失败确认缺少R223资源环境变量；补齐后的唯一限定复验9项全部通过，外层45.009秒，旧失败仍保留。

完整UTC memory于2026-11-01T04:19:35Z结束：1 passed/0 failed/0 error/0 skipped，pytest2355.490秒、外层2356.436秒；三个场景原始case、资源侧车和JUnit齐全，2647项资源均观测到清理完成，cleanup_errors为空，源前后无漂移。它仅是CPU软件诊断通过，不替代原双backend合计600秒验收；当前工作区仍包含未提交的local_temporal候选，不能由此宣称候选性能提升。SQLite也于2026-11-01T04:58:50Z完成：1 passed/0 failed/0 error/0 skipped，pytest2353.836秒、外层2354.930秒；三个场景与2639项资源清理均完整，源无漂移。两后端外层合计4711.366秒，因此原合计600秒验收仍未满足。其余T3节点也已结束：两个启动节点通过，五个终态/公共读取节点失败；其中四个失败属于测试工厂空manifest与公共reader契约不匹配，另一个commit_close故障钩子未触发，早期异常未从持久记录恢复。T3总计4通过、5失败、0超时。剩余覆盖清单已经冻结并于2026-11-01T05:27:40Z开始执行：组01–04各追加最多300秒，只运行旧尾部未启动节点；组05沿用原900秒中保守扣除31秒后的869秒余额；组06、closure、MuJoCo与浏览器沿用各自原额度。总墙钟继续使用原R373开始时刻，不重新计时。实时合并统计见[R374覆盖清单](../round374-diagnostic-runtime-prerequisites-20261101/reporting/coverage-manifest-live.json)，历史失败不会因新环境通过而删除。

Astra另确认仅将组01的phase12_2_runtime_authenticity模块与组02的operational_windows模块稳定置后，以降低其他模块失去执行机会的风险；这不是对余下节点耗时的已证判断。旧清单/脚本保留，新`continuation-v2/`的节点多重集合、完整子项对象、预算和脚本字节均与原版一致，唯两个组内顺序变化。旧等待器已单PID停止并回收，当前T3进程未受影响，新等待器已确认十个前置阶段回收并开始续跑。

当前44个姿态标记相关失败（关联36、范围集成8）在相同登记来源校验处被拒绝。只读Git历史核对显示，配置绑定10月5日版本的marker_association.py，而当前源码已在10月17日加入运行时间域逻辑；这是来源版本不一致，旧登记与原件继续保留。另1项资产注册表测试发现assets/manifest.yaml登记SHA与scene.xml实际SHA不一致；二者都与UTC修复前提交相同，见[R374资产只读审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/asset-manifest-readonly-audit.json)。4个中文检查测试失败，分别涉及29/9/2个公开接口说明缺失，以及2330个已跟踪可审计文件未进入默认检查集合。

工作台模块另有6通过/1失败，最后WebSocket用例首事件预期run_state、实际job_created。R374模块级SIMULATION_RUNTIME_DB覆盖了各测试自己的临时artifact目录；实际Astra已生成[R375限定计划](../round375-diagnostic-database-scope-20261101/plan.md)，并对新adapter作两次复核。待当前全部阶段终态后，仅移除该环境覆盖、同序复验原7节点一次，尚未执行。原失败、预算和冻结runner不改写。

## 待完成

普通六组续跑已完成预算记账，尚有未完成及未启动节点；三个closure组、关键MuJoCo模块和两组浏览器用例仍在继续，之后执行R375限定对照。P6九节点已结束为4通过/5失败。单组超时后保留已完成和未完成明细，再继续独立组；仅实际Astra明确批准的环境诊断允许复验指定节点。

第六组末尾的visual_full_effect_requirements子阶段只剩1.045秒实际执行额度，外层1.529秒即收口；该中断不能当作模块本身耗时超标的证明。较长的运行用例也须区分实际慢执行与等待：Phase12 validation用例确实调用完整生成流程；闭环首个心跳用例约289秒时累计CPU仅4.35秒、线程等待、无计算子进程，只有只读/proc线索，尚无调用栈根因结论。

完整 UTC 每后端诊断上限3600秒，其他七个T3节点各600秒；原双后端合计600秒验收仍未证明。过程计时仅为本机诊断，不能作为受控性能基准。

## 已确定的交付限制

本轮一次远端预检在沙箱内因DNS失败；唯一环境重试获准在沙箱外运行后仍因TLS握手中断而退出128。详见 `delivery/remote-preflight*/`。当前远端SHA不可验证，不能声明本地、上游、远端一致。

版本元数据探测曾查询未安装的发行包名 `opencv-python`，只读核验确认实际安装 `opencv-python-headless 4.14.0.94`；该探测错误不算OpenCV产品缺失，原说明保留在 `preflight/version-probe-note.json`。
