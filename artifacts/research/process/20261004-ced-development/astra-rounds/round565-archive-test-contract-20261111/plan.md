# R565 Archive Test Contract Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans；父流程内联执行，无新审查。

**Goal:** 只修正新测试桩契约及两项静态检查。

**Architecture:** 保持新离线工具及全部历史输入冻结，仅改测试文件三个站点。

**Tech Stack:** Python、pytest、Ruff。

**Spec:** 本轮request.json；实际planner_model=gpt-6-astra。

## 问题、证据和前置

已核验6项指定输入SHA及两个gzip解压字节。R564 first-implementation.log为20 passed/1 failed：CLI测试verify_archive桩缺真实返回中的passed_cases，打印时KeyError。first-ruff.log记录F401 unused Path、B023循环year未绑定；原shell末尾cat导致退出0，不能当作Ruff通过。旧日志与源码快照保留不改。这里不是生产或真实raw失败。

实施前核对plan.json精确SHA；使用原app绝对Python、worktree cwd和src PYTHONPATH。源码或失败范围漂移则停止相应修复。无模型/网络/硬件前置。

### Task 1：仅三个测试站点并GREEN

**Modify:** tests/test_molmo_multiscene_archive.py；其余文件实现不变。

- [ ] CLI桩derived_summary加入整数`passed_cases: 0`，保留valid_suite=True、all_cases_pass=False及原断言；不改CLI容错逻辑。
- [ ] 删除未使用的`from pathlib import Path`。
- [ ] 仅循环内Later.now改为`def now(cls, tz=None, _year=year):`，返回`datetime(_year, 1, 1, tzinfo=UTC)`。不动另一个非循环Later类或两个年份、即时消费顺序。
- [ ] 先核对diff只有上述三个站点，冻结新verifier源码SHA仍为8dd2dd9fb046460910cf62bf277d56952e00b8dfef20615cbe9869fe2f78f177。
- [ ] 原app Python运行`-m pytest tests/test_molmo_multiscene_archive.py tests/test_molmo_multiscene.py -q`：新21+旧85全部PASS；准确保存数量和原输出。
- [ ] scoped Ruff检查两个新文件并单独保留退出码，git diff --check通过；保存步骤报告后继续R564原七案独立只读派生核验。

## 验收边界

三个测试站点外无实现改变；不重构fixture、不改生产/原harness/registry/raw/预算，不新增审查。计划不宣称修复已通过。0新增load/generation/paid/hardware，真实核验沿用R564限定离线流程；软件GREEN不替代真实或正式验收。
