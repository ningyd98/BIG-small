# R123：restart 测试回调的真实 owner 局部绑定

实际 Astra 规划，2026-10-11。仅限定测试修正，不读取正在实施的四生产源、不追加其hash前置。

## 原始发现和独立结论

ROOT只读工具d819ab退出0，在R122 mapping-change中发现restart回调改为：

```python
captured.append((session, runtime._operational_owner.export_record(owner.task_window), _rows(repo)[0]))
```

冻结稿第422行确有该表达式。有限文本复核确认：嵌套check只有append/return；外层test及模块没有此owner绑定。其他helper/测试或推导式中的同名局部变量不会绑定到该回调。因此缺陷成立，属于R122映射未完成；尚未运行到该行，不冒充运行时失败。

原finding/source-index及五份current+copy共10项SHA/bytes核验通过；P5 runtime._operational_owner与export_record(window_id)两来源hash仍匹配R122。原RED1/0，后七预算各0/1。证据路径、字节和hash完整见plan.json。R122原mapping-change及报告必须保留。

## 唯一测试修改

在 `test_restart_terminates_without_reissue.check` 开始处，从参数runtime的 `_operational_owner` 绑定局部owner，确认真实owner及其task_window非空；用同一owner调用 `export_record(owner.task_window)`。保留captured三元组、session.epoch返回、两个restart参数变体及其他断言。禁止借全局owner、其他worker的owner、重建窗口、新origin或产品兼容属性补洞。

## 实施步骤

1. ROOT verifies frozen finding/index, current test and original R122 mapping/reports/ledger pins and two protected P5 interfaces only. Bind R123 plan to same replacement author. No74-input/full repo/product-source rescan; expected current production changes are not R123 failures.

2. Author performs the minimal local owner/window binding correction in restart check only. Preserve R122 mapping-change and reports unchanged as historical partial-mapping evidence; save new R123 mapping-change.json with actual limited diff and before/after test SHA.

3. Record R123 step-report.md/json and update existing command ledger status truthfully without changing counts. ROOT may save activation/input-check. OriginalRED remains exactly consumed1/remaining0 on pre-R122 draft; do not rerun or relabel it as covering repaired branch.

4. Resume original remaining seven R113 commands only after test correction and independent production readiness. Original scope proof/format/static/GREEN validate the correction within existing budgets; no extra compile/import/collect/test/static/probe is authorized. Unexpected failure follows next Astra plan before repair.

## 边界

独立R113生产实施可继续；本轮不要求其保持旧hash，不扩大其六路径范围。只写上述测试局部与R123新mapping/步骤/激活元数据；不改R122历史记录。禁止新增产品/test/static/Git/actual运行；原七命令是继承额度而非新授权次数，修复本身不增加一个单独验证命令。最终scope/static/GREEN与独审尚未完成，仍为 `LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO`。新异常或范围扩大先停相关修复并交Astra，不重跑RED或重置预算。
