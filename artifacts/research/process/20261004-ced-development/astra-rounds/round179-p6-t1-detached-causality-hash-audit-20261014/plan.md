# R179 Detached causality and hash audit — implementation plan

> **For agentic workers:** implement only after ROOT activation and exact source/runner gate. Use the existing sole Sol author; this Astra planner performs no implementation. Checkboxes below are mandatory. Canonical machine contract: [plan.json](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/plan.json).

**Actual planner:** gpt-6-astra, /root/astra_status_plan, 2026-10-14.

**Goal:** close the seven source-review findings in T1 detached codecs without creating runtime authority or consuming old command budgets.

**Architecture:** pure typed data validation and deterministic history replay; canonical local hashes are separate from unchanged legacy hashes. Actual private issuers remain protected. The original 15 tags, six outer fields, exact body fields and four history fields remain unchanged.

**Tech stack:** existing Python codecs and pytest; planning and evidence checks use .venv stdlib only.

**Spec:** pinned R158 T1; original R175 review and R179 original-review-finding. The review is source-only Needs fixes, not an observed negative test run. 235 current source/protection fingerprints independently match (24 owned + 211 protected). Full SHA/bytes and protected regions are in [input-observation.json](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/input-observation.json).

## Global constraints

- Only these three files may change:
  - /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py
  - /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py
  - /home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py
- Shared codec changes are detached validation/projections/replay only. In visual_verification.py only two local hash methods and their pure shared call may change; every legacy method remains byte-identical.
- Test changes: _b_local_cases only for coherent canonical fixture hashes/origins, and appended _r179_* helpers/31 exact new nodes. Preserve A80556 bytes, all seven T1 bodies/decorators, R175 _b_legacy_sources resource wrapper and every other pre-existing definition.
- Other21 owned,211protected,16-tag golden and old raw/review/history are immutable. R173 getter types are unchanged and receive direct test coverage. No T2/T3/runtime/P5/private writer edits.
- Parent R158 remains3 spent/12HELD, R175 three spent. R179 grants six fresh slots, not retries. No Git/network/native/physical/formal promotion.
- No AST/import/compile/probe outside exact approved pytest/Ruff child commands. Pure metadata check uses text/hash/JSON/tokenize only. No broad Any, ignore, noqa or suppressed checking.

## Independent disposition

- **I1:** Confirmed; close through deterministic detached definition→initial state→request→next state replay and joins, not merely mutually equal arbitrary digests.
- **I2:** Confirmed; exact local tag always selects local canonical content hash; legacy tag always keeps exact legacy audit hash. Diagnostics may never switch algorithms.
- **I3:** Confirmed; recompute both labels with precise request-tag dispatch; define semantic projection below and preserve full-byte input_hash separately.
- **I4:** Confirmed; carry original_time through nested validation, compare exact original and verification/recovery references before counters/CAS checks.
- **I5:** Confirmed missing necessary observable lower bound, not proof of issuance. Implement only OC1-compatible same-domain upper-current >= source-lower; preserve overlap and hard/age upper semantics.
- **M1:** Confirmed null bypass; if exact tag FIELDS contains scope require exact expected string unconditionally.
- **M2:** Coverage gap only; direct typed getters/accessors added to tests; no pretense that the existing code failed at runtime.

Accepted declined findings remain: deliberate T1 runtime STOP; caller-created UNKNOWN records are detached; UTC legacy accessor separation; truthful partial-init denominator. Nested diagnostic/renewal hash invariance is now explicitly specified below, not silently declined.

## Canonical contract

### Hashes and tag dispatch

**local_envelope.** Recognize only exact schema tag and complete six-field validated envelope. P(envelope)={schema_version,payload:P(payload),original_time:original_time}. Exclude only its decision, transaction, diagnostics. Recurse only through exact recognized local envelope nodes. Other dictionaries, including legacy tags, semantic model timestamps, source hashes, counters and policies, retain every key/value; never blanket-drop keys named utc/time/hash.

**publication.** publication_hash = H({schema_version:'visual.owner.publication.local.v1', payload:P(body with ONLY publication_hash removed), original_time:original}). The hash covers all substantive body fields, nested original references/pools/checkpoint/source/operation data. Validate nested local selfhashes before using their projections. An original legacy publication embedded under its exact v1 tag retains its complete legacy content-hash algorithm including actual timestamps.

**route_input.** input_hash=H(exact complete request bytes parsed as JSON), including event_key/diagnostics/decision if present; it is intentionally not renewal-invariant. For local semantic_hash use H({schema_version:'visual.verification.route-input.local.v1', payload:P(request.payload with ONLY top event_key removed), original_time:request.original_time}). Local source_key retains exact existing local source-key.v1 recipe lines734–748: original_time_hash, original_plan_hash, task_id,step_id,attempt,phase,frame_id/checksum,plan_version,command_seq,requirements_hash. Decoder and methods share these same pure recipes.

**legacy_route.** Exact legacy route-input.v1/v2 uses existing preserved source_key recipe lines493–513 and semantic_hash field selection lines515–530 (conditional grounding_receipt). Invoke/reuse pure computations without invoking current-UTC producer gates or inventing a valid legacy instance. Do not change any legacy bytes/algorithms.

**invariance.** Only local diagnostics and current renewal decision/transaction are non-semantic; original acquisition/task references are always included. Nested legacy audit payloads are immutable historical bytes, not new local diagnostics. Local publication selfhash follows P, so nested renewal alone is stable. Substantive budget/claim/action/source/epoch/original changes must change hash or fail. Full envelope.digest and input_hash remain byte-sensitive.


**Canonical JSON:** Use current _canonical: json.dumps(sort_keys=True,separators=(',', ':'),allow_nan=False), UTF-8, existing ensure_ascii default. SHA256 lower hex. Type guards precede hashes.

**Nested pools:** Every nested local verification/retry envelope in local publication/route must have EXACT original_time equal to enclosing original; verification state.original_budget_reference == enclosing verification_reference; LocalRetryBudgetRecord.original_recovery_reference derives enclosing recovery_reference, never a new payload field. Route request/local publication/before/after/produced local envelopes all bind same original, task/source/fence/epoch; retain existing exact revision+1/no-refund/frozen-limit checks. Legacy nested records are exact-tag archival sources under unchanged hash/UTC rules and cannot satisfy a new local history's private permission.

### Four-field history replay

**classification.** Empty history means definition-derived revision-zero local initial state. A nonempty history is homogeneous: exact preserved legacy archival shapes OR four-field local events. Reject mixed/archive-to-local implicit promotion. Legacy archival rows retain original UTC and algorithms, are explicitly audit-only and never gain a VALID/current/private status because they parse.

**state_projection.** S(tag,body,original)={schema_version:tag,payload:P(body with ONLY history removed),original_time:original}. h_state=H(S). Excluding the history itself avoids request/CAS/result circularity; retain revision and all record semantic fields. Never exclude counters, pending/claims, definition, observation/draft/decision content or exhausted flags. Exact legacy definitions can remain nested audit sources; their source hash uses their preserved canonical codec.

**initial.** Derive complete bootstrap/supervision initial record from its frozen definition and original references, not from caller-supplied final record. Bootstrap state has frozen limits/reference and untouched initial allowances, revision0/no history/no pending/no observation/draft/no claimed capture/no terminal/adoption. Supervision initial counters/cursors/wait=0, claims empty, limits from original hard duration and frozen cadence. Validate definition/source/role/task identity using actual source contracts. Local versus legacy definition dispatch must be explicit; an unsupported nested original format is rejected as unsupported, never silently normalized with fake UTC.

**operation.** For each event require exact matching local bootstrap transition/promotion or supervision transition tag; original identical to enclosing record. request.expected_record_hash == current h_state; supervision expected_revision == current revision; definition/task/bootstrap identifiers exact. operation_sha256=H({schema_version:'visual.local-history-operation.v1',request:P(request)}), with event_key and expected pre-hash INCLUDED. operation_id=request.event_key. Both decision and transaction equal this operation digest/id; transaction.event_key equals request.event_key and event_kind equals exact request.schema_version; expected_event_revision=current revision,event_revision=current revision+1.

**replay.** Pure typed data replay of original phase/claim/counter/CAS semantics only, no private runtime call or fake UTC. Apply each exact kind to the derived previous state: reserve only unclaimed/pending-free effects, bind deterministic claims to original definition/prestate/kind or cursor, increment/debit exact counters, complete only matching pending claim/step/context, no refund/refill/replay, terminal stops further positive transitions. Bootstrap source contracts _derive635–771/_promote; supervision _start/_apply448 and611–800 are semantic references, not functions to execute with invented now. Replace only temporal authorization with provided typed detached decision/reference checks; do not synthesize walltime or grant permission. Promotion retains exact original/contract/role/claim source. If a phase cannot be deterministically checked from existing four-field contract, STOP rather than adding fields, rejecting all legal phases, or silently postponing that branch. Local claimed effects must not invent claimed_at/reserved_at/current UTC timestamps. Pure local pending/claim data is derived deterministically from the enclosing local tag, request IDs and source models, using existing semantic fields/claim containers; keep a private replay accumulator for request-relative phase evidence if necessary rather than adding envelope/body/history fields. Existing archival claim timestamp fields remain untouched only in archive histories. Positive branches must not be rejected merely because the live reducer normally requires a current issuer.

**outcome.** Compute post-state from request; resulting_record_hash and transaction.event_record_hash must equal computed h_state. Bind successor pre-hash to this result. After final event, every enclosing semantic field excluding history must equal replay state and enclosing decision/transaction must equal last event evidence. Reject duplicate event IDs/reordered or skipped revisions, altered final state or counters even when all arbitrary digests were recomputed.

**authority.** COMPLETE requires existing two receipt hashes and matching phase; UNKNOWN descriptive histories remain descriptive and must not produce runtime authorization. VALID fields are self-described local consistency only, never proof of issuer. Two positive multistep histories exercise genuine decoders, independent expected data replay and unchanged real permission registries.


**visual.bootstrap.record.local.v1.** Definition accepts exact visual.bootstrap.definition.v1 archival source or exact visual.bootstrap.definition.local.v1 only through its typed local decoder; complete policy/role/episode/source relation is retained. Four-field local history requests are only bootstrap.transition.local.v1 or bootstrap.promotion.local.v1; their exact tags select local replay. Request original must match enclosing original. Pure archival UTC history uses its existing exact old shapes only.

**visual.supervision.record.local.v1.** Definition accepts exact supervision.definition.v1 archival source or exact supervision.definition.local.v1 through typed local decoding. Four-field local history accepts only supervision.transition.local.v1. No bootstrap request in supervision or converse. The replay definition/hash used in every request must match that exact definition, not a mode guessed from timestamps.

**local_definition_dependencies.** Local supervision definition/transition/route-input may embed the exact legacy original/publication accepted by their present audit contract, or a supported exact local publication envelope with exact enclosing original. Do not route local publication through legacy UTC constructors. A local original in a field whose existing typed adapter only supports exact legacy original is explicitly unsupported and rejected; R179 does not expand all nested domain adapters or fabricate a legacy object.

**budgets.** Exact local nested pools retain full original; exact legacy pools stay archival using unchanged algorithms. Mixed local/legacy pools may exist in a local publication only under each exact tag's audited branch, and must retain task/source consistency. A local history cannot treat a legacy pool's UTC timestamp as a new D origin. Unknown tags and raw semantic dictionaries pretending to be local envelopes fail closed.


### Causal lower bounds

Before any numeric relation require exact domain identity. For self-described VALID app_current require upper_ns >= every required reference hard origin (deadline_ns-budget_ns) and every age.lower_ns; retain own-age event/budget linkage for non-bootstrap references. Lease current.upper >= acquisition.lower and current segment.lower; current segment.upper >= original acquisition.lower. Preserve original acquisition bytes, separate renewable segment, and current upper<segment deadline/HARD_OPEN plus AGE_CLOSED inclusive bounds. Do NOT require current.lower>=event.upper or compare domains. Overlap/equality at lower bound is allowed. Hidden mark-point/token identity cannot be reconstructed and is never certified by this decoder.

The source basis is actual operational_time_v1.age_bounds354–373: only current.upper < event.lower proves observable impossible ordering; hidden mark-point/token checks cannot be reconstructed from a JSON history. P5 hard origin=deadline−budget and AGE_CLOSED brackets retain same-domain sources. Broker receipt preserves seven exact fields and separate current segment.

### Fixtures

Update _b_local_cases only to generate the explicitly new local publication hash and coherently bind new-local nested origins/hash fields. Do not carry old publication_hash under new tag; do not choose algorithm via diagnostic UTC. Old legacy source objects and goldens remain unchanged. Appended _r179_* builders label caller-created/descriptive evidence and use independent expected canonical calculations; no registry injection, fake verdict, monkeypatched authority or direct SQL.

## Task 1 — freeze test-first preparation and run RED

- [ ] ROOT read full plan, issue evidence, all script text, exact fixtures and relevant SHA inputs; archive current before bytes without altering historical candidates.
- [ ] Sole Sol append exact cases and runner. No implementation before RED. Keep original seven bodies unchanged.
- [ ] Run **prepare_red** once and inspect its complete source/protection/raw manifest. ROOT gates exact RED19 and per-mutation baseline decode.
- [ ] Run **RED19** once. Expected19 assertion failures/exit1, no errors/skips/fixture/API failure. Preserve every raw failure. If an already-existing guard rejects a case, report it honestly; never manufacture a RED.
- [ ] ROOT reads every failure and accepts only the named causal/hash gap. No authorized repair follows a different unexpected cause.

## Task 2 — implement bounded strictness and freeze

- [ ] Apply only the two product scopes plus permitted fixture bookkeeping. Preserve RED test bodies/IDs and compare all unowned definitions/regions.
- [ ] ROOT reads full new shared replay/projection, local hash methods, fixtures and all exact delta. If four-field replay cannot express a required legal phase, STOP for a new plan; no reject-all workaround.
- [ ] Run **prepare_green** once. Archive/red-reference old13 reports if needed; produce new R179 candidate, scope proof and fixture map rather than overwriting historical reports.
- [ ] Run one narrow **Ruff F821/F822/F823** check. It does not claim full type/format/lint acceptance; parent final static gates stay held.

## Task 3 — one GREEN38, resources and independent review

- [ ] ROOT rechecks current candidate/script pins and exact command; run **GREEN38** once (31 new + original7), expected38PASS/0FAIL/ERROR/SKIP.
- [ ] Preserve independent stdout/stderr, actual exit and JUnit. Resource observer records actual calls/init/close/thread identity/restoration; no assumed4-per-node denominator. No-helper nodes have no invented sidecar. Unobserved worker/broker/OS counters stay null.
- [ ] ROOT **root_settlement** once verifies raw/source/golden/resources/role budgets. Retain old failed T1 and both historical successful recovery runs separately.
- [ ] Resume same original reviewer's remaining3 batches plus at most5 explicitly separate R179 fix-review batches, ≤600 lines each. No duplicate seat or reset of original9 used. All findings and declined issues receive explicit disposition.
- [ ] T1 remains pending until actual tests/resource checks and independent review pass and ROOT makes the bounded decision. T2/T3 remainHELD until then; B9/P6/T12/native/actual/formal/Git are not accepted by this plan.

## Exact new node matrix

- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[request_event] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[operation] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[request_kind] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[result_hash] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[cas_prestate] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[transaction_event] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_history_binding_rejects[final_state] — I1: Each uses a complete structurally valid four-field new history with one exact causal/state join changed; no interface error can count as RED.
- tests/test_operational_runtime_closure.py::test_r179_publication_hash_rejects[without_utc] — I2: A valid local publication independently hashed under the local contract is changed without recomputing its hash. The without_utc variant is the existing accepting branch targeted in RED; all three must reject in GREEN.
- tests/test_operational_runtime_closure.py::test_r179_publication_hash_rejects[with_utc] — I2: A valid local publication independently hashed under the local contract is changed without recomputing its hash. The without_utc variant is the existing accepting branch targeted in RED; all three must reject in GREEN.
- tests/test_operational_runtime_closure.py::test_r179_publication_hash_rejects[partial_utc] — I2: A valid local publication independently hashed under the local contract is changed without recomputing its hash. The without_utc variant is the existing accepting branch targeted in RED; all three must reject in GREEN.
- tests/test_operational_runtime_closure.py::test_r179_route_labels_recomputed[semantic_hash] — I3: Change one well-formed digest after retaining valid exact request, input_hash and nested pools.
- tests/test_operational_runtime_closure.py::test_r179_route_labels_recomputed[source_key] — I3: Change one well-formed digest after retaining valid exact request, input_hash and nested pools.
- tests/test_operational_runtime_closure.py::test_r179_nested_original_rejects[publication_verification] — I4: Replace one individually valid nested local original with another same-task original; recompute all unrelated content hashes so only the enclosing original join is broken.
- tests/test_operational_runtime_closure.py::test_r179_nested_original_rejects[publication_retry] — I4: Replace one individually valid nested local original with another same-task original; recompute all unrelated content hashes so only the enclosing original join is broken.
- tests/test_operational_runtime_closure.py::test_r179_nested_original_rejects[route_before] — I4: Replace one individually valid nested local original with another same-task original; recompute all unrelated content hashes so only the enclosing original join is broken.
- tests/test_operational_runtime_closure.py::test_r179_nested_original_rejects[route_after] — I4: Replace one individually valid nested local original with another same-task original; recompute all unrelated content hashes so only the enclosing original join is broken.
- tests/test_operational_runtime_closure.py::test_r179_valid_causal_lower_bound[app_hard] — I5: A self-described VALID record has current.upper less than its required same-domain source lower; every existing upper bound still passes. Self-description never claims real issuer provenance.
- tests/test_operational_runtime_closure.py::test_r179_valid_causal_lower_bound[app_age] — I5: A self-described VALID record has current.upper less than its required same-domain source lower; every existing upper bound still passes. Self-description never claims real issuer provenance.
- tests/test_operational_runtime_closure.py::test_r179_valid_causal_lower_bound[lease_acquisition] — I5: A self-described VALID record has current.upper less than its required same-domain source lower; every existing upper bound still passes. Self-description never claims real issuer provenance.
- tests/test_operational_runtime_closure.py::test_r179_valid_causal_lower_bound[lease_segment] — I5: A self-described VALID record has current.upper less than its required same-domain source lower; every existing upper bound still passes. Self-description never claims real issuer provenance.
- tests/test_operational_runtime_closure.py::test_r179_scope_null_rejected — M1: Set present required scope to null; loop exact scope-bearing tags, each baseline otherwise valid.
- tests/test_operational_runtime_closure.py::test_r179_history_replay_positive[bootstrap] — I1: At least two legal sequential requests from definition-derived revision-zero state, four fields per history event, exact final state/hash and registry denial. Bootstrap reserve+complete capture, supervision reserve+complete wait.
- tests/test_operational_runtime_closure.py::test_r179_history_replay_positive[supervision] — I1: At least two legal sequential requests from definition-derived revision-zero state, four fields per history event, exact final state/hash and registry denial. Bootstrap reserve+complete capture, supervision reserve+complete wait.
- tests/test_operational_runtime_closure.py::test_r179_semantic_projection_invariant[outer_diagnostics] — I3: Semantic/source/local publication hashes stable only for permitted diagnostic or current-decision changes; full input/envelope hashes reflect changed bytes. A paired substantive budget/source mutation must change identity or reject.
- tests/test_operational_runtime_closure.py::test_r179_semantic_projection_invariant[nested_diagnostics] — I3: Semantic/source/local publication hashes stable only for permitted diagnostic or current-decision changes; full input/envelope hashes reflect changed bytes. A paired substantive budget/source mutation must change identity or reject.
- tests/test_operational_runtime_closure.py::test_r179_semantic_projection_invariant[nested_renewal] — I3: Semantic/source/local publication hashes stable only for permitted diagnostic or current-decision changes; full input/envelope hashes reflect changed bytes. A paired substantive budget/source mutation must change identity or reject.
- tests/test_operational_runtime_closure.py::test_r179_causal_overlap_positive — I5: Same-domain overlapping brackets including current.lower < event.upper remain accepted when current.upper >= event.lower and upper expiry passes; decoded evidence still detached.
- tests/test_operational_runtime_closure.py::test_r179_cross_domain_causality_rejected — I5: Equal numeric endpoints in a different domain do not permit a comparison or local validity.
- tests/test_operational_runtime_closure.py::test_r179_publication_history_getters[local] — M2: Direct concrete calls to both history getters and all LocalRetryBudgetRecord accessors; preserved legacy types, local old-getter explicit denial, unsupported tags, detached immutability and unchanged registries.
- tests/test_operational_runtime_closure.py::test_r179_publication_history_getters[legacy] — M2: Direct concrete calls to both history getters and all LocalRetryBudgetRecord accessors; preserved legacy types, local old-getter explicit denial, unsupported tags, detached immutability and unchanged registries.
- tests/test_operational_runtime_closure.py::test_r179_local_publication_positive — I2/I4: Real domain codec accepts complete correctly hashed local publication with matching local verification/retry envelopes, both with and without diagnostic UTC; no permission or NEW_COMMIT.

RED selects the19 explicitly listed in JSON: history7 + publication without_utc1 + route2 + nested4 + causal4 + scope1. The other12 cover publication diagnostics variants, multistep replay, semantic invariance, overlap/cross-domain, concrete getters and valid publication. GREEN executes all31 then exact original7; total38. No A40 rerun.

**RED contract:** Before each mutation decoder must accept the complete seed on current source; assert exactly the intended rejection (ValueError with causal/hash category), not broad Exception/AttributeError/NameError. RED uses current accepted four-field history/diagnostics-empty local publication/route seeds, with all unrelated checks valid. No artificially missing API or deliberately failing placeholder. ROOT proves each of19 failures corresponds to its named join; pre-existing rejection is not new RED evidence and must be reported, not forced to fail. Pin the 19 exact test bodies and parameters before RED; green may not weaken them. A seed constructed under the new publication algorithm can be accepted by the current diagnostics-empty branch, so the negative must mutate only its target label after baseline decode. Positive new replay/getter coverage belongs to GREEN and is not substituted by prior seven-pass evidence.

## Finite commands and capture

All use cwd /home/ningyd/文档/ChatGPT/BIGsmall and its exact .venv/bin/python. No inherited secret/environment forwarding; exact finite env is in JSON. All output directories and tmp roots must be absent before use. Each slot startsHELD, used0/rem1; reserve before process creation; timeout does not restore allowance.

| Slot | Timeout | Exact invocation / result |
|---|---:|---|
| prepare_red | 120s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/implementation/prepare-evidence.py red ; One stdlib text/hash/JSON/tokenize preparation: archive current baseline and new tests/runner, verify fixed bytes and exact RED19, create immutable red input receipt. No product imports/AST or test collection. |
| red | 600s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest + exact JSON node list; 19 exact expected assertion failures: pytest exit1, no setup/import/type-interface failure, error, skip or xfail. Each mutation starts from decoder-accepted pre-mutation old-source seed. ROOT inspects every failure; a different cause stops. |
| prepare_green | 120s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/implementation/prepare-evidence.py green ; One new stdlib source delta and final candidate freeze; keep RED fixture/test snapshots. Verify region/constant/legacy/protection and test-body continuity, archive the old 13 reports if refreshing derived reports; do not overwrite historical R172-R178 outputs. |
| ruff | 120s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m ruff check --no-cache --select F821,F822,F823 /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py /home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py; One narrow undefined-name/binding static check, expected exit0. This is not full lint/type/formatter acceptance; R158 final static budgets remain held. |
| green | 600s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest + exact JSON node list; 31 new plus original7 = 38 exact nodes, one run expected exit0/38PASS/0FAIL/ERROR/SKIP; no original A40. Old seven bodies unchanged, explicitly new R179 regression allowance, not reset parent GREEN. |
| root_settlement | 120s | /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014/implementation/root-settlement.py ; ROOT one independent stdlib bytes/hash/JSON/JUnit/resource/ledger settlement after all prior gates; actual failure raw and prior results immutable; no product execution. |

The full exact argv arrays and finite env are canonical in JSON, not shell strings. Six new script/runner slots contain three product/static child invocations (RED, narrow Ruff, GREEN). No additional hidden collector, compile, import, AST, baseline or probe command is allowed. Author scripts: prepare-evidence.py and run-command.py; ROOT script: root-settlement.py. ROOT reads and pins every script before execution. All actual tool returns are stored before display; missing streams/exit stay null. Native independent child stdout/stderr are captured as bytes, never reconstructed from combined output.

## Metadata/current-history boundary

Historical original-review-finding stage_before snapshots remain historical. ROOT may archive exact before then update only planning.R179/current T1 finding and budget facts, append PHASE and R179 step reports after actual observations. No B/T12 acceptance bump. Do not require mutable phase/state/ledgers to equal their historical bytes after approved writes. Before every update compare current byte pin with immediately archived before and strict allowed-field diff. New gate pins current script; archive prior gate when it appears in earlier run input pins; no self-referential hash or broad history exception.

## Review focus and acceptance

- Every I1-I5/M1-M2 finding has separate actual assertion/positive evidence; four-field history is deterministically replayed, not hash-label equality.
- No UTC-dependent algorithm selection or blanket recursive field removal; nested original and counter/source invariance correctly bounded.
- Original definitions/hash source identity and all phase semantics remain usable; unsupported nested tags rejected explicitly, not reject-all new histories.
- Same-domain upper/lower necessary condition only; hidden issuer/order provenance not claimed; overlap positive tested.
- Typed getter tests actually invoke concrete properties, old compatibility types intact.
- 31+7 JUnit exact and per-helper observed resource sidecars; no fabricated fixed denominator or workers0 from absence.
- Prior raw and spent budgets preserved; metadata history/current mutable roles never conflated.

No product, pytest, static or Git command was executed by this planner. The saved plan is an authorization proposal pending ROOT applicability/activation, not successful repair evidence.

