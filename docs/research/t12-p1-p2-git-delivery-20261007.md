# T12 P1/P2 Git 交付记录（2026-10-07）

已验证的 P1（RW1、OC2）与 P2 软件分三次提交，并推送到 `origin/codex/research-20261007-p1-delivery`。每次推送后均核对本地 HEAD、上游引用和实时远端 SHA 一致；这三份收据记录各自推送时点。

| 交付 | 完整 commit SHA | 本次导出候选验证 | 变更路径 / 按路径 blob 字节 |
|---|---|---|---|
| RW1 生命周期失败与计数证据 | `3daddcc96c1d23e928fb4c9a3d868750b6cc37ec` | 66 个唯一用例通过 | 144 / 2660091 |
| OC2 来源关联与失败报告 | `98b8282138ba61367db526d7d8f52e27085f4f9f` | 46 个唯一用例通过 | 312 / 4956330 |
| P2 动作参考与 S/D 计时描述 | `851b80c88c242007a740dae778671bdf98ab330c` | 单次 4 个关键用例通过 | 107 / 923370 |

RW1 与 OC2 均经不同作者独立审查；P2 作者为 GPT-6.1-sol，ROOT 完成独立代码与范围审查。P2 原有验证覆盖为 93 项原通过证据加 R85 修复后 1 项通过，共 94 个唯一节点，未重跑全 94 项。本次候选 4 项用于交付工作区验证，独立记账。281 项依赖前后字节一致，145 个实际导入模块来自候选工作区。

三批完整 Git 空白检查均真实返回 exit2，分别有 134、74、17 条冻结日志、XML 或差异原件的空白诊断。各批当前源码和新文档严格子集均 exit0，逐条原件例外已绑定源与索引 SHA，未分类为 0；历史失败和原始字节保留。完整检查的非零结果未改写为通过。

交付从已推送的 `4d40a65059ab75292fa1842bacf62653829808e6` 起建立独立分支。主研发分支 `research/20261004-continuation` 的用户 `1007` 提交 `34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e` 保留，且不是交付分支祖先。两个嵌套 physics 工作区的修改保持原位。未合并、重置、清理这些材料，未 force push。

R88 处理只读 JSON 展示器的类型误判；R89 将激活收据重复携带的嵌套状态文本改为逐字段摘要，完整 10005801 字节原件保留本地，派生收据为 10702 字节。两轮计划、失败/发现与恢复证据为 local-only，不增加产品测试或真实运行，也未修改冻结载荷。

本轮交付包含限定源码、测试、小型证据及文档。完整批量 raw、运行数据库、CPU 临时原件副本、凭据、模型权重与 SDK 未作为本轮新增载荷；清单不代表完整远端复现包。P2 的 GRASP/mutable contact 与完整 future D 仍为 NOT_SUPPORTED/UNKNOWN，native 为 UNAVAILABLE，依赖完整抓放的九组及大先导批量保持停止。P3 软件派单仅准备，P4 真实 prefix 未启动；本轮新增校准组 0、actual 0、formal_accepted=false。

推送收据：[RW1](../../artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-rw1/root-delivery.json)、[OC2](../../artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-oc2/resume-round86/root-delivery.json)、[P2](../../artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-p2/root-delivery.json)。RW1收据复用既有提交；本汇总、OC2/P2两份收据与最新状态另作有限文档提交；该文档提交之后的最终三 SHA 收据保存在本地 `delivery-final/root-delivery.json`，不通过反复 amend 将收据写入自身提交。

R90 收尾恢复：准备器误把既有 RW1 收据视为应新增文件，现复用字节相同的原件，仅复制 OC2/P2 两份收据；六个选定路径对应五个实际变更，原有 P1/P2 章节保持且未重复追加。
