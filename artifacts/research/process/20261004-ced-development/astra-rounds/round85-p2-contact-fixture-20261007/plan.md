# Astra Round85 — P2 单测试 contact 父目录恢复

状态：仅计划。本轮真实创建R85计划；此前恢复失败没有生成计划。

R84唯一GREEN结果94个唯一节点：93pass/1fail、0error/skip。新测试在contact/cloud.py写入前因contact父目录不存在抛FileNotFoundError；此前LIFT位移/0参考速度/正TCP/digest拒绝通过，contact伪fixedflag拒绝未到达。整个失败节点不能记为通过。

## 唯一改动

在tests/test_native_references.py的test_fixed_goal_zero_reference_velocity_is_not_zero_body_velocity中，原contact sample调用前插入：

```python
(tmp_path / "contact").mkdir()
contact_inputs = sample(tmp_path / "contact", "GRASP")
```

只新增第一行，第二行保持原样。不改全局sample/role_binding，不加exist_ok或parents，不改生产源码、旧断言或调用顺序。

## 执行与预算

1. S1 ROOT核对本计划、R84原94节点结果与五源freeze；GPT-6.1-sol只取得tests/test_native_references.py单写者。保存source-before，生产3源和其他测试/fixture完全保护。原P2 GREEN已消费，不把旧额度重置。
2. S2 仅在命名测试中，原contact_inputs = sample(tmp_path / "contact", "GRASP")之前紧邻新增一行 (tmp_path / "contact").mkdir()。不加parents/exist_ok，不挪动sample，不改全局sample或role_binding；只建立这个测试新子目录。原所有assert/raises/body-travel/TCP/digest/伪fixedflag检查和顺序保持。
3. S3 生成精确diff与坐标证明：完整AST(type_comments=True)仅删除这个函数此锚点前唯一Expr/Path.mkdir调用后与before相等；其余所有定义、参数化、fixture、注释、函数签名相同。不能删其他AST节点/旧assert或修改source guard，五源中只有此测试SHA变化。
4. S4 不运行formatter或产品mypy；一行是常规Ruff格式，运行限定测试文件Ruff check和format --check各一次。若出现计划外格式/静态失败，保存原件并下一Astra，禁止静默formatter或重复检查。产品完全相同，沿用R84三源mypy与生产静态通过。
5. S5 两静态实际通过后，执行唯一targeted_GREEN一次，只运行整个先前失败节点。独占新的round85 basetemp/JUnit/命令收据；必须1pass/0fail/error/skip，实际执行到原contact伪fixedflag拒绝。若仍失败，保存完整stdout/JUnit及原件后停，不扩成94或重试。
6. S6 汇总R84原93通过节点（原SHA）＋R85原失败节点新1通过，并证明其余测试/生产输入保持；这是跨轮证据闭合，绝不写“94例本轮重跑通过”。保存新CPU原件完整分母及旧799原件清单的只读引用；不覆盖原P2 RED、类型失败或R84 GREEN失败。作者报告后交不同作者独审，未验P2不提交发布；执行者Git/actual为0。

新增授权仅：测试文件Ruff check一次、format --check一次、原失败完整节点一次。formatter、mypy、RED、其他93例和完整94新次数均0。精确命令/env见JSON。

## 验收与复用

Three production files and unchanged other test/fixture inputs match frozen bytes; removing only local mkdir recovers full original test module AST. The 93 prior passing nodes have no modified body/shared fixture and do not depend on this one test-owned temporary subdirectory.

最终描述应为“原93例通过证据仍适用＋修复后受影响1例通过”，不是“本轮94/94”。原799文件/34846709字节CPU分母和所有历史失败保持。GRASP/futureD支持限制不变，actual/formal未验收，未验P2不发布。

## 输入SHA256

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` | 2458 |
| `src/cloud_edge_robot_arm/vision/native_references.py` | `bb15bea435b045fa931e3ae43ba92c8b843950d22fc1589325488e1b1a33a149` | 14831 |
| `src/cloud_edge_robot_arm/vision/native_calibration.py` | `a707ac74d5e668b57a5a7883154a2e9b83d3d1695f1fbe42f7681f5c03d35fff` | 28630 |
| `src/cloud_edge_robot_arm/research/native_geometry_calibration.py` | `84d287c423c8de6eaafa09987445a59d74f81307cccbd5cb6a0c023b65018843` | 30883 |
| `tests/test_native_references.py` | `0fd4faf5c296bcf23b12f0b89ba6e50840b04a1e4eccac5306c0077b6c928003` | 14707 |
| `tests/test_native_calibration_source.py` | `5c9afd4cba51a35eb454f259c74245a535e87402d6bf6952513bfa42ba723ae6` | 34656 |
| `tests/test_ced_runtime_binding.py` | `ebdff387edaae902726042239c87cc4ae5533b9493e61d26a4d2b9e2f44fe48a` | 12212 |
| `tests/test_phase6_2_replan_resume.py` | `2a0a384a8bc63d9f40f2db80acd04097e89ce682f660e719ab5665cff814e7c1` | 22957 |
| `tests/test_visual_evidence_contract.py` | `770b9fcef2836615a1d61f939ccef90f34bb60c5dfaa050186845f507738564a` | 9994 |
| `src/cloud_edge_robot_arm/vision/runtime_binding.py` | `d6e6c7a42cc57a2ef0aa2e205c6499fe84244be53c8ca91241137265d2fc69dc` | 6092 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/plan.md` | `3c77f0e86249b6e1df0d684af7408dcfa093b97a8429d5ca0ed97c5d27e15dfe` | 16660 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/plan.json` | `4dbcf4d63ee31c3a2fdba39861d6809bc8008f5ae2d749ad4967c6a2d9d196e0` | 27448 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/root-authorization.json` | `ad4b4b9ed91d02dca9e4ac542011ffc2152029474bcfe8ceda52d59725fea956` | 625 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/GREEN.stdout.txt` | `756fe3058757847bfa954b852320bc700b6ba07872fc49e8e488760fa4422a4a` | 3327 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/GREEN.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/GREEN.command-start.json` | `e9d346f50b42b47bc37531e535ecb65e8810fe378d8765b10f757fa641960073` | 691 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/GREEN.command-result.json` | `28d69268398822d3174206d27d9df9ce71f2bc88d2d9c28075a1605aa55e7bd4` | 795 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/GREEN.junit.xml` | `365fbd7e4e1a1e06df2620f6f17fc69215335d1fe8b374da9b87bb99ea59ce10` | 17593 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/step-report.md` | `78c6b57f06a84a7486d53499d83b8ff960eae7c675d29b1e08df277198bd3922` | 2356 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/step-report.json` | `06df5220fb8fcb44e2f68410b19a094640360fb06e4b6df9b16841fc5f1c3011` | 3180 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/failure-receipt.json` | `6ef520411e55e181ef6ebcfb26ff7aeb3bd14623c7da6dbdb024834ae12d98c8` | 2235 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/source-freeze.json` | `54d471bfd68ca4bc831717030e443fd9ce62b72915d62bae0b2990faf4752442` | 1033 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/run-ledger.json` | `f4eb80799c827b083480403312ee30cb66e7ae7dca20726d3a8ac18277d98de3` | 1951 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/test-outcomes.json` | `5c3143643a9023dbbb080e59a1d6e3f93e78bc969399069d26f6fe4d6f0b21b1` | 23146 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/cpu-originals-manifest.json` | `196b90dad5d2e8f0e5ce25836dbdeae12066dce75c89571bddc2c56e6beb6734` | 487704 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/restricted-ast-proof.json` | `704314d05f320c49ec2795f995ed6fd5fbc623e1bb49d6145745f718227fcca8` | 2810 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/input-check-after.json` | `25cd215f9b93a544728926c9a3a9129734454ea7b89b852c6f48fea382f7dca0` | 20568 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/report-evidence-pins.json` | `fed4d0d693245d76f9c9083ae7f6017c1961e166f6c25b6727e37f4868257e16` | 11476 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/mypy.stdout.txt` | `0b0d2fed57266f8ba89bafa3096623807028cbe90aaf29e5c6028c29608ba3ab` | 129 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/mypy.command-result.json` | `bceedf1836422ead8efe485032f7d5107745c5e06048f29397056c3d58e348a5` | 747 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/ruff_check.command-result.json` | `0049dbd881353a8fcd6a56513390b1e6ffa484260dc283ff67311c705428739d` | 545 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round84-p2-native-types-20261007/implementation/ruff_format_check.command-result.json` | `ba969c9307891822e0aa7b280aec8d3587cd656eee039aa548399761d57e7800` | 562 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.stdout.txt` | `068bbc43f41f8591081f655ebe236b15d6c4102b5ae59254b2f22a5b9aa2985e` | 3899 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.command-result.json` | `c25ae1b45f4af3c68afc3d0d58e1393189c2a20a23a971085e92e49c25c421c3` | 873 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.junit.xml` | `8e687957eabc70ca3ba52535db004777737053fd79c03c1ae98695be0c58a658` | 5270 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.stdout.txt` | `9d6ff3e66da38fde127b945036fa19ef0844cdd8aefb8d7f38fd8f90a7e82203` | 2526 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.command-result.json` | `145c107740e9ac57e4ec4b68eb9cd72bb32139057b58ef0f323596ec62307fb2` | 740 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/support-decision.json` | `4e62481d31d0549dcf2fe856f113dcce3506133a39aae63c4b588b476d382209` | 755 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/contract.md` | `04727670fcb514fa5e5e83db767c0352226c72f39e38bf30b5f0a4b8202551d9` | 5222 |
