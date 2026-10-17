# R189 — prepare_red 传递字段恢复

实际规划者：gpt-6-astra（/root/astra_status_plan）。冻结，等待 ROOT 复核。

已核原始43e036：退出1，KeyError: cmd。该 reader 只读取门控并访问缺失字段；原准备脚本从未启动。当前 transport 仅有 kind/stdout/stderr/tool_capture。原 ROOT reservation 已1/0、author仍0/1，二者不是同一种耗用状态。

282固定输入全部匹配；原 evidence目录及两外层流文件均不存在。以下合同仅允许 ROOT 一次标准库元数据动作：保存三份完整before，新增精确 transport.cmd，并更新 ROOT账本和activation的完整gate pin，保持其余全部字段与计数。原reader不重放；脚本、参数、有限环境、120秒SIGALRM及源码不变。

恢复成功后仍需 ROOT 明确派发同一 Sol 执行原已reserved的唯一prepare_red；本计划恢复动作本身不执行该脚本，更不运行RED8。

```json
{
  "schema_version": 1,
  "round": "R189",
  "date": "2026-10-14",
  "actual_author": "/root/astra_status_plan",
  "author_model": "gpt-6-astra",
  "status": "FROZEN_PENDING_ROOT_GATE",
  "issue": {
    "classification": "PRE_LAUNCH_METADATA_TRANSPORT_SHAPE_FAILURE",
    "evidence": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/original-failure.json",
    "actual": "Reader43e036 exit1 KeyError cmd. Only JSON/pathlib read+lookup; no prepare command launch.",
    "cause": "Author consumer assumed transport.cmd although frozen gate only declares kind/stdout/stderr/tool_capture. This is not a product or preparation-script failure.",
    "capture": "Original full available combined object preserved; independent stdout/stderr unavailable null."
  },
  "inputs": [
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/initial-finding.json",
      "bytes": 1332,
      "sha256": "b7301747aad48ef7e3443adbad0850b858caf6fd9ba5930eced49ea292f3b155"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/original-failure.json",
      "bytes": 1876,
      "sha256": "da6ad21c856ba5d656eaee0d0f1cfe41d6606511d377b350dee57774b4483fdf"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/script-gate.json",
      "bytes": 88437,
      "sha256": "bf4e7f51481d795c26fbdd261a873708cd8ac798b49ad1e48b5cc3896551e5d9"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-command-ledger.json",
      "bytes": 12993,
      "sha256": "36c910378173f3e2c8c478ab6465728732c575341035dd20504357a66d6d7cf1"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/command-ledger.json",
      "bytes": 12227,
      "sha256": "765c2d33144b9d46e0181e1a54b5db0367c25e218d979759f12486888fc47060"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-activation.json",
      "bytes": 1403671,
      "sha256": "b47df02ccd173a693d4e6ef596a1b2cef591e7940c9a068dd94f14ca1c063bd6"
    },
    {
      "bytes": 13233,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare-evidence.py",
      "sha256": "77cb39339ff2f7aa5d4293174d0fbefb284e9554f16bfd0049c7856516b8e852"
    },
    {
      "bytes": 14179,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/implementation/run-command.py",
      "sha256": "049d873e6328f89641d20d9577de448818d6ff9ff9161054abebaeb27f4bc84e"
    },
    {
      "bytes": 16271,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/implementation/root-settlement.py",
      "sha256": "542f408da66cc5dabf061a994d3877d73dd90c227f2e4d0c48e07eaf3dbfca94"
    },
    {
      "bytes": 12498,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_projection_closure.py",
      "sha256": "cdcf814b8072fc11995f4455c78fdc39219090e87813c89594d41f5b9c70f5ae"
    },
    {
      "bytes": 14806,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/run-command.py",
      "sha256": "6dc5ecae7d14fa8d5119b999064f604ca5f0fe5f4c0e6eed6963f28f84de054e"
    },
    {
      "bytes": 20629,
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/root-settlement.py",
      "sha256": "20a365502526256d38039bbcef061c9d6f7b9b522935aafa45f4cfab656b6e9a"
    }
  ],
  "input_roles": {
    "fixed": "All original failure/raw and six code pins; author ledger fixed during metadata repair.",
    "mutable_archived": [
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/script-gate.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-command-ledger.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-activation.json"
    ],
    "input_records": "All282 gate.commands.prepare_red.input_records remain byte/hash fixed; actual282match. No gate/ROOTledger/activation overlaps observed."
  },
  "scope": {
    "actor": "ROOT",
    "source_edits": 0,
    "script_edits": 0,
    "only_mutations": {
      "script-gate.json": "Add commands.prepare_red.transport.cmd exactly as approved_transport.cmd; every existing field/value remains identical.",
      "root-command-ledger.json": "Only replace commands.prepare_red.script_gate_pin with complete after-gate path/bytes/SHA; retain RESERVED_BY_ROOT/used1/remaining0/attempts1/retries0/sameRID.",
      "root-activation.json": "Only replace script_gate with identical complete after-gate pin; all other fields including source_gate_before, historical inputs/status/released counts unchanged."
    },
    "forbidden": [
      "replay original failing lookup",
      "modify argv/env/source hashes/timeouts/input_records",
      "change author ledger or reset reservation",
      "change STATE/PHASE or product/test source",
      "run prepare script within metadata recovery",
      "release RED or other held slots",
      "AST/import product/static/compile/probe/Git/network"
    ]
  },
  "approved_transport": {
    "cmd": "set -C\nexec env -i BIGSMALL_R158_COMMAND=t1_green 'BIGSMALL_R158_LEGACY_GOLDENS=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013/implementation/legacy_control/legacy-goldens.json' LANG=C.UTF-8 'PATH=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin' PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare-evidence.py' red > '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare_red-outer-stdout.txt' 2> '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare_red-outer-stderr.txt'",
    "shell": "/bin/bash",
    "login": false,
    "cwd": "/home/ningyd/文档/ChatGPT/BIGsmall",
    "launcher_argv": [
      "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare-evidence.py",
      "red"
    ],
    "finite_env": {
      "BIGSMALL_R158_COMMAND": "t1_green",
      "BIGSMALL_R158_LEGACY_GOLDENS": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013/implementation/legacy_control/legacy-goldens.json",
      "LANG": "C.UTF-8",
      "PATH": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin",
      "PYTHONDONTWRITEBYTECODE": "1",
      "PYTHONPATH": "src:."
    },
    "timeout_seconds": 120,
    "hard_cap": "Existing script signal.SIGALRM120 unchanged",
    "stdout": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare_red-outer-stdout.txt",
    "stderr": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare_red-outer-stderr.txt",
    "derivation": "set -C newline exec env -i + shlex.quote on each sorted KEY=value argument and each launcher argv element, then exact quoted redirection paths. No interpolation/eval/sourcing.",
    "execution_authority": "Not executed by R189 metadata action. After ROOT inspects exact text and metadata receipt, same Sol may use this literal command for already-reserved original prepare_red once. No second preflight lookup/replay."
  },
  "recovery": {
    "id": "r189-transport-metadata-addition-once",
    "authorized": 1,
    "used": 0,
    "remaining": 1,
    "retries": 0,
    "owner": "ROOT",
    "timeout_seconds": 60,
    "interpreter": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
    "mode": "One fully ROOT-reviewed inline stdlib action, no new helper execution layer",
    "preconditions": [
      "Match direct before pins and282fixed input_records; assert exact role-specific states and RID.",
      "Check cmd key absent, launcher argv and finite_env equal approved fields; script pin current; timeout120 and original alarm retained.",
      "Evidence directory and both outerstream paths absent. Implementation parent exists; no evidence creation.",
      "ROOT fully reviews literal metadata source and approved_transport.cmd before reserving this one new metadata slot."
    ],
    "steps": [
      "Create only R189 implementation directory; exclusive-save full before bytes for gate, ROOTledger, activation; verify archived SHA matches pinned before. Preserve author view unchanged.",
      "Construct proposed gate by adding single transport.cmd. Verify deleting only this added key restores original JSON equality.",
      "Compute complete proposed gate bytes/fullSHA. Derive ledger/activation copies with ONLY two allowed gate-pin replacements. Verify substituting original pin restores each original JSON equality. Assert RID and all counts/states unchanged.",
      "Before each mutation compare current file bytes with captured originals; fail closed on concurrent change, not merge/rebase. Write only approved three metadata files; no source or original evidence writes.",
      "Read back three outputs and author view; verify exact expected bytes/hash, role states, all282fixed inputs and absence again. Record full before/after pins and allowed JSON delta; do not claim prepare execution.",
      "Write exclusive transport-update.json and step-report.json/md. Immediately store actual complete tool object, preserve independent streams honestly; short stdout below1500chars only path/pin/count summary, never parse truncation prefix.",
      "Any failure/partial write: preserve actual state and stop for new Astra. Never rollback/retry or reset original reservation."
    ],
    "outputs": [
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/before-script-gate.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/before-root-command-ledger.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/before-root-activation.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/transport-update.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/actual-tool-return.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/step-report.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/implementation/step-report.md"
    ]
  },
  "metadata_gate_files": [
    "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/root-activation.json",
    "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/input-check.json",
    "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round189-p6-t1-prepare-transport-command-shape-20261014/command-ledger.json"
  ],
  "budgets": {
    "new_metadata_actions": 1,
    "new_product_commands": 0,
    "new_pytest_commands": 0,
    "new_static_commands": 0,
    "new_Git_commands": 0,
    "original_reader_retries": 0,
    "R182_prepare_red": {
      "root_used": 1,
      "root_remaining": 0,
      "root_state": "RESERVED_BY_ROOT",
      "author_used": 0,
      "author_remaining": 1,
      "author_state": "HELD",
      "reservation_id": "r182-prepare-red-root-20261014-after-R187-R188-exact-source-gate",
      "actual_started": false
    },
    "R182_other_five": "HELD0/1",
    "R179_remaining_four": "HELD",
    "R158": "3spent12HELD",
    "R175": "threeSPENT",
    "R188": "two metadata actions SPENT1/0; no reset"
  },
  "acceptance": {
    "metadata_only": true,
    "requires": "Actual exact additive transport field and gate-pin continuity, old failure preserved. Does not certify prepare_red or any test.",
    "resume": "ROOT explicit dispatch same Sol original reserved prepare_red once after recovery; its own actual evidence/author consumption must be recorded under R182.",
    "planned_green_union": 51,
    "passes_claimed": false,
    "T1": false,
    "T12": false,
    "native": false,
    "formal": false
  },
  "stop": "Any new mismatch, downstream field assumption or source change outside stated metadata delta requires next genuine Astra. No broadened consumer adaptation."
}
```

