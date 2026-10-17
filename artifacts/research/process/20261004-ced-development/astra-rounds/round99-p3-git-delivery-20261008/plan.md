# R99 P3 scoped Git delivery plan

实际Astra规划，仅具体化已验收P3软件交付；没有新增产品失败、产品修改、测试或actual运行。ROOT不同作者最终审查为 `PASS_SCOPED_P3_SOFTWARE`，90 unique GREEN、11新增case和最终五命令均通过。旧R92/R94失败保留，R94四阶段/四负控成功与R97精确整文件替换证明复用，不重跑。

## 真实基线与前置依赖

既有worktree `/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall`，branch `codex/research-20261007-p1-delivery`。本轮真实只读Git确认：HEAD及tracking均 `a77568043bb5589471e3f15a07d3203998acb8b4`，worktree含untracked检查为空；parent是03f33416。4d40是祖先，用户1007 `34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e`不是祖先（is-ancestor的exit1是预期查询结果）。本轮未查询live remote；ROOT报告三端一致，实施前再真实核对，不能以tracking代替live。

五候选当前源与ROOT最终pins完全一致；交付树五文件逐字等于R92 source-before。因此只应用已审P3完整增量，不纳入用户1007历史：

- `configs/research/ced_roles.yaml`：2041B，d3fddcff7a06306d3b56a0b17478c8f398f702a614a313d729199a9b9d1539b3。
- `src/cloud_edge_robot_arm/vision/role_models.py`：9696B，cdeef8872e38aab742a2018ff1826575cedb3a35aca7969da369a8854890959e。
- `src/cloud_edge_robot_arm/vision/planner.py`：28189B，33dfe0aa25b6a316a346e7247724fa20a9db6082ef5317c036bbc9f7ddaea317。
- `tests/test_rgbd_role_models.py`：52099B，07a3ca1d8f0d9340cf7828817d474e08e07fd1196ba5cf7a90be91fc83619a9c。
- `tests/test_ced_runtime_binding.py`：14429B，40b665857bec2c07c74e2f789d2ad28319e561ef856870b13aa190ed85be8d4b。

针对所选positive node、roles动态工厂、probe模块和模型/消息/存储入口，有限核对26个明确已有文件：probe_rgbd_roles/probe_rgbd_model、model_resolver/messages/observations/top_grasp/defaults、model-control service/catalog/downloads/provider/repository、contracts、planning等，均已tracked且与主树当前同字节。历史verification.json也已在候选中，无需为未选旧历史测试复制资料。根及tests下无conftest，不是缺失必需fixture。**新增依赖源0**。详细路径/SHA/bytes与真实Git输出在本轮本地 `readonly-base-dependencies.json`；这是有限导入面核对，不宣称扫描了全仓依赖。最后一例候选执行验证实际checkout闭包；若意外缺依赖，停止并以准确路径交新Astra，不临时复制整树。

## 精确交付范围：64条已固定文件 + 3条计划自文件

`delivery-paths.json`逐条固定path/target、SHA256、bytes、mode、A/M、semantic_role与理由。64条共332091B：5当前源 + 58份已审历史计划/原始失败/成功收据/XML/diff/最终审查小证据 + 本轮明确 `delivery-boundary.md`。除此只加入同目录 **plan.md、plan.json、delivery-paths.json** 三条自文件，共67个选定路径；ROOT在计划完成后用本次handoff实际hash固定这三条，避免递归自hash。不得按目录、glob、报告中的引用自动扩展。路径选择数不等于新增文件数/最终变更数；若候选已有完全相同blob按实际记录复用。

R92选择原RED命令/输出/XML、原proof失败tool输出/exit、Ruff失败输出/result、停止报告及formatter结果；R94选择其计划/ROOT审查、成功scopeproof/执行起止、Ruff失败、停止报告和局部diff；R97选择计划/一次真实diff诊断、最终五命令各start/result/stdout/stderr、90GREEN XML、local proof、最终完整P3 diff/freeze/report/ledger；ROOT最终review两文件。不是复制三个round目录。

排除完整CPU/原tmp/SQLite/凭据、406份CPU全包及详细原件manifest、source-before/after树、helper proof/runner、模型权重/SDK、实验raw、活动P4/R98和全局总表。本轮本地dependency observation与postpush等未来收据不发布。历史计划/报告可能引用被明确排除的本地原件；`delivery-boundary.md`明确远端不是完整取证/复现包。禁止假称只上传索引就上传了全部原件。

## Task 1：ROOT隔离候选、验证和正常推送

1. ROOT重验本计划/有限pins、最终5源、全部64manifest条目以及3个完成后的自文件；独占新建主树 `HAND/delivery-p3-round99` 保存本地收据。真实确认当前HEAD/upstream/live同a775、worktree clean、既有origin/branch/受众未变，4d40祖先与1007非祖先。仅要求交付候选单写者，不要求P4/R98活动主树quiet，也不pin它们的未来输出。
2. 审阅每条待发布内容及来源/敏感性，逐文件原字节copy，核mode/byte/SHA；五源码旧blob须仍R92before，最终须最终ROOT pins。用户1007、主tree、raw/DB/脏嵌套不动。敏感材料不发布，保留原件后停止相关范围，不strip再谎称原样。
3. 执行下面一次四文件compile，再一次唯一normalized positive CPU用例；每条保存真实start/argv/env/cwd/stdout/stderr/exit。compile或case失败立即停，禁止重跑90/旧RED/formatter/Ruff/mypy，不自行添加依赖或重试。
4. 使用明确NUL路径清单stage；staged全集须与67选定路径中实际变化的集合一致，逐blob哈希/字节/mode与候选manifest一致，无额外路径、删除、symlink/gitlink或祖先。父级仍a775。
5. 沿R77/R81/R96做**完整** `git diff --cached --check`，如实保存exit与原输出。每个原样空白诊断必须逐行/EOF范围绑定VERBATIM文件、原来源SHA/bytes、staged blob与行字节SHA；例外恰好覆盖真实诊断、unclassified=0。历史证据保持字节，不strip、不重序列化、不改.gitattributes/config/ignore。全量若exit2不能写exit0；非空白/配置/IO失败不豁免。
6. 对五当前源与本轮4个新文档/metadata的**明确非空严格子集**单独cachedcheck，必须exit0；必要JSON/UTF-8解析只检查新元数据结构。历史计划在本次作为冻结审计原件，非当前运行工具；本清单不交付可执行helper。若有兼具运行角色者须重新分类为CURRENT_EXECUTABLE，不能借原件豁免代码。
7. ROOT最终审阅完整范围/内容/byte总量、5source、候选1case、whole真实exit/strict0/逐行例外及staged对象，创建一个普通commit，parent精确a775；不amend、merge或cherry-pick用户1007。commit tree相对父变更仍精确对应清单。
8. 沿既有授权与受众一次non-force push：`git push origin HEAD:refs/heads/codex/research-20261007-p1-delivery`。推后分别真实读取HEAD、@{u}、live ls-remote完整SHA，三者一致且候选clean才DELIVERED，否则PUSH_UNVERIFIED留证，不自动重试。所有新候选/空白/commit/postpush收据仅本地，不能为自引用报告再改/再推已审commit。

## 候选验证预算（不能借此重新资格认证）

cwd为delivery worktree；既有解释器 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`，环境 `PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1`。候选路径优先，不在primary执行：

一次标准库compile，读以下4路径的原字节并调用`compile(data, path, 'exec', dont_inherit=True)`，不import产品、不写pyc：

```python
from pathlib import Path
for name in ('src/cloud_edge_robot_arm/vision/role_models.py', 'src/cloud_edge_robot_arm/vision/planner.py', 'tests/test_rgbd_role_models.py', 'tests/test_ced_runtime_binding.py'):
    compile(Path(name).read_bytes(), name, 'exec', dont_inherit=True)
print('four candidate Python files compiled; no product imports or pyc writes')
```

仅一次CPU正向serialized-wire例：

```bash
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p3-r99-candidate tests/test_rgbd_role_models.py::test_ced_max_reuses_successful_normalized_transport --junitxml=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-p3-round99/candidate-positive.junit.xml
```

期待1uniquePASS、0fail/error/skip；真实双图320×240/normalized_1000/Max think false必须经过实际工厂与urllib Request.data，唯一外部HTTP边界被原CPUfixture替换。没有真实网络/模型/相机/MuJoCo；不读取真实secret store。候选临时SQLite与模拟wire原件全本地，不入67paths。原90PASS仍同一个原90分母，这一例单列导出闭包检查。

预算compile1、candidate1、额外测试/静态重跑0、actual0、commit1、nonforcepush1、自动retry0。Git推送与live查询是后续Git网络，不能混记成模型实际请求。本轮规划仅只读Git/文件及本目录写入，未compile/pytest/stage/commit/push。

## 验收边界

软件与所列小证据已交付≠当前Max actual source资格；旧35调用不继承。P3真实cold+3warm仍待P8最终适用sourcefreeze与ROOT单独激活，formal未验。P4/R98新实际疑问独立处理，本计划不改变其停点、源或输出。用户完整历史/原件保留，不能通过推用户1007祖先扩大8GB载荷。新的根因/检查失败/范围漂移保留并交下一Astra，不悄悄扩包。
