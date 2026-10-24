# R336 supervision context generation fixture plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol` only.

The new fixture sets `context.state_version=claim.cursor`. Those values describe different things. The actual claim captures a publication, and strict local/legacy capture consumers require that publication's `state_generation`. The fixture's adoption → grounding → route chain advances publication generation while periodic capture cursor remains 1. This is a static producer-binding defect, not an executed runtime failure.

`root-finding.json` and `original-RED-test.py` preserve the finding and full accepted RED test generation (312244 bytes, SHA256 `c0863aa83fff9763bb7bf090fdfba2d426627f91c522474cf798b2a22b2f998b`). Actual claim getter/source-check interfaces are recorded in `claim-interface-source-slices.json`; all immediate pins and ledger facts are in `plan.json` and `planner-relation-readout.json`.

## Minimal correction

Modify only the appended `_b_t3_supervision` function.

- [ ] After the real capture reservation, bind `claim_publication = claim.publication` and `current_publication = runtime.supervision_source_publication`.
- [ ] Assert `claim.cursor == 1`, and `claim.publication_hash == claim_publication.digest() == current_publication.digest()`. Verify the claim step matches the publication checkpoint step and existing original identity remains coherent.
- [ ] Set `SupervisionContext.state_version=claim_publication.state_generation`. Preserve every other context field and actual consumer call. Assert the context generation equals both claim and current publication generations; retain cursor as an independent value.
- [ ] Add actual relation evidence under `cadence["supervision_context_binding"]`: claim id/cursor, claim/current publication hashes, publication generation and context state version. The existing returned cadence already reaches UTC-provenance evidence; no caller change, new node or poll is necessary.

Do not use a hard-coded 2, stale `data["publication"]`, a rebound claim or cursor as a generation proxy. Do not change product consumers, publication generation, cursor, existing cadence/cost assertions or strict source checks.

## Verification and source generations

- [ ] ROOT verifies frozen before pins and same Sol. Sol preserves the original RED source and applies only this helper correction.
- [ ] Use stdlib source-byte/hash/AST/symbol-table operations to prove successful parsing, exact helper-only diff and direct claim-publication data flow. No import, execution, collection or test call.
- [ ] Original **260206-byte prefix**, SHA256 `dfe6ce74fd0fe2c8f1694b73e74766f0933cb5ad1f67e7a033838c89d9adaf29`, and every byte outside this helper remain unchanged. Nine nodes and fifteen-poll cap remain.
- [ ] Save before/after pins, minimal diff and `implementation/source-proof.json`. ROOT independently checks strict relation assertions and evidence plumbing, then records R336 acceptance.
- [ ] Preserve RED's accepted/spent status (**used 1, remaining 0**); **never rerun RED**. GREEN stays **unused/held, used 0, remaining 1**. Its future ROOT source gate must bind the new fixture SHA and actual completed product generation.

The original RED established planned missing-interface guards on its original source. It did not exercise this corrected relation. No retroactive replacement of RED source/raw or claim of current-generation behavioral evidence is allowed.

## Concurrent work boundary

Independent original R331 application-cap/public-model/service/final-audit work may continue. R336 does not freeze or require rollback of those changing files. The used worker-runtime interfaces are pinned as finite source slices, not as a whole-file immutability demand. Frozen `local_temporal.py`/`visual_verification.py` relation sources must remain unchanged during this fixture correction; any later product migration proceeds under its own applicable R331 gate.

Acceptance is only the new fixture's correct source-generation binding. No product validator weakening, new runtime allowance, budget reset, agent spawn or B acceptance. If the actual interface/consumer relation contradicts the plan or broader edits are needed, stop the affected repair for actual Astra while independent authorized work continues.
