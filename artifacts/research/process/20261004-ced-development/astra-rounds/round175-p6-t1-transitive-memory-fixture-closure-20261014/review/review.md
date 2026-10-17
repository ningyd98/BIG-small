Spec Compliance

**Needs fixes.** The task implements all fifteen exact outer/body field inventories and detached domain dispatch, but the immutable-history and semantic-hash audit contract is not yet met. The Important findings below are T1 decoding defects; none requires activating T2/T3's private runtime.

Strengths

- Shared strict JSON copying rejects nonfinite values, non-JSON/live objects and duplicate Mapping keys; exact outer/body sets are enforced ([local_temporal.py:47](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:47), [local_temporal.py:936](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:936)).
- Original acquisition is separated from renewable lease segment and joined by identity, epoch and original hash ([local_temporal.py:238](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:238), [local_temporal.py:318](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:318)). Domain objects store canonical JSON and return fresh detached values; they expose no issuer registry ([local_temporal.py:837](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:837), [local_temporal.py:1048](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:1048)).
- Local verification routing explicitly stops, consistent with T1's no-live-runtime boundary ([verification_router.py:94](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/edge/recovery/verification_router.py:94)).
- Resource cleanup records attempted allocations, closes real instances in finally and restores patched methods ([test_operational_runtime_closure.py:2205](/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py:2205)). Actual JUnit directly records seven tests, zero failures/errors/skips; stdout says seven passed. Controller-settled aggregate reports 28 initialized and 28 successful closes. The independently read owner_grounding sidecar records four of those closes, four observed emptied fields, no errors and restored methods. These are bounded software/resource observations only.

Issues

Critical

None identified. The decoder concerns below do not demonstrate live authorization or physical effects.

Important

### I1. History receipts are not bound to their request or resulting state

Location: [local_temporal.py:538](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:538).

Trigger: In an otherwise decodable new bootstrap/supervision history item, change request.payload.event_key to a fresh nonempty key, leaving transaction.event_key and both operation hashes untouched; alternatively replace resulting_record_hash with another 64-character lowercase hash.

Consequence: The history still passes these checks although its declared request/result no longer matches its receipt. Revision equals only the number of items; it does not prove pre/post state causality.

Evidence: Lines 527–542 validate request and original, compare transaction only against decision, format-check resulting_record_hash, and read the request event key for duplicate detection. No request-operation digest, transaction event key, expected-record link, or resulting-state comparison is made. Callers at 627–628 and 697–698 use only the returned count.

Remedy: Within detached history validation, bind the permitted request tag and canonical operation to the recorded decision/transaction, event identity and acyclic pre/post state references. Validate/rederive the recorded state chain without live issuers or wall-clock calls. Add focused negative cases for independently altered request/event/result links.

### I2. Diagnostic timestamps select whether a publication content hash is verified

Location: [local_temporal.py:750](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:750).

Trigger: For the currently exercised local publication fixture, set diagnostics.utc to {}, then change payload.publication_hash to a different valid SHA256 string without changing content.

Consequence: The native local branch accepts an unverified declared publication hash. Removing logging-only timestamps also changes validation semantics. Nested route produced_publication_hash can then merely repeat that unverified value.

Evidence: Lines 750–757 reconstruct the legacy publication only when both UTC keys exist. The local branch at 411–416 strips schema/original_time and never recomputes publication_hash; its later loop at 457–458 checks only hash shape. Actual comparison exists exclusively in the legacy branch at 423–426.

Remedy: Define and validate the new publication canonical hash consistently, excluding only its self-hash according to the frozen acyclic contract, regardless of diagnostic presence. Keep archival legacy hash validation explicitly separate. Cover both empty diagnostics and preserved diagnostics, including local nested budget histories.

### I3. Route semantic and source hashes are accepted as arbitrary labels

Location: [local_temporal.py:784](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:784).

Trigger: In any otherwise accepted local route record, replace payload.semantic_hash or payload.source_key with any different well-formed SHA256 string.

Consequence: The decoded record claims semantic/source identity that disagrees with its embedded input, defeating T1's semantic hash audit even though input_hash itself remains checked.

Evidence: The generic loop at 593–595 only verifies *_hash shape. The complete route branch at 773–816 checks input_hash but neither recomputes semantic_hash nor source_key, despite explicit local input methods existing in visual_verification.py:734 and :750.

Remedy: Use the exact tagged detached input decoder and established tag-specific canonical algorithms to recompute both identities, preserving legacy definitions for archival input. Add independent mutations for each declared hash, including nested local inputs.

### I4. Nested budgets can carry a different immutable origin than their enclosing history

Location: [local_temporal.py:803](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:803).

Trigger: Supply a local route whose before/after local budget envelopes share the same task_id, sequential revisions and allowed counters, but whose internally valid original_time/reference belongs to another origin. Likewise, a publication can contain internally valid local budget envelopes with the same task_id but different original_time.

Consequence: A detached history can attribute budget consumption to the wrong original obligation while passing individual-envelope validation. Matching task text and nonincreasing limits do not preserve original authority causality.

Evidence: _audit_pool at 506–508 discards each local envelope's original_time and returns semantic content. Lines 803–812 compare only task/revision/counters/limits, not original_budget_reference or enclosing original. _audit_publication at 441–452 similarly reduces nested local budgets to task_id. Local state validation only binds each budget to its own envelope at 608–611.

Remedy: Retain tagged envelope causality during nested auditing and join local input, publication, before/after budget and enclosing immutable original references. Reject rebinding even where task names and numeric limits match. Preserve explicitly separate legacy archival semantics.

### I5. A recorded VALID decision can precede its own original events

Location: [local_temporal.py:304](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:304).

Trigger: Use valid nonzero-origin references and a valid broker segment, but set app_current lower_ns/upper_ns to an earlier counter value in the same app domain and lease_observation.current to an earlier value than segment acquisition in its own domain. Leave the two statuses and disposition VALID.

Consequence: The detached validator accepts temporally impossible positive evidence because being before the expiry is the only temporal condition it checks. This is an audit-causality defect, not proof that the record grants live permission.

Evidence: _bracket at 138–146 checks only lower <= upper. VALID checks at 304–314 enforce upper deadline bounds; they do not ensure current follows original app origin/required reference events or lease acquisition/segment. _join_decision at 318–336 checks identities and descriptors without the missing order relations.

Remedy: Validate the same-domain recorded causal lower bounds required by the frozen P5 descriptor semantics as well as expiry bounds; never compare app numbers with lease numbers. Add nonzero-origin negative fixtures and valid overlap/boundary controls based on the exact P5 event ordering contract.

Minor

### M1. Null scope bypasses the exact semantic scope guard

Location: [local_temporal.py:589](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py:589).

Trigger: Set payload.scope=null in a bootstrap definition or another scoped local payload, preserving the required field.

Consequence: A schema advertised as strict accepts a scope that is neither its required tag nor a valid string.

Evidence: The guard tests scope is not None before checking equality; no later scoped-field type check rejects null.

Remedy: For tags whose exact field set contains scope, require equality unconditionally and add a null-scope negative case.

### M2. Typed nested-history accessor behavior is not covered by the seven executed nodes

Location: [test_operational_runtime_closure.py:2626](/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py:2626).

Trigger: The R173 verification_budget_history/retry_budget_history and LocalRetryBudgetRecord typed accessors are changed, but the seven cases build publications from legacy nested budget payloads and compare serialized envelopes only.

Consequence: Successful roundtrips do not establish that the new local nested getter route works or that it rejects unsupported tags. No runtime failure of these getters is asserted here.

Evidence: _b_decode_domain at 2573 routes retry-budget through generic LocalEnvelope; the roundtrip assertions at 2626–2630 call to_payload only. New getters are at visual_owner.py:487 and :508. actual-evidence.json:43 explicitly reports no targeted R173 accessor execution.

Remedy: Recommend exact focused follow-up validation for both local and legacy nested budget variants, unsupported-tag rejection, returned concrete types and immutable/detached exports, without starting a live budget or broadening into T2/T3.

Assessment

**Task quality: Needs fixes.** Spec compliance: Needs fixes. Code quality: Needs fixes. The single shared codec, immutable storage and resource reporting are useful, but incomplete cross-object validation makes its acceptance stronger than the evidence it establishes. All triggers above are static control-flow deductions, not executed reproductions.

Cannot verify in this review:

- No new product commands, imports, probes, compilation or tests were authorized or run. Proposed mutation cases and R173 accessor calls need separately authorized focused validation.
- The seven executed cases use caller-created UNKNOWN lease/transaction descriptors. They do not prove raw registered broker receipt provenance, positive VALID decision ordering, complete new-style history replay, or fully nested local publication/budget combinations.
- This review directly read JUnit, stdout/stderr and one resource sidecar. The 28-close aggregate comes from the supplied actual ROOT-settled evidence; the remaining six sidecars and full settlement report were not independently re-read.
- Source type-check closure, private transaction/CAS consumption, crash/fault replay, actual worker/broker lifecycle and external model/network/native counters are not established by these seven cases. The latter counters remain null in the evidence.
- No B9/T12/native/physical/actual research/formal acceptance or Git delivery is inferred.

Considered but declined findings:

- Fail-closed local route STOP is deliberate T1 scope, not a missing T2/T3 implementation defect.
- Caller-created UNKNOWN descriptors are valid detached codec controls; they must not be described as actual broker-positive receipts. Their existence is not itself authority forgery.
- Explicit local accessors reject legacy UTC authority deadlines; this is intentional separation. The focused inherited-method check found the relevant route/supervision semantic accessors overridden; no unsupported claim that all inherited accessors are broken is made.
- New semantic_hash methods include entire nested payloads, including any local diagnostics/current publication decision (visual_supervision.py:566; visual_verification.py:750). This is a real static property, but the supplied frozen text does not specify enough of the semantic projection to classify every resulting hash change as a separate defect. Follow-up validation should explicitly settle nested diagnostic/renewal invariance while fixing I3, without changing legacy hashes.
- Partial Memory initialization is reported as incomplete cleanup and fails the fixture when genuine close prerequisites are absent; it is not silently reported as successfully closed. No resource failure path was executed by this reviewer.

Read budget and provenance

Used **9/12 batches**, **3 remaining**; maximum actual source/text batch 600 lines. Metadata 270 lines; complete task diff 3031 lines in six batches; one focused inherited-accessor check (266 source lines plus 27 ledger metadata lines); raw evidence 190 lines. No reset, duplicate reviewer seat, full changed-source reread or outside-diff crawl. Diff SHA256 independently matches 845840f3a5b93a43483f59fb3c4167819366588f9280d8cf1ff9c7184e30b052 (160636 bytes). Display-truncated segments were recovered from immediately stored actual tool returns, not reread from disk. Product/Git/network/source edits/subagents: zero. Writes confined to this review's read-ledger.json, review.md and review.json.
