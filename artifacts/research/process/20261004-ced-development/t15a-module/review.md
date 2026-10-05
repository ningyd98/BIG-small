# T15a independent software review

Verdict: **REQUEST CHANGES**. Two reproducible persisted-record contract gaps remain. Neither counterexample promotes a software fixture to accepted physical success.

## Reviewed snapshot and scope

- Reviewer: independent `/root/ced_cloud_roles`; review started after `/root/ced_research_runner` explicitly released its final snapshot and promised no further T15 edits.
- HEAD/base: `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`.
- Exactly the 12 files listed in `source-hashes.json` were reviewed against their preserved `source/` copies and `review-package.diff`. All SHA256 values, byte counts, saved copies, and reconstructed diff sections match. Manifest byte SHA256: `5c36cbc1f2409627577f4176f9b32f730bd8b627754d1d633e2d6d4f801c2fc3`.
- Read original `docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md` Task 15, lines 422–438, and current `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md` T15a/T15b/T15c boundaries, lines 190–209, plus the module report and relevant existing protocol/provenance/replay dependencies.
- Applied the requesting-code-review workflow as the independent reviewer already dispatched by root; no additional reviewer was spawned. No production, tests, shared documentation, dependencies, or commits were changed. This report is the only repository write. Counterexamples used temporary files only.

## Findings

### P2 — Validate persisted failure penalties against the frozen Tcap before accepting resume records

Locations: `scripts/run_rgbd_research.py:80–91`, `src/cloud_edge_robot_arm/research/assignments.py:209–217` and `:388–403`.

The online BLOCKED/MOCK runner correctly assigns the full Tcap. The persisted-record boundary does not enforce that rule: `EpisodeRecord` accepts any finite nonnegative penalty, and resume validates the content hash and assignment identity without validating the record against the frozen protocol. A producer can therefore construct a normal, internally hash-consistent BLOCKED record with a 0.001-second penalty under Tcap=120; the loader and resume retain it as a valid original. This is not merely corruption with an unchanged digest: the public `to_payload()` generates the valid digest for the invalid semantic record.

Concrete CPU reproduction using the released test fixtures:

```python
pool = scene_pool.__wrapped__()
base = record(assignment(pool), "BLOCKED")
payload = replace(base, duration_penalized_s=0.001).to_payload()
restored = episode_record_from_payload(payload)
assert restored.duration_penalized_s == 0.001  # accepted; frozen Tcap is 120
```

A temporary CLI run first generated all 600 BLOCKED records. Replacing the first line with the valid `to_payload()` of that shortened record and resuming produced `status="BLOCKED"`, `assigned_denominator=600`, `recorded_assignments=600`, `blocked_assignments=600`, and only the ordinary missing-runtime reason. Resume left the 0.001-second record unchanged instead of rejecting it as NOT_RUN. Executed assignments and physical success remained zero.

Requested correction: add a protocol-aware semantic validation boundary before persisted records enter `completed` or downstream formal statistics. Reject a shortened penalty for BLOCKED/TIMEOUT/STOP/FALLBACK/FAILED and unsuccessful completion; preserve original bytes on rejection. A hash verifies what was written, not whether a failure used the preregistered penalty. Add a regression with a newly hashed invalid record, because the existing unchanged-hash tampering test cannot cover this case.

### P2 — Reject unsupported EpisodeRecord schema versions during construction/loading

Locations: `src/cloud_edge_robot_arm/research/assignments.py:198–202` and `:388–403`.

The verification envelope has an exact supported schema check, but its containing persisted EpisodeRecord does not validate `schema_version`. `episode_record_from_payload()` accepts an arbitrary nonempty, empty, or unrelated schema tag if the payload digest matches, interpreting it with the v1 layout anyway. This defeats the versioned persisted-record contract and allows unknown record formats into resume.

Independent reproduction (without changing the penalty):

```python
payload = replace(base, schema_version="unknown.record.v9").to_payload()
restored = episode_record_from_payload(payload)
assert restored.schema_version == "unknown.record.v9"  # accepted
assert restored.duration_penalized_s == 120.0
```

The combined CLI reproduction also accepted this unknown tag while resuming all 600 originals. Requested correction: require the supported `ced.episode-record.v1` version at the constructor/loader boundary, or explicitly dispatch supported versions; reject unknown/missing persisted versions. Keep the defaulted keyword extension compatible with the original positional constructor. Add a newly hashed unsupported-version regression.

## Requirements confirmed in this snapshot

- Full 2400-row source pool is checked before selection; scene/group/assignment uniqueness and 200-per-stratum balance are enforced. Selected N is balanced and uses original per-stratum prefixes. Requested methods share complete scene/perturbation/physics seed/network schedule bindings and deterministic method order.
- INITIAL, invalid FINAL hashes, missing frozen method/source hashes, omitted/drifted pools and network schedule content drift are rejected or produce explicit BLOCKED records. The actual runtime and real FINAL acceptance remain unimplemented and are identified as such; no execution success is inferred from a metadata-only FINAL fixture.
- The default runner performs zero model requests/actions/physics steps; explicit MOCK adapters clear physical/task success and apply Tcap. Recovery failure remains 60 seconds. Existing original records are append-only during ordinary resume. Infrastructure rerun authorization retains original hashes, requires a readable hashed whitelist incident, full caller-provided method set, and identical paired context; it does not execute reruns or retry task failures.
- Gate replay preserves opportunity order/identity, common candidate snapshots and each frozen clock. Changing oracle labels does not change gate verdicts. Formal G3 is refused; the explicit software fixture output is labeled MOCK/SOFTWARE_ONLY and cannot count as task success.
- The power function requires exactly 120 strict Boolean pairs, fixes alpha=.05, target=.8 and five-family Bonferroni planning alpha=.01, uses observed paired discordance without a variance floor or favorable pilot effect, and chooses only the minimum allowed N satisfying both gates. At q=0, the all-concordant noninferiority null bound is `(1-margin)**N`; separate discordance confidence bounds do not affect sample choice. It makes no claim to replace formal Holm analysis or verify pilot source authenticity.
- Verification envelopes require exact envelope schema/keys, an unmodified hashed verdict payload and nonempty well-formed source references; `source_verified=True` verifies referenced file byte hashes. Verdict/provider mappings are recursively frozen. This is structural/hash verification only: `accepted_task_success` is always False, including fabricated PHYSICS metadata with valid file references. `structurally_complete_success` is explicitly metadata-only.

## Independent validation

- `.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py`: **46 passed in 9.60s**, exit 0.
- `.venv/bin/python -m pytest -q tests/test_research_protocol.py tests/test_research_provenance.py tests/test_research_cost_ledger.py tests/test_fixed_opportunity_replay.py tests/test_visual_evidence_contract.py`: **71 passed in 2.94s**, exit 0.
- Ruff over the nine scoped Python files: **All checks passed**, exit 0.
- Constructor/loader counterexamples independently printed `penalty_only BLOCKED 0.001 ced.episode-record.v1` and `schema_only BLOCKED 120.0 unknown.record.v9`.
- A bare `pytest` command was unavailable (exit 127); all actual tests used the documented project virtual environment afterward.
- No network/cloud/model/GPU/render/physical execution, broad project suite, or real provider/credential acceptance was attempted. Passing CPU fixtures is software verification only. Real method integration, source-based physical verification, INITIAL/FINAL acceptance, the new 120-group real power pilot, and formal research acceptance remain unverified.
