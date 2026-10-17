# Astra Round75 — OC2 登记表 recorder 类型残留修复计划

状态：PLAN_ONLY_NOT_IMPLEMENTED。新实际 Astra 规划代理 `/root/astra_oc2_residual`，不冒称旧线程恢复。执行者由 ROOT 指定可用 GPT-6.1-sol。规划未改产品、未运行 mypy/Ruff/tests/actual/模型/网络/Git。

## 问题与原始证据

src/cloud_edge_robot_arm/research/operational_prefix_v1.py:459: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
pyproject.toml: note: unused section(s): module = ['ament_index_python.*', 'rclpy.*']
Found 1 error in 1 file (checked 4 source files)

原件目录：`artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation`。round74 Ruff check/format 各一次通过；mypy 一次 exit1；6 case targeted 与 R03 均未运行，各仅余一次。旧 63/63 GREEN 只属于原冻结字节，不是改后实跑。

## 可追溯根因与唯一修复

1. src/cloud_edge_robot_arm/research/operational_prefix_v1.py:170: _LiveApplicationV1.recorder: Any = None is the earliest remaining untyped identity operand.
2. check_recorder first proves type(recorder) is OperationalPrefixRecorderV1, then evaluates recorder is not record.recorder. On the continuing false arm this is recorder is record.recorder; target type Any broadens recorder to Any.
3. Subsequent recorder._application is not self therefore has an Any attribute operand despite constructor application having a concrete annotation; the continuing identity arm broadens self to Any.
4. return self.check_active() consequently has Any, although the declared check_active return is dict[str, Any].
5. Installed mypy 1.20.2 checker.py:6686+ narrow_type_by_identity_equality calls conditional_types for both operand directions; :6671 swaps is-not maps; :8447 proposed Any explicitly broadens to Any. This establishes a concrete propagation route without product/test execution.
6. Only runtime assignment to record.recorder is _issue_recorder_v1:647, from OperationalPrefixRecorderV1 construction at :635; initial None is explicitly checked at :626. Recorder __init__.application and self._application are already concrete after round74. Thus changing the actual registry slot contract closes this source; no second speculative type edit is authorized.

唯一允许修改：`src/cloud_edge_robot_arm/research/operational_prefix_v1.py` 中 `_LiveApplicationV1.recorder: Any = None` → `recorder: OperationalPrefixRecorderV1 | None = None`。既有 TYPE_CHECKING 导入足够。守卫、身份比较、`return self.check_active()`、字段初值/顺序、source/runtime authority 不动。禁止 cast self/return、ignore/noqa、Any 扩展、绕过方法分派或挪动检查。

本地 mypy 源码明确支持 Any 身份比较的拓宽路径；最终修复效果仍须唯一一次改后 mypy 确认。若失败，保留新证据进入下一 Astra 轮，不执行第二种猜测修复。

## 实施与验证

1. S1 ROOT复核本计划与输入；指定当前可用GPT-6.1-sol单写者（旧代理不在live列表，不冒称恢复）。仅协调prefix文件，不锁全仓或RW1。冻结source-before，核对四源等于round74 source-after及历史证据SHA。HEAD 34c7a559/1007仅为ROOT告知的本地背景，不作为本计划已核验事实，不执行Git或推送。
2. S2 沿登记表字段→精确类型检查→身份比较→_application→self→check_active审读完整类型链。_LiveApplicationV1.recorder只允许None初值和_issue_recorder_v1实际具体Recorder赋值；不新增诊断mypy/test调用，不重复RED。存在其他赋值/输入漂移则停止本轮。
3. S3 只把_LiveApplicationV1.recorder: Any = None改成recorder: OperationalPrefixRecorderV1 | None = None。使用既有future annotations及TYPE_CHECKING导入；无新import，无参数/return/guard变动，不变初值、字段序、工厂、登记表权威或异常顺序。
4. S4 保存逐hunk diff、前后source及受限AST证明：唯一允许差异为指定class中recorder AnnAssign.annotation；将这一节点注解还原为Any后全模块AST必须完全相等，注释相同。禁止批量删注解/排序/去assert。注明__annotations__/dataclass Field.type元数据确有变化，不能声称所有反射结果逐字节相同；业务执行与字段默认值保持。其余round74三源哈希不变。
5. S5 用实际源和原失败构成RED依据，按verification顺序ruff check、format --check、四显式源mypy各一次。前两项只检查本轮变动prefix，其他七个round74已通过Ruff目标以保护SHA沿用；mypy保留原四目标/选项，仅新独占cache-dir。任何失败立即保存原件并停止，不追加cast/ignore/第二次mypy或探针。
6. S6 静态全部成功后，消耗原剩余6case targeted_CPU一次，再消耗原剩余R03一次。完整63额外次数0。新targeted basetemp为/tmp/bigsmall-oc2-round75-targeted；R03沿原/tmp/bigsmall-oc2-round67-r03。所有输出/JUnit在round75新独占implementation；开跑前检查目录未存在（包括悬挂软链），不得清理旧目录。冲突记录并交ROOT/Astra，不自行反复换目录试跑。
7. S7 保存command-start/argv/env/stdout/stderr/exit/wall/JUnit、输入前后核对、source-after/限定diff和完整CPU产物分母。保留原63GREEN与所有失败/partial/数据库交付边界，不回写旧收据源SHA、不冒称清单为完整远端包。分别报告作者软件验证、独立审查待完成、actual=0、formal未验收。供ROOT复核再走既有阶段报告/Git交付；实施者本轮不操作Git。

具体 argv/env、次数和门禁见 `plan.json.verification`：新 Ruff check/format 各一次，仅变动文件；mypy 原四目标一次；继承定向 6 case 一次及 R03 一次；完整 63 重跑零次。原 round74 其余 Ruff 目标依相同 SHA 沿用通过记录。

## 实际运行与验收边界

仅开发验证。未来真实运行需完整软件证据、独审、既有 Gate C/D、ROOT 专属 actual 授权，并重新核对原 recipe/source/asset、独占输出、真实租约/worker/application/source 身份与 OC1/observer/raw 分母前置。当前 actual、teacher、GPU/provider/network 均 0；正式研究 NOT_ACCEPTED。源码类型通过不替代真实采集。

四个当前源均逐字节匹配 round74 source-after。ROOT 告知本地 HEAD 为 34c7a559（1007）；规划不执行 Git，不假定已推。禁止全仓 pin 或递归冻结活跃 RW1/进度引用。所有历史失败和原始实验字节保留。

## 实际输入 SHA256

下列路径均为本轮实际读取的有界输入。四源按 round74 source-after 校验，其他原保护输入按 round74 原 SHA 校验；全部匹配。

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.json` | `3b9af379e4d64dded875f976b47b6e7e6476976d67977ccfdcbce5e34389aea2` | 54412 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round69-oc2-preflight-metadata/plan.json` | `c146aefd884504c7be0e07128406b24bd18ff308c46466f5201c6d7dcdc55fba` | 17471 |
| `src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `5ab9ec9c9e4d9526ed8ea9e7cdea721ad05a36fa39a103e7daa6f6d425f94283` | 60185 |
| `src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `06373a9c702420ab38c5afa20f888efb35cd6ea109cf094c662fa04511e60b3c` | 14778 |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4` | 80239 |
| `tests/test_operational_prefix_cli_v1.py` | `f3cc2a0d2de8fb18dbcfa3c9b9969d92f657fd03b448b7cda7c58d5926480cfc` | 6546 |
| `tests/test_operational_prefix_v1.py` | `1ccb56de190f5cea0280882690bead41ed15aaff0fdfa2b74b32ca9c5cd1b426` | 11934 |
| `tests/test_operational_capture_v1.py` | `ebe63baa223a7f2dc1f99fc28603ceb3ae9505516085c605ef0dbb2a39fa6aaf` | 18729 |
| `src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py` | `918e029a6a1f0d2a7a455820c721118abdb50b7c5eda6e8ee15f54bed543e67c` | 11537 |
| `src/cloud_edge_robot_arm/research/operational_time_v1.py` | `b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b` | 20734 |
| `scripts/run_operational_prefix_v1.py` | `fe8e8c9e021ec437b601895de724f1d10f17eb221fea6b8302c304a65fbcffa9` | 1885 |
| `configs/research/operational_prefix_v1.json` | `c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1` | 394 |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` | 2458 |
| `tests/test_native_clock_prefix_worker_v2.py` | `fbfa14e5596bdba70d5263b7f770dd689bdda342e56389da16985f417bc20b7b` | 9339 |
| `tests/test_native_clock_publication_v2.py` | `a57b3a1a7ffb8e0c4afb28b96cf355e83c3b52e93317ae17e151667528fa147f` | 11677 |
| `tests/test_native_reset_capture_v2.py` | `551d080e6eb33d2bcc6183e3be044224aa903c4691066946d0d52775a584f7b8` | 6239 |
| `tests/test_native_clock_prefix_cli_v2.py` | `0df55934ca677b03a67dc186bfe14d989561f79bd27c6718ce79f8cc7effbae0` | 4985 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.command-result.json` | `ccf4d0f164b3d311816c8ddba2fdde2d34e6e72ac95a1ecfdade780259856c6d` | 839 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.stdout.txt` | `cf3b56b858287086ee0f769fe34993b63c55be21d161341f394ddd71caec16ee` | 339 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.junit.xml` | `8313fc28e1f4715bee46061d7b330f5fe1e1453d3c1e3e08738a915a7c539dbf` | 8980 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.command-result.json` | `187a88b0efbf83a2fbdd80b6461845f4fcbe3f4d18c3d9625f1b44e7ad63d16f` | 885 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.stdout.txt` | `99744fd905de28e27d8adb1c1eabf3f548d76e515c0eedecdb32d6e47ead0ce1` | 999 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.command-result.json` | `336d4a5e356cf1daa13d2fc6b9ca12ce66fbe3816969c757a6d144a140b34512` | 755 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.stdout.txt` | `cf51c2f99708ca4b7f8997492507161fe836c15aa949fe65e162e1290e68704a` | 1113 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_format_check.command-result.json` | `bf660d1c30e51eec3c3e13e7570c6c6518bdafb650be5b2f8901a5fe0233c060` | 901 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_format_check.stdout.txt` | `8e93d18ae56550d4eef2feac77e6630617c7e169246e56e39c75d58b46167985` | 26 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-freeze.json` | `6c1413fa2d3aecea183ee7135c0203d67ae67e0334dae51affa59a90df0c2454` | 1449 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/input-check-after.json` | `ce7c6b4efba596a48eebfdff5aca866448f22a43c4c2c44d613d1bc884245d73` | 33095 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/test-outcomes.json` | `b39fcf7bd4799894c42d9f7216380206838ac57ba4e5ed9abb149b227ea69a28` | 7010 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/failure-taxonomy.json` | `8018eaf0f0ce0631de6fd5ea4aa58a333023f433947829e15f783c9ab4675634` | 6449 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/format-equivalence.json` | `2f42147ab625cb0c1cff21f0a17db0e1e9ff0c55d5b3880ff18927e435c3984f` | 879 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/plan.md` | `66d3f6947fe3ff1f9375fb366d02eb6c64379d5b8b5be82402835fb2c69b9332` | 18755 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/plan.json` | `c0bef1f6970fb3dc7457fb7e240b4fba2b8ec561d139bde7b72a82cf86c64fe2` | 25516 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/root-authorization.json` | `cc2e8ba96bf8c92fdd08a17d8302ca8279bb5e393814764fb4f503851c24670a` | 8994 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/step-report.md` | `766ceba74dddfb9e4e33f7af469fd17c23a160f099e121e1ed05688d4215e916` | 2161 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/step-report.json` | `70d16e6478f869b60ec6d0a1d064fdbc25ec01ba7ac662c81287df55df8a25b6` | 4896 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/failure-receipt.json` | `70d16e6478f869b60ec6d0a1d064fdbc25ec01ba7ac662c81287df55df8a25b6` | 4896 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/mypy.stdout.txt` | `e7b2c483153c89e482a456521da2ce62b44cb1189d1fc54b32f3f83db4df122d` | 287 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/mypy.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/mypy.command-start.json` | `83640af1f138dc92d9889f2c86182aca77ad1ba13d6656520f3be1ee424b1808` | 667 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/mypy.command-result.json` | `c66ee3c94ff821036ea2a83544dd2ce4e772a8eb921034da5da290248bee808d` | 770 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-freeze.json` | `0df92ba0f2bb6fd3f5793758be5d77b71b9db485c245dfe260cf18927f46428a` | 667 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/restricted-ast-proof.py` | `507ab7a4b03c5698e1c8b72c97263856e73485ba6f7dca853283a9645e0f2454` | 8879 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/restricted-ast-proof.json` | `cd93e4edba88cef743fb20dba551927546b22ed7ead094a2580a4d4b41013a08` | 11710 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/ruff_check.command-result.json` | `5407925b5d4a947917c6be23d2bf552321a7c515f12ab93e6b9b199117874c2b` | 900 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/ruff_check.stdout.txt` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | 19 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/ruff_format_check.command-result.json` | `aba639c410ad5a4268b14d07b0f916d702412dcf2e599cac095116a62a90f2f7` | 916 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/ruff_format_check.stdout.txt` | `8e93d18ae56550d4eef2feac77e6630617c7e169246e56e39c75d58b46167985` | 26 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `5ab9ec9c9e4d9526ed8ea9e7cdea721ad05a36fa39a103e7daa6f6d425f94283` | 60185 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `06373a9c702420ab38c5afa20f888efb35cd6ea109cf094c662fa04511e60b3c` | 14778 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4` | 80239 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/tests/test_operational_prefix_cli_v1.py` | `f3cc2a0d2de8fb18dbcfa3c9b9969d92f657fd03b448b7cda7c58d5926480cfc` | 6546 |

## 本地类型检查器证据

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `.venv/lib/python3.12/site-packages/mypy/checker.py` | `a259272147aaab699a88d3f9ff5d123d70cf0797f80caf787ad166b4409f548b` | 430682 |
| `.venv/lib/python3.12/site-packages/mypy/version.py` | `790cd0770ddf20796690e1c5c7266fb00e3911cb8d2f3ef4a089aff3cbbda7fa` | 23 |

这些环境证据仅用于解释 installed mypy 1.20.2 的逻辑；没有运行检查器，也不是可移植复现包。
