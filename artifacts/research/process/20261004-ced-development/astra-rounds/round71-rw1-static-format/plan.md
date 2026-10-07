# Round71 — RW1 静态格式失败修复计划

状态：PLAN_ONLY_STATIC_REPAIR_NOT_EXECUTED。Astra 本轮只读诊断及写计划；ROOT 仍为实施作者。

ROOT 的 Round68 fixture 修复已取得唯一一次 82/82 命名 CPU GREEN；随后 Ruff check 的唯一 E501 是 ROOT 新断言 103 字符超过既有 100 上限。Ruff format --check 同时报告 producer/tests 两文件需要格式化；mypy 单 producer 已成功，窄回归尚未运行。原失败原件永久保留，本计划不宣告修好。

## planner

```json
{
  "requested_model": "gpt-6-astra",
  "role_source": "explicit ROOT existing Astra-thread dispatch under AGENTS.md",
  "runtime_model_independently_verified": false
}
```

## raw_failure

```json
{
  "receipt": {
    "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/static-failure-receipt.json",
    "sha256": "89489565a051dc641aa5069fcacf88be44e8615f1acb5a82230b4e48108eed5b",
    "bytes": 6562
  },
  "step_report": {
    "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/step-report.md",
    "sha256": "c7422a483feec42e160df195b1960a495bff479678244eb7aac089435f9b0de2",
    "bytes": 778
  },
  "ruff_check": {
    "command": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.command-result.json",
      "sha256": "a8108dfee2fc5397e36f6bab094338a90f9e960a57ea71e41f9bd4b4d735a8e1",
      "bytes": 516
    },
    "stdout": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.stdout.txt",
      "sha256": "b1fc83e94d46dddd6eb703305803452b736828aeb0a2cfc3f37d06b624594477",
      "bytes": 526
    },
    "stderr": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.stderr.txt",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "bytes": 0
    },
    "exit_code": 1,
    "diagnostics": 1,
    "code": "E501",
    "path": "tests/test_protocol_generation_sources.py",
    "line": 1288,
    "observed_length": 103,
    "configured_max": 100
  },
  "ruff_format_check": {
    "command": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.command-result.json",
      "sha256": "75bf548d7233ce2a13a8fd2a3a8d3697b6045ffdf24c1e9a2ef3c4e046a5aaca",
      "bytes": 532
    },
    "stdout": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.stdout.txt",
      "sha256": "7dbe375e289649c848e24170f7635511895579143ce4bfad371e7d984df74a57",
      "bytes": 160
    },
    "stderr": {
      "path": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.stderr.txt",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "bytes": 0
    },
    "exit_code": 1,
    "would_reformat": [
      "src/cloud_edge_robot_arm/research/protocol_generation.py",
      "tests/test_protocol_generation_sources.py"
    ]
  },
  "old_failures_preserved_not_relabelled": true
}
```

## diagnosis

```json
{
  "confirmed": [
    "ROOT as Round68/70 inline author introduced the103-character failure-message assertion; test-source.diff and raw Ruff output establish this provenance. This is a new formatting failure, not an owner behavior failure.",
    "Existing pyproject.toml line-length100 remains authoritative. Both owned files are reported by original formatter; producer still matches its pre-Round68 hash, so its formatting requirement predates ROOT fixture edit.",
    "Current source bytes match original static-failure-source-freeze for both files. Planner independently read logs/diff/source/config and verified original JUnit82 unique nodes in recorded order with no failures/errors/skips."
  ],
  "limit": "No formatter diff or formatting command has been run by planner. Exact proposed formatting delta must be saved and checked during implementation; formatter success alone cannot prove no logic change. AST equality ignores positions and ordinary comments, so additional complete diff/comment review is mandatory. No actual behavior or higher research gate is established."
}
```

## prior_success

```json
{
  "named_GREEN": {
    "command": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.command-result.json",
    "junit": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.junit.xml",
    "unique_cases": 82,
    "passed": 82,
    "failed": 0,
    "errors": 0,
    "deselected": 32,
    "runs": 1,
    "pytest_s": 1.87,
    "wrapper_s": 2.1166441420209594,
    "new_runs_allowed": 0,
    "carry_forward_condition": "Both full-module ASTs exact plus test parameter/decorator identities and relevant comments/config unchanged; identify tested pre-format hashes and formatted post hashes separately."
  },
  "mypy": {
    "command": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/mypy.command-result.json",
    "exit_code": 0,
    "source_files": 1,
    "new_runs_allowed": 0,
    "carry_forward_condition": "Same exact producer AST, unchanged typing/type-ignore comments and unchanged pyproject config."
  },
  "pending_regression": "NOT_RUN; one originally authorized narrow regression remains pending",
  "original_round66_GREEN": "81pass/1fixturefailure remains unchanged history, not superseded bytewise or counted as new82 cases"
}
```

## scope

```json
{
  "planner_write_allowlist": [
    "artifacts/research/process/20261004-ced-development/astra-rounds/round71-rw1-static-format/plan.md",
    "artifacts/research/process/20261004-ced-development/astra-rounds/round71-rw1-static-format/plan.json"
  ],
  "implementation_source_allowlist": [
    "src/cloud_edge_robot_arm/research/protocol_generation.py",
    "tests/test_protocol_generation_sources.py"
  ],
  "author": "ROOT inline after reading71; role transfer70 remains",
  "new_evidence_exclusive_root": "artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/round71-static",
  "format_only_exception": "Round68 producer byte-freeze becomes a strictly verified formatting-only delta under this new plan. All owner semantics and original two-file outer scope stay fixed; do not rewrite prior68/70 authorization.",
  "protected": [
    "pyproject.toml maxline100 and lint/type configuration",
    "imports order, literals, names, control flow, parameter identities, assertions and owner contracts",
    "original37/64 input maps,7 role/dispatch pins, all historical logs and CPU fixtures",
    "teacher/backend/OC1/worker and RW2/RW3 integration",
    "platform evidence, original real event field provenance and fixed D deadline"
  ],
  "forbidden": [
    "ruff check --fix or import sorting",
    "new ignores/noqa/skip/xfail, dropping files or tests to obtain pass",
    "editing any old receipt/check/result or frozen source archive",
    "product owner or test semantic changes",
    "platform probes, actual recovery0002, freezev3, provider/physics/camera/network",
    "Git/staging/commit/push",
    "new subagent spawn or ROOT signing own independent review",
    "writing six ROOT summary docs"
  ],
  "parallel_scope": "Active OC2 implementation and six ROOT summaries are excluded from pinning; no whole-repository quiet claim."
}
```

## ast_equivalence_contract

```json
{
  "coverage": "entire producer module and entire test module, never only modified functions",
  "method": "ast.parse(before_text, type_comments=True) and ast.parse(after_text, type_comments=True), then compare ast.dump(tree, include_attributes=False) exactly for each whole module; save full canonical dumps or exact dump hashes plus equality and parsed source hashes. No NodeTransformer, node removal, import reorder, return rewrite or custom normalization.",
  "position_note": "AST type-ignore lineno is stored as a field; if any such field changes prevent exact equality, do not normalize it away: preserve evidence and stop for next Astra.",
  "parameter_proof": "Compare all test decorators/parametrize ASTs and function names against frozen preformat module, retain exact saved82 node IDs and prove unchanged without pytest collect/import. Full AST equality subsumes parameter equality but save explicit result linked to original identities/JUnit.",
  "additional_diff_review": "Save full raw before/after files and unified diff produced with stdlib difflib, not Git. Inspect all hunks for whitespace/line wrapping/quote style only; preserve string/docstring values, comment contents, noqa/type-ignore pragmas, imports order and assertions. Do not remove negative cases or failure preservation.",
  "failure_behavior": "If AST unequal or any nonformat semantic/comment/config change occurs, stop before tests/check acceptance and send new Astra. Do not silently repair normalization or repeat tests to mask the delta."
}
```

## tasks

```json
[
  {
    "id": 1,
    "title": "固定失败与格式化前基线，仅格式化两文件并证全AST相等",
    "actions": [
      "ROOT reads both71 plans and checks bounded current2source, config, original receipt/source archives, prior role/authorization/plans and listed fixed evidence. Reuse saved64/7/37 prior checks rather than rehash whole repository or CPU denominator. All relevant fixed pins must remain exact; only the two permitted format deltas are later exempt.",
      "Create round71-static exclusively. Save input-pins-before, full source-before, exact formatting argv/env/start/end/exit/stdout/stderr and pre/post metadata. Keep original static failure files,82GREEN,81/1history and old CPU bytes untouched.",
      "Run designated two-file ruff format write command once. No check --fix/import organizer and no additional source edits to change behavior. Save full source-after and diff, run stdlib whole AST and parameter proof under above strict contract. The long assertion is only wrapped with identical expression/string. If formatter cannot satisfy contract, stop for next Astra."
    ]
  },
  {
    "id": 2,
    "title": "两项新静态检查与尚未运行窄回归各一次，冻结待他人独审",
    "actions": [
      "Only after exact whole-module AST and diff/parameter proof, run new Ruff check once and Ruff format --check once on both complete owned paths using same config. Independent commands may be batched; record separate argv/env/times/exit/rawstdout/rawstderr. Do not rerun mypy or82 namedGREEN. Any unexpected failure stops further dependent work and returns to Astra.",
      "When both static checks pass, run pending original narrow regression selection once with fresh basetemp and new JUnit/log files. Record actual unique denominator and CPU sentinel scope; no whole-suite expansion,82 replay, platform API, actual backend or external action.",
      "Freeze both final modules and bounded input after map. Preserve formatter/check/regression outputs and source hashes before/after; verify originals plus protected configuration/role/history remain exact. Quietness is limited to two owned paths and fixed protected inputs. Save step-report.md/json with original static failure ->71 plan ->format-only diff and AST proof ->new one-shot checks/regression; cite original82 GREEN and mypy rather than representing new runs.",
      "ROOT remains sole author. Different available existing reviewer independently checks full diff/AST/parameter identity, original82/mypy provenance, new static/regression and historical/protected evidence. No self independent acceptance. If reviewer unavailable, await independent review without creating a new agent; actual/higher gates remain closed."
    ]
  }
]
```

## verification

```json
{
  "env": {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPATH": "src:.",
    "MYPYPATH": "src"
  },
  "commands": {
    "format_write": {
      "argv": [
        ".venv/bin/python",
        "-m",
        "ruff",
        "format",
        "src/cloud_edge_robot_arm/research/protocol_generation.py",
        "tests/test_protocol_generation_sources.py"
      ],
      "max_runs": 1,
      "kind": "future format-only mutation; not executed by planner"
    },
    "ruff_check": {
      "argv": [
        ".venv/bin/python",
        "-m",
        "ruff",
        "check",
        "src/cloud_edge_robot_arm/research/protocol_generation.py",
        "tests/test_protocol_generation_sources.py"
      ],
      "max_runs": 1
    },
    "ruff_format_check": {
      "argv": [
        ".venv/bin/python",
        "-m",
        "ruff",
        "format",
        "--check",
        "src/cloud_edge_robot_arm/research/protocol_generation.py",
        "tests/test_protocol_generation_sources.py"
      ],
      "max_runs": 1
    },
    "pending_regression": {
      "argv": [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_protocol_generation_sources.py",
        "-k",
        "successor or actual_reset_elapsed or budget_uses_fault_start or execute_preserves_allocation or wrong_review_pin or actual_path_wires or wall_deadline",
        "--basetemp=/tmp/bigsmall-r07-round71-regression",
        "--junitxml=artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/round71-static/regression.junit.xml"
      ],
      "max_runs": 1,
      "denominator": "Record observed selected unique cases, passed/failed/errors/deselected; do not infer32 or add to82."
    }
  },
  "named_GREEN_repeats": 0,
  "mypy_repeats": 0,
  "new_RED": 0,
  "pytest_collect_only": 0,
  "platform_probe_repeats": 0,
  "actual_calls": 0,
  "command_records": "Exact argv/cwd/env/start/end/wrapper duration/exit/stdout/stderr exclusive new files, including failures; no old result replacement."
}
```

## execution_preconditions

```json
[
  "ROOT reads plan before change; current owned bytes equal frozen71 input pins",
  "fresh exclusive round71-static, fresh regression basetemp, existing .venv tools only",
  "every exec require_escalated; Python .venv/bin/python with PYTHONDONTWRITEBYTECODE=1",
  "prior37/64 and7 role checks reused as fixed evidence, no active OC2/docs pinning",
  "CPU-only sentinels still prohibit real provider/backend initialize/fault/physics/camera actions",
  "AST equality and complete diff review precede successful evidence carry-forward"
]
```

## acceptance

```json
{
  "now": "PLAN_ONLY_NOT_STATIC_PASS",
  "maximum_author": "VERIFIED_RW1_TASK1_AWAITING_INDEPENDENT_REVIEW",
  "independent_review_required": true,
  "author_cannot_self_review": true,
  "actual_runs": 0,
  "actual_binding_proven": false,
  "RW2_RW3": false,
  "freeze_v3": false,
  "actual_recovery_0002": false,
  "formal_accepted": false,
  "g4_measured": false,
  "suspend_restart_hostpause_actual": "UNTESTED",
  "global_source_quiet": false
}
```

## new_issue_rule

```json
"New cause, pin drift, path collision, nonformat delta, failed equality, or unexpected static/regression failure: preserve original outputs and pause affected work for next actual gpt-6-astra plan before further changes/reruns. Unrelated OC2 may continue."
```

## planning_execution

```json
{
  "read_only_source_and_evidence": true,
  "input_count": 47,
  "input_mismatches": [],
  "JUnit_unique_identity_check": 82,
  "format_commands": 0,
  "source_edits": 0,
  "test_runs": 0,
  "product_imports": 0,
  "actual": 0,
  "platform_probes": 0,
  "Git": 0,
  "network": 0,
  "new_agents": 0,
  "output_files": 2
}
```

## 实际输入 SHA256 / bytes

以下固定原件与当前 owned source 已逐字节读取核验。旧37/64/7验收映射仅作固定证据沿用；不重算全仓/旧CPU文件，不 pin OC2/动态总结。

| Path | SHA256 | bytes |
|---|---|---:|
| AGENTS.md | 8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649 | 1774 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/failure-receipt.json | 260900da9f05402502cd1ab6d50fd836ecc77c33b1c831add253439aa632c976 | 14684 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/green.command-result.json | f3af9855e2f02bf3373cd61858c8ff35cf39821050a4f160b6a0393ad52cd2c0 | 18380 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/green.junit.xml | 198938f85ce6e60826c173eccab3db79198e6bfb2f2b734dbdd9ddb782673aeb | 19705 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/green.stderr.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/green.stdout.txt | 732da9505c2b459936b435d3496c7e214f7412a24fd24db9a37878f08de2a01c | 8348 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/input-pins-after.json | f20d8747c5bde0b0dcf4a07356f0948339da70c22fc71b40be4745dcefe60261 | 16872 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.command-result.json | af8788c1108ef38f670e8e29488582bcde4ace018320e4122f82098573b71d81 | 888 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.command-start.json | a7dea4972a74a2045ea85c5a334b86e55903dbbdddabbf018299905c2e7911f9 | 784 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.junit.xml | aad48e84d1becf29786958d71cef2d9ccba8aa8a7387fda5f0bbbd225ac1d355 | 12006 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.stderr.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/green.stdout.txt | 20014f83be5f00e082d2bde6524f8d55125c919e858996af64d008bb5ffbadcb | 402 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/input-pins-before.json | 89c3a2fb78543f0fd2a7aa1da1872a36c2d539a1fd0051512010031550780824 | 19639 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/mypy.command-result.json | 646a9e98d1cbb52ed04216d22753769f96e0bca51875fe3c0e53882185c79ee9 | 533 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/mypy.stderr.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/mypy.stdout.txt | bdbe2f06ea7266524139adf5e97f20c2834e875a541276b7c38090af317ddeaf | 128 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/node-id-tool-failure.json | 5c403b33258293846dc1d5338218706eee45a3fda91606520e9f322e19c1aed6 | 1723 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.command-result.json | a8108dfee2fc5397e36f6bab094338a90f9e960a57ea71e41f9bd4b4d735a8e1 | 516 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.stderr.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-check.stdout.txt | b1fc83e94d46dddd6eb703305803452b736828aeb0a2cfc3f37d06b624594477 | 526 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.command-result.json | 75bf548d7233ce2a13a8fd2a3a8d3697b6045ffdf24c1e9a2ef3c4e046a5aaca | 532 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.stderr.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/ruff-format.stdout.txt | 7dbe375e289649c848e24170f7635511895579143ce4bfad371e7d984df74a57 | 160 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/static-failure-receipt.json | 89489565a051dc641aa5069fcacf88be44e8615f1acb5a82230b4e48108eed5b | 6562 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/static-failure-source-freeze/src/cloud_edge_robot_arm/research/protocol_generation.py | 07e12a8921cc41b2f0229235614f8a16ec3b4520bd266b0bc46bc198ecc09bd7 | 65393 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/static-failure-source-freeze/tests/test_protocol_generation_sources.py | a3ec1598ff056c371eafbc2071da66c3920e9fcb6deeaaddac9ace58ec02224b | 50220 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/step-report.md | c7422a483feec42e160df195b1960a495bff479678244eb7aac089435f9b0de2 | 778 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/test-identities-before-green.json | 9f014ab3e2ec8cfc74e0cd55ddbadb260e4debf8d6e7275408dd887fe6f06cdb | 9092 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round68/test-source.diff | 101960426004ad7c832428953c4cb7ff08d22fa500310c72029db5a65999f014 | 2695 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/root-round68-authorization.json | 05a189584f7db79c05b6d1550ad8dc89713d34f70c7ed6ca14bee9a63bb8a8fc | 754 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/root-round68-dispatch-failure.json | 300471f3c9607f15d64f19f16539108eab7742c5a516506fc6c298d957ca9d4b | 959 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/root-task1-authorization.json | a0bec6df57fe610b5bc9f6fe70a6eb94661a75209588c7efaf522f3d5ce41dcc | 4437 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/round70-dispatch-recovery/role-transfer.json | bd83cd3e6f6dc68cff29c9794b5134e5fa00381d2ccbd1a05926a0da58d59abf | 1568 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/round70-dispatch-recovery/step-report.json | bd83cd3e6f6dc68cff29c9794b5134e5fa00381d2ccbd1a05926a0da58d59abf | 1568 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/round70-dispatch-recovery/step-report.md | 7bf050ffacc187170506ac7922f530c138c9dfb2378dad1cb32ac66094eb3d99 | 439 |
| artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/round70-dispatch-recovery/transfer-receipt.json | bd83cd3e6f6dc68cff29c9794b5134e5fa00381d2ccbd1a05926a0da58d59abf | 1568 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round57-recovery-wall/plan.json | 5b5f47a9f455e3731e58e14092252cadda4f97369aee2a167ccc3d354a9a8450 | 9308 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round57-recovery-wall/plan.md | 5dd08d0e57660c49044b321820d5ee83d52e6f1c026c494bbaae85eb31fe93db | 18804 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round66-rw1-event-episode/plan.json | d7358d578873bf0d0210e9e1066623e657998378ccbaf25c9ad33143e9b05f24 | 26897 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round66-rw1-event-episode/plan.md | 1fea4d3a21c2e57afd97d40106adb232caf517467e9d1fc9dbb3423c2e19afb9 | 20432 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round68-rw1-fixture-alias/plan.json | 21cb2128d9a5e8ad7cfd1055381207e15527547f09eccf0a2fa701eed073a92e | 31995 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round68-rw1-fixture-alias/plan.md | 3526fd23bc1aaad099e2589bac5650d0109eb853ccb80c985585397dcd3fee1a | 22369 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round70-rw1-dispatch-capacity/plan.json | 00e57e580b7d04e2febfbcce340f348cc7fc2544986f97a8ef50cec414338294 | 9827 |
| artifacts/research/process/20261004-ced-development/astra-rounds/round70-rw1-dispatch-capacity/plan.md | f13cf84b50febe01a1110c3a9cb0fe5383c7196402b16f80b41d64ccbd353a2a | 5629 |
| pyproject.toml | b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c | 2458 |
| src/cloud_edge_robot_arm/research/protocol_generation.py | 07e12a8921cc41b2f0229235614f8a16ec3b4520bd266b0bc46bc198ecc09bd7 | 65393 |
| tests/test_protocol_generation_sources.py | a3ec1598ff056c371eafbc2071da66c3920e9fcb6deeaaddac9ace58ec02224b | 50220 |
