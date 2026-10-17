# R203 — 精确历史世代映射的元数据 reader 修复计划

实际作者：gpt-6-astra（/root/astra_status_plan）。本轮只有计划；尚未修改或运行 reader。

已独立确认：reader 在载入最终软件接受记录的 metadata_history_added 之前就检查历史引用，遗漏 RESERVED 账本世代；实际 invocation 的 gate-before.json 另有 43 组档案关系。初始、review-release、acceptance、archived-gate 与 invocation 四档案合计 62 关系、52 个不同 original 三元组，62 份物理档案均按字节核对。固定 authority/settlement 的 243 个 pin 出现中，238 当前相符、5 经精确历史关系相符、0 未映射。这是普通只读元数据观察，不是执行第 24 批或终审通过。

只允许原同一 reviewer 修改 read-terminal-metadata.py 的档案注册、加载顺序与历史来源记录；read-settlement-text.py 保持全字节不变。先验证物理档案的完整 pin 与原世代 bytes/SHA，再允许 exact (original path, bytes, SHA256) 回退；不可 blanket historical，不可忽略错误，313 current pin 仍逐个当前核验。所有源代码、产品、测试、结算脚本、旧门、原件不动。

ROOT 完整读本计划、保存两 reader 全 before、核输入与 0/1 原预算后才允许源码修改；改后 ROOT 全文/精确 diff/SHA 门禁。零新执行槽，第 24/25 批仅沿用 R202 两个原 120 秒额度，各一次。23 已耗不重置；失败 STOP。

本轮不同步 R196 角色/STATE/PHASE；原 R202 两读结束后才按既定 archive/CAS 合同同步。当前软件 63 PASS/252 close 保留；独审仍待完整证据，T1/T12/native/formal/Git 均不晋升。

完整可执行合同与所有精确输入如下；物理档案 62 项完整 pin 位于 input-observation.json。

```json
{
  "schema_version": "astra.r203.plan.v1",
  "round": "R203",
  "status": "FROZEN_PLAN_PENDING_ROOT_APPLICABILITY_GATE",
  "actual_author": {
    "agent": "/root/astra_status_plan",
    "model": "gpt-6-astra",
    "subdelegation": false
  },
  "problem": "A draft metadata reader checks historical authority references before loading all explicit, physically preserved generation maps. It would reject legitimate RESERVED/root-role and other historical references against later current files.",
  "evidence": {
    "original_finding": {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round203-p6-t1-review-reader-historical-generation-map-20261014/original-static-review-finding.json",
      "bytes": 14510,
      "sha256": "586516d0403ce123d973ace90f1df6f6794686bda67dc44df18f9a513d42b2cb"
    },
    "runtime_failure": false,
    "original_source_return": "ROOT 0c5e4d exit 0 source read; prospective finding only",
    "planning_observation": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round203-p6-t1-review-reader-historical-generation-map-20261014/input-observation.json"
  },
  "inputs": [
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round203-p6-t1-review-reader-historical-generation-map-20261014/original-static-review-finding.json",
      "bytes": 14510,
      "sha256": "586516d0403ce123d973ace90f1df6f6794686bda67dc44df18f9a513d42b2cb"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round202-p6-t1-review-final-batch-truncated-json-20261014/plan.json",
      "bytes": 21771,
      "sha256": "1ade7bbfc56578af736b9e3764713b9e9fdf9d08c26d1483ce1fa937ed8ae618"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round202-p6-t1-review-final-batch-truncated-json-20261014/review/read-terminal-metadata.py",
      "bytes": 9485,
      "sha256": "629d3feb241f25b09bf7ac731513dae20220fa6336263972bfb5f82fecd37577"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round202-p6-t1-review-final-batch-truncated-json-20261014/review/read-settlement-text.py",
      "bytes": 1241,
      "sha256": "374fed52d716bfa530018bb7e7cbd8699a2636b3dc08b240abbb1b649522738e"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/before/manifest.json",
      "bytes": 65507,
      "sha256": "0295c8825c68314d40d88d16c82310fd365d99abb97696e6f9d9dd23c7ac3cd3"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/review/access-gate.json",
      "bytes": 85840,
      "sha256": "508005357655acfa7f199db70fd3f05dfb46e665fd7b41201598a11386b7d382"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root-final-software-evidence-acceptance-review-pending.json",
      "bytes": 5196,
      "sha256": "c2650ff5e327a401374be5273c947b0f40e842df812ab51100a46dea38724d71"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/result.json",
      "bytes": 78614,
      "sha256": "1559376bee1c46fc06b59e1146b7b9495ca2652d9efd8a7622e35d7ad1680eb6"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/settlement.json",
      "bytes": 96101,
      "sha256": "f0450796d91eefb20ba82f09a3db519ccb858fb0025906339c00dbb3bc69a04e"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/tool-return.json",
      "bytes": 84240,
      "sha256": "8c3d87760e8d61f20509265ce121209277ac6754f8f8857cdf6387c3872e2883"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/invocation.json",
      "bytes": 841449,
      "sha256": "f9ad9bb36b16f91591dc42b0934d5b0bd960a2ad6496c39c232aceb383f7cd91"
    },
    {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/gate-before.json",
      "bytes": 576957,
      "sha256": "cb7412e2963c98b8e51a6934e9ebe1e5b32df2a8a42056883e3a9a3130d9e302"
    }
  ],
  "archive_inputs_reference": {
    "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round203-p6-t1-review-reader-historical-generation-map-20261014/input-observation.json",
    "field": "physical_archive_inputs",
    "count": 62,
    "require_full_bytes_sha_match": true
  },
  "root_cause": {
    "confirmed": "archives_from currently covers initial before and review access-gate only; authority.metadata_history_added is not admitted before walk(authority). The fixed invocation gate contains another 43 exact historical pairs. R196 root ledger 25288/d8840c04cfbcf7fb57ac8459fc845f161552e5fc515f22b8dcc2bd808c462029 is physically archived but not admitted at the required point.",
    "same_cause_scope": "Resolve all generations referenced by the fixed authority and settlement using the explicit initial, acceptance, review, invocation and archived-gate maps before historical walks.",
    "independent_observation": {
      "pairs": 62,
      "unique_original_tuples": 52,
      "physical_archives": 62,
      "authority_and_settlement_current_occurrences": 238,
      "historical_occurrences": 5,
      "unmapped": 0
    },
    "non_claim": "These bounded text/hash observations do not execute the reader, approve terminal review, or alter the 63-PASS/252-close software evidence."
  },
  "scope": {
    "implementer": "same original reviewer /root/t1_fresh_astra_review, actual gpt-6-astra; no replacement seat",
    "only_source_edit": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round202-p6-t1-review-final-batch-truncated-json-20261014/review/read-terminal-metadata.py",
    "unchanged_reader": {
      "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round202-p6-t1-review-final-batch-truncated-json-20261014/review/read-settlement-text.py",
      "bytes": 1241,
      "sha256": "374fed52d716bfa530018bb7e7cbd8699a2636b3dc08b240abbb1b649522738e"
    },
    "allowed_regions": [
      "archive registration and exact tuple lookup",
      "fixed pinned authority/invocation/archived-gate preload order before historical walks",
      "audit provenance labels for historical resolution"
    ],
    "protected": "All product/test files, ROOT settlement source, original gate/ledger/result/streams/JUnit, prior review artifacts and frozen plans unchanged. All 313 review access-gate inputs retain current-byte verification; no historical fallback for that loop.",
    "root_metadata": "R203 input-check, root-activation, source-gate, step-report and before archives/diff may be saved. They do not rewrite old R202 source preparation approval. The new reader source requires a new exact pin in the R203/R202 dispatch gate, retaining the original pin and approval as history.",
    "forbidden": [
      "blanket historical allow",
      "unverified archive admission",
      "silent error removal",
      "skipping current inputs",
      "JSON parsing internal truncated tool output",
      "product/AST/import/compile/SQL/probe/test/static/Git/network execution",
      "new review seat",
      "rewriting historical snapshots or raw"
    ]
  },
  "history_contract": {
    "pin_keys": [
      "path",
      "bytes",
      "sha256"
    ],
    "original_key": "exact absolute original path plus integer byte count plus full SHA256",
    "admission": "Read the physical archive as regular non-symlink bytes, verify its exact path/bytes/SHA pin, and require original.bytes/archive.bytes and original.sha256/archive.sha256 equality. Only admit after every assertion succeeds. Failure remains fatal; never populate an accepted map from a failed check.",
    "duplicate_rule": "The same original tuple may have multiple verified archive paths if their bytes are identical. Preserve all provenance labels; reject conflicting bytes or malformed records. Different generations of one original path remain distinct keys.",
    "sources": [
      {
        "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/before/manifest.json",
        "field": "archives",
        "count": 7
      },
      {
        "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/review/access-gate.json",
        "field": "metadata_history_added",
        "count": 4
      },
      {
        "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root-final-software-evidence-acceptance-review-pending.json",
        "field": "metadata_history_added",
        "count": 4
      },
      {
        "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/gate-before.json",
        "field": "metadata_history",
        "count": 43
      },
      {
        "path": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root_settlement/invocation.json",
        "field": "before_metadata",
        "count": 4
      }
    ],
    "invocation_original_bindings": {
      "activation": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/root-activation.json",
      "author_ledger": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/command-ledger.json",
      "gate": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/script-gate.json",
      "root_ledger": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/root-command-ledger.json"
    },
    "invocation_rule": "Require exactly the four observed keys. Each record names an existing physical *-before.json archive, not the original path. Verify physical bytes against all three pin fields and base64 before applying the explicit original-role binding above. No arbitrary basename inference.",
    "gate_chain": "Check the fixed final-acceptance/result/invocation pins first. Check invocation.before_metadata.gate and its physical gate-before.json before parsing its metadata_history. Its bytes/SHA also equal the acceptance metadata_history_added script-gate generation. No traversal of unpinned arbitrary JSON files.",
    "loading_order": [
      "Read and pin the fixed top-level documents from this plan. Keep the original 313-current-input loop unchanged.",
      "Load/validate initial archives and review-release pairs.",
      "Load/validate final authority.metadata_history_added before walk(authority).",
      "Pin the result-linked invocation, verify all four physical before_metadata records/base64, then pin/parse its archived gate and validate its 43 metadata_history pairs.",
      "With all permitted mappings admitted, perform original authority and settlement recursive pin checks. Current exact match is preferred; only explicitly historical checks may resolve an exact tuple through this verified map.",
      "Record the selected current/archive resolution and provenance. Unknown/missing/changed archives, unsupported schema, or an unmapped mismatch are failures, never warning-only."
    ],
    "embedded_data": "Base64 validity alone does not create a historical exception. A physical archive with the matching tuple is required; no new archives may be manufactured from claimed hashes to pass a mismatch.",
    "applicability": "The independently observed fixed trees resolve 238 occurrences currently and 5 historically with no unmapped record. This count is evidence of map sufficiency, not permission to omit future checks or hardcode success."
  },
  "steps": [
    {
      "id": 1,
      "actor": "ROOT",
      "action": "Full-read this plan/observation and compare exact before reader/textreader plus pinned fixed roots. Preserve both complete current readers exclusively under R203/before before allowing edits; original evidence stays immutable. Confirm 24/25 HELD0/1 and 23 prior reads spent. No automatic release."
    },
    {
      "id": 2,
      "actor": "same reviewer",
      "action": "Edit only the metadata-reader resolver/preload/provenance regions above using native structured source editing. Preserve old source and exact limited diff; do not run or compile any script."
    },
    {
      "id": 3,
      "actor": "ROOT",
      "action": "Full-text review final metadata reader, normal byte/hash scope verification against archived before; textreader unchanged; verify all existing terminal/JUnit/resource/role/failure/capture checks and 313 current loop remain. Save exact final script pin and dispatch authority without altering old approvals or consuming a read."
    },
    {
      "id": 4,
      "actor": "same reviewer after ROOT release",
      "action": "Execute the original R202 batch24 and batch25 once each, with unchanged exact launcher/environment/timeouts/output contracts except new approved metadata-reader source SHA. Record separate actual returns immediately. Any unexpected failure stops; no retry."
    },
    {
      "id": 5,
      "actor": "ROOT",
      "action": "Assess real outputs and inherited R202 report/sync gates. No terminal approval from static source repair alone; remaining missing coverage must be reported honestly."
    }
  ],
  "budget": {
    "new_execution_slots": 0,
    "new_product_slots": 0,
    "new_review_batches": 0,
    "inherited_R202": {
      "batch24": {
        "used": 0,
        "remaining": 1,
        "timeout_seconds": 120
      },
      "batch25": {
        "used": 0,
        "remaining": 1,
        "timeout_seconds": 120
      },
      "prior_used": 23,
      "total_ceiling": 25
    },
    "native_source_preparation": "No executable self-test or extra verification script. Normal metadata pin/text/diff gates and native before/source/report saves only.",
    "unchanged_limits": "R202 exact argv/cwd/finite environment, SIGALRM120, no subprocess/product calls; stdout byte bounds and full audit output remain. Metadata summary <=6000 UTF-8 bytes; text reader <=600 lines and <=40000 UTF-8 bytes. Validate display size before printing, no huge raw/base64 emission."
  },
  "mutable_boundary": "This round does not update R196 roles/STATE/PHASE. They remain current for all 313 checks until the original R202 post-read archive/CAS synchronization. R203 approvals and new reader pin are separate metadata; no simultaneous current-and-historical requirement for the edited reader.",
  "stop_conditions": [
    "new cause or required source scope expansion",
    "input drift not explicitly authorized here",
    "archive tuple mismatch or unknown schema",
    "either actual inherited reader failure or truncated evidence",
    "budget exhaustion without completed coverage"
  ],
  "acceptance": {
    "metadata_repair_only": true,
    "required": "ROOT approved narrow source delta, then actual inherited R202 evidence and complete coverage; no assumed success.",
    "software_63_pass_evidence_preserved": true,
    "review_completion_pending": true,
    "T1_complete": false,
    "T12_complete": false,
    "native": false,
    "formal": false,
    "Git": false
  }
}
```

