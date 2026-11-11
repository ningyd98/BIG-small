# R559 Multiscene Import Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans；父流程内联实施，无额外审批。

**Goal:** 修复研究脚本唯一 I001，不改变行为。

**Architecture:** 仅应用保存的 Ruff 导入块差异。

**Tech Stack:** Python AST、pytest、Ruff。

**Spec:** 本轮 request.json/original-ruff.diff；实际 planner_model=gpt-6-astra。

问题：R558 新测试29项、组合247项CPU通过后，task1-ruff.log报告一个I001。原因是同一模块导入块中scripts导入的排列/空行不符现有Ruff规则。四项输入大小与SHA256全部核验；original-script.py.gz解压逐字等于冻结源码。精确SHA清单在plan.json，原日志、diff和gzip不得修改。

### 唯一任务

**仅修改：** scripts/probe_molmo_multiscene.py。

- [ ] 实施前复核四项SHA和gzip原件；把 `from scripts.probe_molmo_grounded_planner import _admit_resources, _save_capture` 移至cloud_edge导入组末尾，严格等于original-ruff.diff。所有导入仍位于原sys.path设置之后；不移动该设置或其他语句。
- [ ] 比较完整import节点AST多重集合，包含所有模块、名称、别名。仅将此连续导入块按完整AST表示规范排序，再比较整个模块AST（不含位置）；其余节点不得归一化。要求相同，且文本差异精确匹配保存的Ruff补丁正文。Ruff输出末尾的说明文字不属于补丁。
- [ ] 重跑原247项CPU组合命令，Ruff检查新研究脚本/测试/launcher，并运行git diff --check；要求通过。保存新输出，不覆盖原失败。无需新功能测试或真实调用。
- [ ] 记录源文件最终SHA、限定AST等价、测试/lint/diff结果，继续R558既有审查和运行门。按明确路径交付，不修其他问题。

前置：原app .venv解释器、托管worktree cwd和PYTHONPATH=<worktree>/src；写权限按需scoped escalation。超出精确导入变更的新问题交下一轮Astra。验收仅为样式/CPU验证；既有生产、策略、运行时、预算全部冻结。本轮0实际调用，R558 +3加载/+20生成/+3付费仍未消耗，独立审查及实际前置门保持。无未决接口。
