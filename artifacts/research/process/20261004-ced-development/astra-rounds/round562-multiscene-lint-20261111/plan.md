# R562 Multiscene Lint Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans；父流程内联执行，不新增审查或审批。

**Goal:** 仅修正两处静态检查失败，保持R561行为不变。

**Architecture:** 只修改现有研究脚本的字符串排版与同步lambda的等值别名；无接口或控制流改动。

**Tech Stack:** Python AST、现有Ruff/pytest。

**Spec:** 父流程R562请求、original-command.json及original-ruff.stdout/stderr；实际planner_model=gpt-6-astra。

## 问题、依据与前置

规划阶段实际重跑Ruff退出1，仅E501（原1642行107字符）和F821（原1850行lambda中的exc）。R561原始harness-first-full.log为81 passed in55.35s，仅复用为行为基线，不伪称修复后通过。原脚本以mtime=0 gzip冻结；精确输入SHA见plan.json。

F821发生于except绑定名的lambda引用；已核对同一except第一句error=exc，_io同步直接return action()。本轮只改此lambda内别名，不重写异常处理。在内存构造两处拟议修改并将原lambda唯一exc节点规范为error后，全模块AST相同；未写入实现。E501两个相邻f字符串形成同一JoinedStr。

实施前复核脚本SHA和Ruff仍仅这两项，使用原app绝对Python及worktree cwd/PYTHONPATH。父流程独立R561新增测试可以继续；记录实施时测试版本，不将新增行为纳入本轮。源码漂移、新根因或AST不等即停止相关修改另立Astra计划。

### Task 1：精确两处修正与验证

**Modify:** scripts/probe_molmo_multiscene.py；不修改测试、业务规则、生产、场景、预算或runtime。

**Interfaces:** 全部不变。

- [ ] 保留本轮Ruff RED原件并核对输入SHA。
- [ ] 原1642行拆成相邻 `f"provider:"` 和 `f"{type(failure).__name__ if failure else 'counter_or_raw_integrity'}"` 两行，维持相同缩进层次与括号。
- [ ] 原1850行仅lambda里`type(exc)`替换`type(error)`；其他exc引用、赋值和调用不动。
- [ ] 解压原快照并比较：只定位含case-error.json的唯一lambda，把旧AST该唯一Name(exc)规范为error；忽略位置属性后整模块AST必须完全相同。不得全局规范exc；相邻字符串必须保持原JoinedStr。另确认文本diff恰好这两处。
- [ ] 用 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest tests/test_molmo_multiscene.py -q` 重跑原81项及父流程独立新增项；全部PASS。保存准确数量，不能把新增测试失败当静态修改已验证。
- [ ] 用原绝对ruff执行 `check --no-cache scripts/probe_molmo_multiscene.py tests/test_molmo_multiscene.py`；再 `git diff --check`。保存原输出、AST验证和步骤报告，汇入R561。

## 验收边界

开发验收为限定diff、AST等价、harness与scopedRuff/diff通过；不新增行为测试或整体审查。这里只规划，0native load/0generation/0paid/0hardware；R558七案预算与生产门完全不变，软件验证不替代真实运行。原失败、冻结快照不能覆盖或清理。无待定设计决策。
