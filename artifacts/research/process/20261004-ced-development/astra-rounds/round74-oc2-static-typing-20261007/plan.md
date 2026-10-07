# Round74：OC2静态导入与类型契约限定修复计划

状态：PLAN_ONLY_NOT_IMPLEMENTED。原gpt-6.1-sol实施，ROOT先复核；本规划不改产品、不运行测试。

## 问题与已读原件

完整GREEN：63 passed，pytest 495.79s，wrapper 498.1624464050401s，exit0；JUnit为63/0 failed/0 errors/0 skipped。随后ruff exit1两处I001，mypy exit1六项；格式exit0。GREEN及三个静态各1次已消耗；R03尚0次。旧证据根：artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007

```text
I001 [*] Import block is un-sorted or un-formatted
   --> src/cloud_edge_robot_arm/research/operational_prefix_v1.py:616:5
    |
614 |       directory: Path,
615 |   ) -> Any:
616 | /     from cloud_edge_robot_arm.research.operational_capture_v1 import (
617 | |         OperationalPrefixRecorderV1,
618 | |         _ISSUER,
619 | |     )
    | |_____^
620 |
621 |       record = _live(application)
    |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
   --> tests/test_operational_prefix_cli_v1.py:143:5
    |
142 |   def test_execute_once_cli_real_worker_no_retry(tmp_path, capsys, monkeypatch):
143 | /     from tests.test_operational_capture_v1 import cpu_components, require_task2
144 | |     from cloud_edge_robot_arm.research import operational_prefix_v1 as api
    | |__________________________________________________________________________^
145 |
146 |       require_task2()
    |
help: Organize imports

Found 2 errors.
[*] 2 fixable with the `--fix` option.
src/cloud_edge_robot_arm/research/operational_prefix_v1.py:285: error: "SimulationWorker" has no attribute "_operational_prefix_application"; maybe "_native_clock_prefix_application"?  [attr-defined]
src/cloud_edge_robot_arm/research/operational_prefix_v1.py:458: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
src/cloud_edge_robot_arm/research/operational_capture_v1.py:79: error: Returning Any from function declared to return "OperationalPrefixRecorderV1"  [no-any-return]
src/cloud_edge_robot_arm/research/operational_capture_v1.py:281: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
src/cloud_edge_robot_arm/research/operational_capture_v1.py:288: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
src/cloud_edge_robot_arm/research/operational_capture_v1.py:310: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
pyproject.toml: note: unused section(s): module = ['ament_index_python.*', 'rclpy.*']
Found 6 errors in 2 files (checked 4 source files)
```

## 根因与待验证假设

- I001：源码同模块导入名及CLI测试相邻跨模块导入块顺序不符合ruff。
- attr_defined：startup动态赋值真实worker私有属性，SimulationWorker类型合同未声明。
- factory_no_any_return：_issue_recorder_v1标注Any而实际只返回私有签发OperationalPrefixRecorderV1。
- check_recorder_no_any_return：check_active实际已有dict标注；recorder._application来源Any与self身份比较造成类型污染/收窄为候选解释，须具体application类型与最终mypy确认。
- json_no_any_return：json.loads静态返回Any；三处真实生产者为字典且深拷贝语义必须保留。

## 限定实施步骤

S1 冻结且只核对四个允许修改文件与本计划列出的保护输入；保存source-before、原ruff/mypy/format/GREEN收据及SHA。ROOT锁定四文件单写者，不锁RW1或全仓。不重跑失败当RED，现有静态输出就是本轮原始失败。
S2 修复两处I001。operational_prefix_v1.py仅调整_issue_recorder_v1内同一模块导入名次序；CLI测试仅调整test_execute_once_cli_real_worker_no_retry内两个相邻import的次序/空行，任何断言、fixture、monkeypatch、参数、test名、body其余语句不变。此计划显式允许这一个原保护测试文件最小扩范围；源导入名集合及模块边界保持。
S3 SimulationWorker原动态_operational_prefix_application属性仅增加TYPE_CHECKING下具体OperationalPrefixApplicationV1 | None声明及对应类型专用导入；无默认赋值，无新运行时import，无新工厂/注册/分派分支。保留getattr(None)及原精确类型、双应用冲突检查，不用setattr或Any强制隐藏attr-defined。worker.py由原保护扩为仅类型声明，不准改现有功能。
S4 为_issue_recorder_v1返回值写OperationalPrefixRecorderV1，TYPE_CHECKING导入具体类；为OperationalPrefixRecorderV1.__init__的application及from_application的application参数使用具体OperationalPrefixApplicationV1，类型专用导入避免循环。check_recorder可将recorder参数由Any收紧为object以保留原type(recorder)精确运行检查；不得移除或搬动原身份/目录/资产/lease检查。check_active已有dict返回，458错误不能假称其未注解；优先以具体_application类型终止身份比较后self被Any收窄的传播，属待验证mypy假设。若仍失败，停并记录新静态结果，不额外cast self或返回值掩盖。
S5 三处json.loads返回仅允许基于内部dict→canonical_bytes→loads闭合来源的精确cast(dict[str, Any], 原表达式)。保留所有JSON往返以维持深拷贝/无别名语义；不改为返回缓存对象，不增加default={}或改变异常顺序。每处说明生产者总为对象：_detached_operational_ledger返回dict；_operational_export为明确dict字面量且调用处非None。Any仅沿用现有异构JSON值契约，不扩大为裸Any，不新增type: ignore/noqa、mypy豁免或全局抑制，不把输入不明的JSON也强转。
S6 先人工diff并生成受限AST等价证据：仅剥离本轮函数/变量类型注解、TYPE_CHECKING专用声明/导入，解包三处经登记的cast；仅在登记的两个import块规范化导入次序。其余AST应相等，测试除那两import外完全相等，worker去除新增TYPE_CHECKING块后完整AST相等。不得全局排序语句/删除assert/异常/比较来制造等价。cast在运行时为恒等调用，仍须保留全部json.loads执行；CLI跨模块import重排不是可普遍忽略副作用，必须由后续独立CLI/lazy-import用例补验证。记录每个允许AST差异坐标及原因。
S7 在改后四文件静止且保护输入匹配后，按verification各一次执行ruff_check、ruff_format_check、mypy。三者都应为exit0；新增类型声明由当前4源mypy命令的导入图校验，不因worker未列为显式目标而扩为全仓mypy。失败保留原输出、立即停止相关后续验证并下一轮Astra，不循环试错。不得自动对保护文件批量ruff --fix/format；人工完成限定布局。
S8 静态通过后一次运行6例targeted_CPU；随后运行round67剩余唯一R03_regression，保留原argv/env（仅额外指定新JUnit与输出收据允许）。预先确认basetemp未含既有原件；如果已存在不清理，停止报告并选经ROOT确认的新未用目录，不复用/删除失败原件。所有stdout/stderr/exitcode/wall/JUnit独立落盘，核对unique/failed/errors/skipped；新失败下一Astra，不重跑。
S9 保存source-after、限定diff/AST证据、输入核对及验证结果。原63例GREEN、12个失败taxonomy条目/CPU原件分母、旧格式通过均按旧SHA原样保留，不能覆盖成新SHA。步骤报告分别列旧软件证据复用与新定向验证、实际运行0、正式研究未验收。供ROOT独立审查；SDD作者不自审/提交，actual继续ROOT调度。

## 验证命令与次数

环境：{"PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1", "MYPYPATH": "src"}

### ruff_check

新增/剩余最多1次；精确argv：
```json
[
  ".venv/bin/python",
  "-m",
  "ruff",
  "check",
  "src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py",
  "src/cloud_edge_robot_arm/research/operational_capture_v1.py",
  "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
  "scripts/run_operational_prefix_v1.py",
  "tests/test_operational_prefix_v1.py",
  "tests/test_operational_capture_v1.py",
  "tests/test_operational_prefix_cli_v1.py",
  "src/cloud_edge_robot_arm/simulation_runtime/worker.py"
]
```

### ruff_format_check

新增/剩余最多1次；精确argv：
```json
[
  ".venv/bin/python",
  "-m",
  "ruff",
  "format",
  "--check",
  "src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py",
  "src/cloud_edge_robot_arm/research/operational_capture_v1.py",
  "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
  "scripts/run_operational_prefix_v1.py",
  "tests/test_operational_prefix_v1.py",
  "tests/test_operational_capture_v1.py",
  "tests/test_operational_prefix_cli_v1.py",
  "src/cloud_edge_robot_arm/simulation_runtime/worker.py"
]
```

### mypy

新增/剩余最多1次；精确argv：
```json
[
  ".venv/bin/python",
  "-m",
  "mypy",
  "--cache-dir=/tmp/bigsmall-oc2-round74-mypy",
  "--follow-imports=silent",
  "src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py",
  "src/cloud_edge_robot_arm/research/operational_capture_v1.py",
  "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
  "scripts/run_operational_prefix_v1.py"
]
```

### R03_regression

新增/剩余最多1次；精确argv：
```json
[
  ".venv/bin/python",
  "-m",
  "pytest",
  "-q",
  "-p",
  "no:cacheprovider",
  "--basetemp=/tmp/bigsmall-oc2-round67-r03",
  "tests/test_native_clock_prefix_worker_v2.py",
  "tests/test_native_clock_publication_v2.py",
  "tests/test_native_reset_capture_v2.py",
  "tests/test_native_clock_prefix_cli_v2.py"
]
```

### targeted_CPU

新增/剩余最多1次；精确argv：
```json
[
  ".venv/bin/python",
  "-m",
  "pytest",
  "-q",
  "-p",
  "no:cacheprovider",
  "--basetemp=/tmp/bigsmall-oc2-round74-targeted",
  "tests/test_operational_prefix_v1.py::test_startup_exact_registry_and_once_only",
  "tests/test_operational_prefix_cli_v1.py::test_real_default_import_has_no_runtime_or_network_effects",
  "tests/test_operational_prefix_cli_v1.py::test_execute_once_cli_real_worker_no_retry",
  "tests/test_operational_capture_v1.py::test_partial_prefix_keeps_all_failures[export]",
  "tests/test_operational_capture_v1.py::test_reset_primary_survives_legacy_freeze_failure",
  "tests/test_operational_capture_v1.py::test_reset_primary_survives_failure_export_failure",
  "--junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/targeted_CPU.junit.xml"
]
```

完整63例GREEN新增0次。三个静态本轮各新增1次；6例定向CPU新增1次；R03只消费原剩余1次，不新增额度。失败停止，不自动重跑。

## 输入SHA256

- AGENTS.md：8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649（1774 bytes）
- artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.json：3b9af379e4d64dded875f976b47b6e7e6476976d67977ccfdcbce5e34389aea2（54412 bytes）
- artifacts/research/process/20261004-ced-development/astra-rounds/round69-oc2-preflight-metadata/plan.json：c146aefd884504c7be0e07128406b24bd18ff308c46466f5201c6d7dcdc55fba（17471 bytes）
- src/cloud_edge_robot_arm/research/operational_prefix_v1.py：05df6d7c638afcb07bf0d269a5211578bcda56a55c8ec47e0c6ac1bcbd294f72（60061 bytes）
- src/cloud_edge_robot_arm/research/operational_capture_v1.py：9ee5af2625a52c9e47d0e1d5e1865f793ba3719cd28a3eaf2a246215c7a669f1（14476 bytes）
- src/cloud_edge_robot_arm/simulation_runtime/worker.py：809b7015b8f316946f521e7990fb3124a429bcfc3c406a31be23ce46d6d0ca20（80038 bytes）
- tests/test_operational_prefix_cli_v1.py：7971985d7032514915509ae0d08d71889aba44721823a12bc54e00d3005cdf9b（6546 bytes）
- tests/test_operational_prefix_v1.py：1ccb56de190f5cea0280882690bead41ed15aaff0fdfa2b74b32ca9c5cd1b426（11934 bytes）
- tests/test_operational_capture_v1.py：ebe63baa223a7f2dc1f99fc28603ceb3ae9505516085c605ef0dbb2a39fa6aaf（18729 bytes）
- src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py：918e029a6a1f0d2a7a455820c721118abdb50b7c5eda6e8ee15f54bed543e67c（11537 bytes）
- src/cloud_edge_robot_arm/research/operational_time_v1.py：b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b（20734 bytes）
- scripts/run_operational_prefix_v1.py：fe8e8c9e021ec437b601895de724f1d10f17eb221fea6b8302c304a65fbcffa9（1885 bytes）
- configs/research/operational_prefix_v1.json：c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1（394 bytes）
- pyproject.toml：b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c（2458 bytes）
- tests/test_native_clock_prefix_worker_v2.py：fbfa14e5596bdba70d5263b7f770dd689bdda342e56389da16985f417bc20b7b（9339 bytes）
- tests/test_native_clock_publication_v2.py：a57b3a1a7ffb8e0c4afb28b96cf355e83c3b52e93317ae17e151667528fa147f（11677 bytes）
- tests/test_native_reset_capture_v2.py：551d080e6eb33d2bcc6183e3be044224aa903c4691066946d0d52775a584f7b8（6239 bytes）
- tests/test_native_clock_prefix_cli_v2.py：0df55934ca677b03a67dc186bfe14d989561f79bd27c6718ce79f8cc7effbae0（4985 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.command-result.json：ccf4d0f164b3d311816c8ddba2fdde2d34e6e72ac95a1ecfdade780259856c6d（839 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.stdout.txt：cf3b56b858287086ee0f769fe34993b63c55be21d161341f394ddd71caec16ee（339 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.stderr.txt：e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855（0 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/full_GREEN.junit.xml：8313fc28e1f4715bee46061d7b330f5fe1e1453d3c1e3e08738a915a7c539dbf（8980 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.command-result.json：187a88b0efbf83a2fbdd80b6461845f4fcbe3f4d18c3d9625f1b44e7ad63d16f（885 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.stdout.txt：99744fd905de28e27d8adb1c1eabf3f548d76e515c0eedecdb32d6e47ead0ce1（999 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_check.stderr.txt：e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855（0 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.command-result.json：336d4a5e356cf1daa13d2fc6b9ca12ce66fbe3816969c757a6d144a140b34512（755 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.stdout.txt：cf51c2f99708ca4b7f8997492507161fe836c15aa949fe65e162e1290e68704a（1113 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/mypy.stderr.txt：e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855（0 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_format_check.command-result.json：bf660d1c30e51eec3c3e13e7570c6c6518bdafb650be5b2f8901a5fe0233c060（901 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/ruff_format_check.stdout.txt：8e93d18ae56550d4eef2feac77e6630617c7e169246e56e39c75d58b46167985（26 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-freeze.json：6c1413fa2d3aecea183ee7135c0203d67ae67e0334dae51affa59a90df0c2454（1449 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/input-check-after.json：ce7c6b4efba596a48eebfdff5aca866448f22a43c4c2c44d613d1bc884245d73（33095 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/test-outcomes.json：b39fcf7bd4799894c42d9f7216380206838ac57ba4e5ed9abb149b227ea69a28（7010 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/failure-taxonomy.json：8018eaf0f0ce0631de6fd5ea4aa58a333023f433947829e15f783c9ab4675634（6449 bytes）
- artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/format-equivalence.json：2f42147ab625cb0c1cff21f0a17db0e1e9ff0c55d5b3880ff18927e435c3984f（879 bytes）

## 前置与验收

- ROOT复核本计划并将四文件交原Sol单写者；独立RW1继续
- 再次验证本计划相关输入SHA，历史收据只读；不递归pin input-check-after内部活跃RW1引用
- 既有63例GREEN与失败日志齐全，不重置次数
- 已可用.venv/bin/python，环境使用原PYTHONPATH/PYTHONDONTWRITEBYTECODE/MYPYPATH
- CPU原始替换缝保持，禁止实际MuJoCo/renderer/model/request；本轮测试仍开发验证
- 新输出目录独占，不覆盖旧basetemp和原始实验字节

- software：四文件限定diff及等价证明、三静态单次exit0、6例定向无skip/error/failure、一次剩余R03通过，原失败分母和63例GREEN完整保留。
- actual：本轮0；OC2真实前缀原前置仍未由软件验收满足。
- formal_research：NOT_ACCEPTED；不晋升T12/METHOD/FINAL/T13或收益。

## 规划工具附属失败

本代理只读行展示超出313行而发生IndexError，退出1；未写入或产品运行。已限制只读终行为min(终行,总行数)。原stderr及来源记于JSON，不冒充产品失败。

新根因、任何计划外失败或范围扩大重新Astra；本轮报告不得把软件通过当真实运行或正式研究验收。
