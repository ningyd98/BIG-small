# R188 — 辅助测试末尾字节范围恢复计划

实际规划者：gpt-6-astra（/root/astra_status_plan）。状态：冻结，等待 ROOT 全文与输入门；未实施。

独立核对证实原 suffix=false 是真实范围差异。原12164B归档末尾两个 LF，当前12497B末尾一个 LF；原 prefix 完全相等，原 suffix == current suffix + 单个 LF。原生补丁只有 helper 三字段修改，没有 EOF hunk。工具内部是否规范化结尾只能列假设，不能改写原 false 报告。

唯一源码恢复：同一 Sol 在精确 SHA 守卫后补回一个 0x0a。预期12498B，SHA256 cdcf814b8072fc11995f4455c78fdc39219090e87813c89594d41f5b9c70f5ae（尚未实际写入）。不修改 helper 语义、节点、断言、夹具、产品或任何脚本。

14个直接输入已读取哈希，R182原255输入全部匹配；角色6槽各0/1且保持 HELD。原 R187 元数据进程退出0只证明读写完成，不能证明范围通过。规划读取938dbc显示截断只保留可见完整字节结论；532242输出独立短摘要完整，未解析截断文本。

ROOT先审两段标准库源码和完整 argv，再允许一次 guarded byte restoration（Sol，60秒）与一次独立 suffix proof（ROOT，60秒）。新证明比较 current == saved12497 + LF，同时以旧12164归档证明 helper外prefix/suffix完整相等；所有固定脚本、255原pin与角色账本保持。原工具/比较不重放。两个动作均不执行任何产品、测试、AST、静态或Git。

以下 JSON 是完整执行合同，包含全路径输入、SHA、前置、输出与失败停止规则；MD与JSON须一致。

```json
{
  "schema_version": 1,
  "round": "R188",
  "date": "2026-10-14",
  "actual_author": "/root/astra_status_plan",
  "author_model": "gpt-6-astra",
  "status": "FROZEN_PENDING_ROOT_INPUT_AND_SOURCE_GATE",
  "issue": {
    "classification": "CONFIRMED_ONE_BYTE_OUTSIDE_HELPER_SOURCE_DIFFERENCE",
    "original_failure": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/original-finding.json",
    "finding": "R187 helper edit removed one final LF outside authorized helper; suffix=false is valid and must remain in historical report.",
    "runtime_failure": false,
    "cause": {
      "proven": "The original comparison correctly reported a real out-of-helper final byte loss.",
      "hypothesis": "Native patch transport may normalize terminal blank lines; only supplied patch and observed bytes are available, not internal patch engine causality."
    }
  },
  "inputs": [
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/initial-finding.json",
      "bytes": 1620,
      "sha256": "618d4e74bab32b0eab68e1f2c9eaa9f00fe66b0efaea5c8b192d57858b929f5d",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/original-finding.json",
      "bytes": 9541,
      "sha256": "a97bc0bda71f3d33948accba2c88eb9164505d80c7b9d72f4129d411a1b46375",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round187-p6-t1-auxiliary-case-evidence-labels-20261014/plan.json",
      "bytes": 11266,
      "sha256": "3c53531718c656ba3e29c8f23ac8cba5fd14aa6744d7cf328e27a737677e0949",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round187-p6-t1-auxiliary-case-evidence-labels-20261014/limited.diff",
      "bytes": 1539,
      "sha256": "3031efd16cee95cd3d3e3137816eb27ffabd110e8cd2b12de4a0619d46625879",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round187-p6-t1-auxiliary-case-evidence-labels-20261014/change-report.json",
      "bytes": 1064,
      "sha256": "2ad49a0d75da7c077225393f9dfff28251f4327c8c0346ecc33bbd53e05d3a35",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round187-p6-t1-auxiliary-case-evidence-labels-20261014/original-static-finding.json",
      "bytes": 16792,
      "sha256": "8da9d2197c86dab7cae439b52e5c29c1b8ee3b490a851750e6fcb356aeaada57",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round185-p6-t1-sol-compaction-transport-20261014/root-activation.json",
      "bytes": 83497,
      "sha256": "1a16f0a8188d5fdcaaf14f0fb1fe1a8eedd98cb8b5cdc23757f8debe3c73b676",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_projection_closure.py",
      "bytes": 12497,
      "sha256": "15b4c86c159c5e05e662ddee6178fbf7e89ef92474e0bc7a2bdaaa3c0f2ba7a9",
      "role": "authorized_one_byte_restoration_before"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/prepare-evidence.py",
      "bytes": 13233,
      "sha256": "77cb39339ff2f7aa5d4293174d0fbefb284e9554f16bfd0049c7856516b8e852",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/run-command.py",
      "bytes": 14806,
      "sha256": "6dc5ecae7d14fa8d5119b999064f604ca5f0fe5f4c0e6eed6963f28f84de054e",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/command-ledger.json",
      "bytes": 12227,
      "sha256": "765c2d33144b9d46e0181e1a54b5db0367c25e218d979759f12486888fc47060",
      "role": "role_snapshot_unchanged_during_R188"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/root-command-ledger.json",
      "bytes": 12595,
      "sha256": "316934c707f8cc4bf248a385b90fd5e4564479bb3df341ee46b7455f3fc6a9a3",
      "role": "role_snapshot_unchanged_during_R188"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/plan.json",
      "bytes": 136098,
      "sha256": "82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d",
      "role": "fixed"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/implementation/root-settlement.py",
      "bytes": 20629,
      "sha256": "20a365502526256d38039bbcef061c9d6f7b9b522935aafa45f4cfab656b6e9a",
      "role": "fixed"
    }
  ],
  "transitive_inputs": {
    "manifest": {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/plan.json",
      "bytes": 136098,
      "sha256": "82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d"
    },
    "field": "inputs",
    "count": 255,
    "actual_matches": 255,
    "fail_closed": true,
    "meaning": "All original product/protected/history inputs remain fixed; no source-content reread required, bytes/hash only."
  },
  "scope": {
    "sole_author": "/root/p6_stage_b_sol",
    "implementation_model": "gpt-6.1-sol",
    "owned_path": "/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_projection_closure.py",
    "allowed_delta": "Append exactly one byte 0x0a to the precisely pinned current bytes. No other source edit.",
    "forbidden": [
      "helper field changes",
      "node/decorator/assertion/mutation/fixture changes",
      "any product or runner edit",
      "rewrite R187 limited.diff/change-report or R188 original evidence",
      "normalize whole file or repeat native patch",
      "product imports/AST/compile/pytest/static/probe/SQL/Git/network",
      "reset or release R182/R179 slots"
    ]
  },
  "before_preservation": {
    "original_auxiliary_archive": {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round185-p6-t1-sol-compaction-transport-20261014/root-activation.json",
      "bytes": 83497,
      "sha256": "1a16f0a8188d5fdcaaf14f0fb1fe1a8eedd98cb8b5cdc23757f8debe3c73b676"
    },
    "field": "before_auxiliary.base64",
    "decoded_bytes": 12164,
    "decoded_sha256": "80667bd840499fdb2c5163ba958a5d1bc20551fef70206df3dbe45ffd0c12e91",
    "new_before_archive": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/before-restoration.py",
    "new_archive_creation": "exclusive; retain exact12497 current bytes"
  },
  "expected_after": {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_projection_closure.py",
    "bytes": 12498,
    "sha256": "cdcf814b8072fc11995f4455c78fdc39219090e87813c89594d41f5b9c70f5ae",
    "actual": false
  },
  "preconditions": [
    "ROOT fully reads this plan, original supplied patch, raw comparison, exact current helper and author restoration/proof source before release.",
    "Match14 direct pins and255 manifest records; distinguish historical12164 original from current12497 and planned12498. Neither mismatch may be silently rebased.",
    "R182 author6HELD0/1 and ROOT6HELD_PENDING_ROOT_GATE0/1 unchanged. OriginalR179 fourHELD, parentR1583spent12HELD and R175threeSPENT unchanged.",
    "Verify original archive decode, helper boundaries, current single final LF, original double LF, prefix equality, suffix+LF equality before any write.",
    "Exclusive new output paths absent; no product execution."
  ],
  "actions": [
    {
      "id": "byte_restoration",
      "owner": "sole Sol",
      "authorized": 1,
      "used": 0,
      "remaining": 1,
      "retries": 0,
      "timeout_seconds": 60,
      "interpreter": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
      "argv": [
        "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
        "-c",
        "<ROOT-fulltext-reviewed restoration source implementing this exact contract>"
      ],
      "cwd": "/home/ningyd/文档/ChatGPT/BIGsmall",
      "finite_env": {
        "PATH": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1"
      },
      "contract": [
        "Stdlib only pathlib/hashlib/json/base64; no AST/import product/subprocess.",
        "Read fixed before/current/pins, require exact before12497/SHA15b4... and compute candidate=current+b'\\n'; require exact planned after12498/SHAcdcf... before write.",
        "Create implementation directory then exclusive before-restoration.py and invocation record. Do not write historical files.",
        "Use target.open('r+b'); re-read and compare exact current bytes through same handle immediately before seek(0,2) and write(b'\\n'); assert write return1. No general text rewrite/strip/rstrip or patch retry.",
        "Readback target exact expected after and archive bytes. Save restoration.json exclusive; tool result immediately store; output only paths/pins/counts under1500chars. Any failure stops; no rollback/retry."
      ],
      "outputs": [
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/before-restoration.py",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/restoration-invocation.json",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/restoration.json",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/restoration-tool-result.json"
      ]
    },
    {
      "id": "independent_suffix_proof",
      "owner": "ROOT",
      "authorized": 1,
      "used": 0,
      "remaining": 1,
      "retries": 0,
      "timeout_seconds": 60,
      "interpreter": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
      "argv": [
        "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python",
        "-c",
        "<ROOT-fulltext-reviewed independent proof source implementing this exact contract>"
      ],
      "cwd": "/home/ningyd/文档/ChatGPT/BIGsmall",
      "finite_env": {
        "PATH": "/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1"
      },
      "contract": [
        "New independent byte/text/hash proof; never replay original R187 reader or overwrite its reports.",
        "Verify exact current==new_before_archive+b'\\n' and expected12498/SHAcdcf; current helper bytes identical to12497 archive helper.",
        "Independently decode original12164 archive, split at unique def _r182_record( and first following double-newline @pytest.mark.parametrize boundary. Compare original/current entire prefix and entire suffix byte-for-byte; both must be true. Signature unchanged; full remaining test suffix implies all nodes/assertions/fixtures unchanged.",
        "Verify14 fixed pins with ONLY target expected-after substitution, plus255 original manifest records. All original two author scripts/ROOTsettler/roles/raw/golden/protected unchanged. Do not accept new current baseline for mismatches.",
        "Write new scope-proof.json with actual comparisons, original false report link and no-test claim; write limited.diff for12497→12498, plus new implementation step-report.json/md. All exclusive. Capture actual full tool return immediately; independent streams null if unavailable, do not invent.",
        "No extra command/helper execution. stdout summary under1500chars. Any false/unknown causes STOP and new Astra, not weakening predicate."
      ],
      "outputs": [
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/scope-proof.json",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/limited.diff",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/proof-tool-result.json",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/step-report.json",
        "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/implementation/step-report.md"
      ]
    }
  ],
  "metadata_authority": {
    "allowed_root_files": [
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/root-activation.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/input-check.json",
      "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round188-p6-t1-auxiliary-helper-suffix-proof-20261014/command-ledger.json"
    ],
    "source_gate": "ROOT may preserve reviewed literal -c source/exact argv and hashes in activation before each action. Native structured saves of records are not additional validation commands.",
    "role_updates": "Only R188 reservation/consumption allowed; original ledgers immutable during this recovery."
  },
  "budgets": {
    "new_metadata_actions": 2,
    "new_product_commands": 0,
    "new_test_commands": 0,
    "new_static_commands": 0,
    "new_git_commands": 0,
    "old_budgets_reset": false,
    "R182_six": "HELD0/1 throughout",
    "R179_remaining_four": "HELD",
    "original_comparison_replay": 0,
    "native_patch_retry": 0
  },
  "acceptance": {
    "scope_recovery_only": true,
    "requires": "Actual one-byte restoration and independent exact proof; preserves helper semantics and original false history.",
    "then": "ROOT may continue normal R182 source/script gate under original authority, no automatic RED release.",
    "planned_green_union": 51,
    "actual_pass_claim": false,
    "T1_complete": false,
    "T12_complete": false,
    "native": false,
    "formal": false
  },
  "stop_rules": [
    "Any difference beyond exactly one final LF, guard mismatch, unexpected output existence, write/proof failure or expanded consumer need stops affected work for actual Astra next plan. No silent cleanup, replay or budget reset."
  ]
}
```

