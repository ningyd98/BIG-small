# R96 P4/R93 Scoped Git Delivery Plan

规划：实际Astra；仅具体化已验证软件的Git边界，不人为新增产品问题。规划未执行任何Git命令、测试、产品或actual。

ROOT最终不同作者PASS：三源最终freeze吻合，62小证据已核，31GREEN与静态/proof通过。完整CPU2117文件520,684,793B仍本地；旧P4首败68文件25,001,424B含DB保留。本轮只交软件和明确小证据，不把manifest冒充完整远端复现包。

## 基线和有限观察

沿现有 `/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall`，branch `codex/research-20261007-p1-delivery`。仅标准库读取refs/loose commit objects并核SHA1，local与tracking为`03f33416d0cb9d35f432c053f08f8ef98afd5cd2`；线性父链03f33416→851b80c8→98b82821→3daddcc9→4d40a650，用户1007的parent是4d40，未进入交付链。实时remote和clean来自ROOT报告，规划未查询；实施前须实际Git复核，不能把缓存ref冒充live。

三条delivery现有文件逐字节等于R93 source-before，主树三条现源精确匹配独审finalfreeze：

- `src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py`：11798B，SHA256 `36c18a83355013bb06701e7b535f65e897a949e3fd965bbf4f0236e42e79fcd0`。
- `src/cloud_edge_robot_arm/research/operational_prefix_v1.py`：65004B，SHA256 `fbe8ee8f11911d3caaad32f91aacb30c927ccdf2018bc5913819a05afdc6348f`。
- `tests/test_operational_capture_v1.py`：33407B，SHA256 `fb033178733a39c75d7bbc28b7c338465d0e79a24a0103c92c02db250cc9e0c9`。

R93新增import仅stdlib re、已在三源内schema函数及既已交付的backend类；没有新项目模块。保留R86已交付OC1前置，不重建活动主树225/288全闭包，不导入P3正在R94修改的文件。

## 精确allowlist与原样证据

`delivery-paths.json`逐条给出全部既有候选的真实path/target、bytes/SHA256、mode、A/M、semantic_role和理由，禁止目录递归copy/add。再加**仅三个本计划自文件**：本目录plan.md、plan.json、delivery-paths.json，ROOT用本轮最终交付hash和实际字节在copy前固定三项，避免文件递归哈希自身。最终candidate manifest完整冻结后才能stage；不允许其他未来文件自动加入。

分类沿用R77/R81/R83/R86：三当前源CURRENT_EXECUTABLE；新计划/元数据NEW_PROSE_OR_METADATA；原stdout/stderr/command收据/XML/diff/失败保全index逐条VERBATIM_EVIDENCE。保持字节，禁止strip/format原件、改whitespace/.gitattributes/.gitignore。完整cachedcheck真实非零若仅原样空白，按逐条stagedblob/来源SHA、行或EOF字节hash登记；strict可执行/新文档非空子集必须exit0，unclassified0。不把底层非零写成exit0，配置/IO/其他失败不是例外。

排除完整R93CPU树及详细CPUmanifest、各阶段完整source快照和保全/proof工具；排除旧P4 actual/**全部raw/DB及其他历史；排除P3活动test/proof/planner/role/config和全局状态表。这里只选旧P4 actual目录外的原始执行收据/失败输出与保全manifest。远端不承诺完整历史取证可自足重跑，具体缺件边界随delivery-boundary.md发布。

## Task 1：ROOT隔离交付

1. ROOT复核有限pins及每个allowlist文件，exclusive新建主树HAND/delivery-p4-r93-round96用于本地收据；实际检查worktree clean、branch、HEAD/upstream/live均03f33416，base祖先及1007非祖先，原origin/受众未变。仅候选树单写者，P3独立工作不要求全仓quiet。漂移不得静默换base。
2. 审阅全部候选内容、范围/敏感信息及受众，再按原字节逐文件复制，核source/candidate SHA和mode；原主树、用户1007、raw/DB及嵌套脏树不动。敏感/未授权内容保留本地原件并停止相关发布，不能strip原件蒙混。
3. 候选验证只一次三文件compile与一次直接受影响cached空实例正链（命令见下）；隔离候选从03f33416出发而非P3活动主树，此一例验证实际已有依赖/真实CPU出版链可运行。主树31GREEN/静态已同字节独审，不再重跑31或R03/Ruff/mypy。任何新缺依赖/失败停Astra，不暗加源。
4. 显式NUL文件路径stage，实际staged集合及逐blob bytes/hash/mode等于allowlist，无额外父提交、删除、symlink/gitlink。完整cachedcheck、逐项原件例外与strict0按R81。新检查/例外/候选CPU/候选审查和postpush收据全部本地，避免自引用索引变化。
5. ROOT最终核对candidate代码/一例/范围/内容/byte总量/祖先，做一个普通commit，parent须精确03f33416；不amend/merge/cherry-pick1007。commit tree路径/blob仍完全对应清单。
6. 同既有origin/受众/branch按用户既有授权一次明确非forcepush，不另造审批：

```bash
git push origin HEAD:refs/heads/codex/research-20261007-p1-delivery
```

7. 推送后分别读取delivery HEAD、@{u}与live ls-remote完整SHA，三者等于新commit才DELIVERED；否则PUSH_UNVERIFIED保留失败不重试。postpushreceipt仅本地，不回写已审commit、不另推自引用文档。原1007及主branch不变。

## 候选唯一验证预算

cwd为delivery worktree，解释器使用主树既有`.venv/bin/python`，`PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1`保证candidate源码优先。compile用标准库compile读取三候选文件，不import产品、不写pyc：

```python
from pathlib import Path
for name in ("src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py", "src/cloud_edge_robot_arm/research/operational_prefix_v1.py", "tests/test_operational_capture_v1.py"):
    compile(Path(name).read_bytes(), name, "exec", dont_inherit=True)
print("three candidate files compiled; no product imports or pyc writes")
```

随后仅一次：

```bash
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p4-r96-candidate tests/test_operational_capture_v1.py::test_cached_capture_preserves_empty_instance_sidecars_cpu --junitxml=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-p4-r93-round96/candidate-positive.junit.xml
```

预期1uniquePASS/0fail/error/skip。原stdout/stderr/start/result/JUnit及新CPU原件完整保留本地，不算重跑31，不冒称actual。compile1、candidate单例1、额外产品测试/RED/静态重跑0、actual0。commit1、nonforcepush1、自动retry0。Git远端核对/推送是后续Git网络，不能记作“所有网络0”；规划本身网络0。

## 运行与验收边界

Git只证明所列软件/小证据交付。完整520MB CPU与25MB首败raw/DB仍localonly；manifest/摘要不等于完整远端复现包。R93新actual仍待P3/P4源最终静止及ROOT单独新sourcefreeze/独占attempt授权，不因Git完成自动启动。formal false、native unavailable、UTC-SI unverified、futureH-D/geometry unknown、calibration_groups0、OC3未验。任何额外范围/新根因/计划外检查失败保留并交下一Astra。

精确候选清单：见delivery-paths.json；有限前置及SHA见plan.json input_pins。候选新增运行/空白/commit/push/三SHA收据全本地，不纳入本次已固定载荷。
