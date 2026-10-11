# R121：ROOT 元数据路径读取恢复

实际 Astra 规划，2026-10-11。仅恢复ROOT有限交付资料读取；不影响正在独立实施R113 stage A的作者。

ROOT工具023283在仓库根执行下列原命令exit2：

```text
rg -n 'delivery|candidate|manifest|git' artifacts/research/process/20261004-ced-development/astra-rounds/round118-status-report-and-finite-git-delivery-20261011/plan.md artifacts/research/process/20261004-ced-development/astra-rounds/round112-p5-frozen-review-and-git-delivery-20261008/plan.md
```

原combined output：

```text
rg: artifacts/research/process/20261004-ced-development/astra-rounds/round118-status-report-and-finite-git-delivery-20261011/plan.md: No such file or directory (os error 2)
rg: artifacts/research/process/20261004-ced-development/astra-rounds/round112-p5-frozen-review-and-git-delivery-20261008/plan.md: No such file or directory (os error 2)
```

没有独立stdout/stderr原流，不补造。根因是从旧摘要猜测目录名，不是产品失败。规划中第一次限定glob检索1bca90无匹配exit1已记录；随后使用`rg --files`限定元数据目录并按文件名过滤，ae17c0退出0，实际位置为：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round118-status-delivery-concurrent-head-20261011/plan.md`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round112-p5-git-delivery-20261008/plan.md`

对这两份plan.md的原关键词有限只读9725fc退出0。仅定位/读取元数据，不检查正在写的产品或测试文件。

## 恢复步骤

1. ROOT preserves original exact command/combined failure from plan.json or writes original-failure.json with explicit tool-transcript provenance. Do not fabricate separated streams or remove metadata search failures.

2. Use the observed resolved_paths and pinned hashes for finite R118/R112 read. The successful planner path inventory/read may be reused; ROOT may independently verify these two hashes, but no repeated broad scans are necessary. If future paths are unknown, rg --files only under the existing astra-rounds metadata directory and filter exact round/path filenames before reading.

3. Read only these historical Git-delivery examples as documentation. Do not execute their Git/candidate-test/compile commands or inherit their past budgets/HEADs into current P6. Actual stageA delivery requires its own frozen inputs and explicit later bounded delivery plan.

4. ROOT may record recovery-check.json and step-report.md/json and append a truthful metadata note. Leave R113/R119/R120 plans and author activation unchanged; do not pause /root/p6_stage_a_sol, change its six-path scope or eight-command ledger.

## 验证和边界

ROOT按下表复核两份文档hash后继续有限阅读即可，可复用已成功定位结果。若新增路径仍不明，仅以现有astra-rounds元数据文件名清单查证，不扩大为源码扫描。所有历史候选测试、compile、Git命令仅作阅读材料，不能执行或迁移其预算/父提交。

不暂停作者，不改R113八预算或R119/R120激活，不宣称当前作者预算仍为0（作者在独立运行，本轮没有读取其动态状态）。产品import/compile/collect/test/static、Git、actual、模型调用全部不在本恢复权限内。只证明读取路径恢复，不代表P6通过或已交付。原错误和本轮搜索诊断全部保留。

| 输入 | SHA256 | 字节 |
|---|---|---:|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round118-status-delivery-concurrent-head-20261011/plan.md` | `c155cf637d721c98056d96b02d9a89d8081566a024d163a5791a9bed0694f499` | 6339 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round112-p5-git-delivery-20261008/plan.md` | `d2afea239371ef40e51cffe06bb0e9ba2304d300d39f382314fddb54492f093b` | 6082 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round120-p6-author-interpreter-recovery-20261011/plan.md` | `0be2f7a8d170ef2ca425b5a96fa15c0aaa533aba1921c9ea7f944fe935d45843` | 3600 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round119-p6-stage-a-resumption-20261011/plan.md` | `85870929c56a43e66b7d8d47c93d05416848e95a89d77e4d0cd652d2b3821bd0` | 4950 |
