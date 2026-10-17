# Astra Round84 — P2 结构化字典类型修正

状态：仅计划。P2首次三源mypy exit1：native_references:152 policy object→Mapping一项，:292 **values逐字段8项，共9项。原函数AST与source-before相同，但没有baseline mypy；不得宣称历史已失败。

```text
src/cloud_edge_robot_arm/vision/native_references.py:152: error: Argument 4 to "RoleRuntimeBinding" has incompatible type "object"; expected "Mapping[str, object]"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "Literal['native.action_reference.v1']"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "Literal['OBJECT_CONTACT', 'FIXED_WORLD_TCP_GOAL']"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "str"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "int"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "float"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "tuple[float, float, float] | None"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "tuple[float, float, float, float] | None"  [arg-type]
src/cloud_edge_robot_arm/vision/native_references.py:292: error: Argument 2 to "NativeActionReference" has incompatible type "**dict[str, float | int | str | tuple[float, float, float] | tuple[float, float, float, float] | None]"; expected "bool"  [arg-type]
pyproject.toml: note: unused section(s): module = ['ament_index_python.*', 'rclpy.*']
Found 9 errors in 1 file (checked 3 source files)
```

## 最小修复

只改native_references.py。原evidence内edge_policy已有闭合Mapping生产链，但返回dict[str,object]抹去了形状；18-key values无注解丢失逐字段类型。保留全部运行构造、kwargs、digest、异常、旧UTC和source守卫。

允许精确 `cast(Mapping[str, object], binding.evidence()["edge_policy"])`：exact-class检查后，__post_init__既有dict→JSON→freeze及policy hash验证，evidence._plain产生分离dict，原重新构造再次校验。cast为identity，不替代运行验证、不扩展到调用方输入。

TYPE_CHECKING内声明下列TypedDict，原dict(...)仅加局部变量类型；18字段等于原dataclass去掉单独计算的reference_digest，kwargs次序和表达式不变。

```python
class _NativeActionReferenceValues(TypedDict):
    semantics_version: Literal['native.action_reference.v1']
    kind: Literal['OBJECT_CONTACT', 'FIXED_WORLD_TCP_GOAL']
    reference_id: str
    execution_payload_digest: str
    contract_digest: str
    grounding_digest: str
    online_digest: str
    source_digest: str
    observation_id: str
    observation_sha256: str
    plan_version: int
    command_seq: int
    context_hash: str
    role_bundle_hash: str
    full_horizon_s: float
    endpoint_xyz: tuple[float, float, float] | None
    orientation_wxyz: tuple[float, float, float, float] | None
    fixed_goal_coordinate_invariant: bool
```

## 实施与额度

1. S1 ROOT核对本计划及有限输入，原GPT-6.1-sol只取得native_references.py单写者。保存source-before与P2原9项mypy失败，另四owned源码/测试完全保护。旧定义AST相同事实只解释范围，未运行baseline mypy，绝不把本次失败回填为历史失败。
2. S2 在既有TYPE_CHECKING块内导入TypedDict并定义_NativeActionReferenceValues（默认total=True），18字段精确等于NativeActionReference除reference_digest之外的同名类型。只把resolve中的values = dict(...)改为values: _NativeActionReferenceValues = dict(...)；所有keyword名称/次序/表达式、_digest(values)、构造器reference_digest关键字与**values全部保持。不要改成另一种dict构造、显式逐字段构造器调用、cast整个values或dataclass放宽字段。
3. S3 仅在_current_sources的RoleRuntimeBinding第4参数，将原binding.evidence()["edge_policy"]包装cast(Mapping[str, object], 原表达式)。cast依据见contract：精确类已有__post_init__ dict→JSON→_freeze，evidence._plain返回同形字典；原重构RoleRuntimeBinding及所有source/hash/policy guard仍执行。不得把此准许推广到公开Mapping、任意JSON或其他输入，不增加/移动运行检查或改异常顺序。
4. S4 只对此源执行正常formatter一次；保存逐hunk/完整before-after。受限AST仅允许移除TYPE_CHECKING中新TypedDict导入/类、将values AnnAssign还原原Assign、解包已登记arg4精确cast后，整模块AST(type_comments=True)与P2冻结相等；所有旧注释/函数签名/kwargs表达式序列相同。TypedDict字段自动与原dataclass及values18keys逐项对照。cast identity证据与调用来源单列；P2原additive proof不改写为本轮新证明。
5. S5 按verification新一次Ruff check、format-check（仅改动源）、三原目标mypy；遇任何新错误/形状假设不成立立即停止并下一实际Astra，不跑临时reveal_type/baseline微探针或第二种修法。
6. S6 所有静态实际exit0后，消费P2尚未用的唯一GREEN，两原测试文件/所有节点不改、原/tmp/bigsmall-t12-p2-green保持唯一未用，JUnit/命令收据写本轮新目录。预期原收集94例，全pass/0error/skip；保留实际唯一节点清单。GREEN失败不重跑、不改旧断言。
7. S7 保存source-after、bounded proof、静态与GREEN原始stdout/stderr/argv/env/exit/wall/JUnit、input前后核对与预算收据，步骤报告汇回P2。GRASP/futureD已知NOT_SUPPORTED、native UNKNOWN和依赖批量暂停保持，不把其当本轮新错误或借类型修正扩语义。最高作者软件验证，仍需不同作者独审；本轮actual/Git为0。

新formatter/ruff/format-check各一次仅变动源；三源mypy一次。保留P2未用GREEN一次，仍为两个原测试文件全量节点（原RED收集6+88=94），不重跑RED或baseline。GREEN必须在最终静态实际通过后运行。具体argv/env见JSON。

## 边界

类型修正不建立校准值、完整future D、GRASP支持或native资格；上述已知NOT_SUPPORTED不是本轮故障。actual/Git/模型/网络均0，作者软件通过后仍需独审。OC2最终审查和RW1独立，不要求全仓quiet。

## 有限输入SHA256

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` | 2458 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/t12-convergence-repair-20261006/plan.md` | `d5c3d6b1ffa6f51f3a2785af5f5ab9fedf506f81080a3bea311644fff7c70219` | 71264 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p2-executor-brief.md` | `166bfe4f1cac8a61ddb9af64f91f5ac28a79f391cfd8393284d82f51665ceaeb` | 4924 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p2-prepared-inputs.json` | `a2fa69cbf70777483934516eceb40d6c839b0e99cec20a3de0b75dc14cdc6d6b` | 1757 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p2-dispatch.json` | `d09ae061769f56badd99c40c5633de2b7351e455a5de9883ad5054be4b11ac4e` | 681 |
| `src/cloud_edge_robot_arm/vision/runtime_binding.py` | `d6e6c7a42cc57a2ef0aa2e205c6499fe84244be53c8ca91241137265d2fc69dc` | 6092 |
| `src/cloud_edge_robot_arm/vision/native_references.py` | `08e36325fd6e29e4cde9ac0f9e583c1bd711b1b15734e9387a15ff3e184297b0` | 14014 |
| `src/cloud_edge_robot_arm/vision/native_calibration.py` | `a707ac74d5e668b57a5a7883154a2e9b83d3d1695f1fbe42f7681f5c03d35fff` | 28630 |
| `src/cloud_edge_robot_arm/research/native_geometry_calibration.py` | `84d287c423c8de6eaafa09987445a59d74f81307cccbd5cb6a0c023b65018843` | 30883 |
| `tests/test_native_references.py` | `0fd4faf5c296bcf23b12f0b89ba6e50840b04a1e4eccac5306c0077b6c928003` | 14707 |
| `tests/test_native_calibration_source.py` | `5c9afd4cba51a35eb454f259c74245a535e87402d6bf6952513bfa42ba723ae6` | 34656 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-before/src/cloud_edge_robot_arm/vision/native_references.py` | `3bba0206ec529c84fdf7e4fd2592a538a4036bcba626772986cf25f5a2d99ff9` | 11089 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-before/src/cloud_edge_robot_arm/vision/native_calibration.py` | `0888c38f4caf4dd65c27c29315d8253a1aa8fa1a6fece0bf2b18bcc9bcedb2a6` | 26273 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-before/src/cloud_edge_robot_arm/research/native_geometry_calibration.py` | `7d555c23c5d2ffcdc1a9ba5aacd4601c71e1f6691b69da56893fad6b45dc822d` | 29791 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-before/tests/test_native_references.py` | `1180e3105884ead4771d45d93a40673679618ea3ac2a82487d60acaae9121409` | 12972 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-before/tests/test_native_calibration_source.py` | `0363bfd373810b1377e07c09aa7284bbc779bd86c19219031c3644b503a0f473` | 31135 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-after/src/cloud_edge_robot_arm/vision/native_references.py` | `08e36325fd6e29e4cde9ac0f9e583c1bd711b1b15734e9387a15ff3e184297b0` | 14014 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-after/src/cloud_edge_robot_arm/vision/native_calibration.py` | `a707ac74d5e668b57a5a7883154a2e9b83d3d1695f1fbe42f7681f5c03d35fff` | 28630 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-after/src/cloud_edge_robot_arm/research/native_geometry_calibration.py` | `84d287c423c8de6eaafa09987445a59d74f81307cccbd5cb6a0c023b65018843` | 30883 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-after/tests/test_native_references.py` | `0fd4faf5c296bcf23b12f0b89ba6e50840b04a1e4eccac5306c0077b6c928003` | 14707 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-after/tests/test_native_calibration_source.py` | `5c9afd4cba51a35eb454f259c74245a535e87402d6bf6952513bfa42ba723ae6` | 34656 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/contract.md` | `04727670fcb514fa5e5e83db767c0352226c72f39e38bf30b5f0a4b8202551d9` | 5222 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/verification.json` | `6fb26cb446f59c7a6232f2817e98b5eda495ba4c07212740babcab48e7ee0557` | 2779 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/dispatch-pins.json` | `7bb3cb160ff83421fc379ece7075665bb1a09fd4c9735c40d57a91b4fa529a32` | 515 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/step-report.md` | `1cd135c9cf97b884e851d86cdedb23d2feb43971061470c8946d4ad56fdd9ca9` | 2633 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/step-report.json` | `b69017992d4279d6cd7f084deb998a695e090f9ec7b13ecceec5399b0007fbca` | 10856 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/failure-receipt.json` | `b69017992d4279d6cd7f084deb998a695e090f9ec7b13ecceec5399b0007fbca` | 10856 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/run-ledger.json` | `1a5202a799bc460f235063a93edc13d12fe70367e7477ccd846ccca898c97558` | 573 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/unrun-verifications.json` | `7ac83b00c9140317c473a2290dd1fa674d0f83563d0dbc33e89ea00413fc2724` | 109 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/source-freeze.json` | `0275fa5dd41bd521202a906e9e2b39059ed31d36a1d3dd451fed3566b8d677aa` | 812 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/additive-scope-proof.json` | `b0668ae1f2a307f6783962c414b00d97c1ac0d44ea38e51c09d7bca72aeb9e60` | 7204 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/input-check-after.json` | `860d2083a62eb7f1cf84be6e593b2da47217ba47068c8fa86915b6be53bca3f5` | 3040 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/support-decision.json` | `4e62481d31d0549dcf2fe856f113dcce3506133a39aae63c4b588b476d382209` | 755 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/report-evidence-pins.json` | `b029619dbde5d48baf64a1a4842156d0fdc087748719adf5ea46b9628184cf19` | 14122 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.stdout.txt` | `9d6ff3e66da38fde127b945036fa19ef0844cdd8aefb8d7f38fd8f90a7e82203` | 2526 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.command-start.json` | `2f793cd8f88e61db5ba2d6f606f8451f3a195d9bc53dba53b3c5f4e1c885cf74` | 637 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/mypy.command-result.json` | `145c107740e9ac57e4ec4b68eb9cd72bb32139057b58ef0f323596ec62307fb2` | 740 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_check.stdout.txt` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | 19 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_check.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_check.command-result.json` | `860e941172ee8720d66bb04eb1040e65cc48646ab8cf50ade53492d392690ee6` | 766 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_format_check.stdout.txt` | `f114d83b30c5c657ee43a847a45bafccaea255d82673feb87c26d252c61e29c1` | 26 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_format_check.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/ruff_format_check.command-result.json` | `c397bccd43fe32cb5b8744553eb9bcd7f5e7e4863ba9182d64711c071cdf9cf6` | 781 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/formatter.command-result.json` | `2a6cf5863cd9b97ddad252eabe42fc6be6a7378227d18ed3bd927f12465a8ebd` | 766 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.stdout.txt` | `068bbc43f41f8591081f655ebe236b15d6c4102b5ae59254b2f22a5b9aa2985e` | 3899 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.command-result.json` | `c25ae1b45f4af3c68afc3d0d58e1393189c2a20a23a971085e92e49c25c421c3` | 873 |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/RED.junit.xml` | `8e687957eabc70ca3ba52535db004777737053fd79c03c1ae98695be0c58a658` | 5270 |
