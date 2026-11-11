# 缺失表达协议修复完成

Molmo原生解析器现将精确完整缺失句`There are none.`映射为既有`ABSENT`，保留原始文本、绑定与计数。现有`ABSENT`、规范点和单终止标记处理保留；近似句、附加解释、混合点/缺失、双终止或截断仍拒绝。点标签内的缺失矛盾也会拒绝，输出上限继续优先判INVALID。

本轮只修改解析器和两个测试文件。基线162通过，新增31项覆盖后共193项通过，Ruff/diff通过；一次独立审查未发现问题。原PlanningPipeline在目标缺失时1次查询停止，目的地缺失时2次查询停止，返回REQUEST_MORE_OBSERVATION且合同为空，不进入cloud transport。

N01/N03两份冻结输出的只读回放均得到ABSENT；各25bytes、原SHA不变，全部422份旧运行文件byte/SHA/mtime未变。旧c071工作区完整归档复核仍为历史4/7，本次没有重跑七案，也不能据此宣称6/7或新推理表现改善。

本轮真实加载、生成、云端请求和硬件调用均0；模型/提示/云端规划与几何门不变。新修复在codex/molmo-absence-protocol-20261111分支，旧实验工作区保留。P03选点问题与正式/实物验收不在本次交付内。完整raw和原Astra输入清单仅本地，公开为代码、合成测试、计划摘要与安全派生记录，不能独立作为完整远端raw复现包。

可复核材料：validation.json、replay-summary.json、historical-check.json、review-report.md，以及plan.public.md/json；完整本地原计划的SHA记录在公开摘要中。原日志逐字gzip归档，不覆盖历史失败。
