# Independent INITIAL Source Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this bounded task. Steps use checkbox syntax for tracking. The root agent already authorizes this execution method and the exact ownership below; there is no additional permission or commit step.

**Goal:** Independently reconstruct owner-registered INITIAL source evidence without granting method or execution admission.

**Architecture:** One read-only auditor binds an allowlisted evidence root and exact INITIAL protocol file to current role/source identities. It recomputes the final immutable T8 evidence-derived spec, compares every spec field and canonical protocol hash, preserves the complete observed file inventory and rejects drift before/after verification. INITIAL_SOURCE and METHOD are separate requested scopes; METHOD remains UNKNOWN because actual risk and finite-weight/selection verification are not implemented.

**Tech Stack:** Python 3.12+, existing Pydantic research/role types, pathlib/hashlib, immutable dataclasses and MappingProxyType, pytest/Ruff/mypy. No added dependencies.

**Spec:** Root's approved bounded INITIAL auditor task and `../t12-runtime-composition/admission-design-audit.md`; inherited `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md`.

## Global Constraints

- Own only new `src/cloud_edge_robot_arm/research/admission.py`, new `tests/test_research_admission.py` and this artifact directory.
- Consume runner's explicitly released immutable final T8 `initial_spec_from_evidence` and supporting sources. Save its exact manifest/overlay before tests; do not use a moving dependency as final evidence.
- No edits to actual policy, vision execution, binding, configuration, repositories, UI or prior frozen adapter. No dispatch, HTTP, model calls, capture, GPU, INITIAL freeze or actual selection.
- No caller-supplied acceptance boolean, injected VALID callback or receipt can bypass reconstruction. Source hashes bind integrity, never admission by themselves.
- No cached acceptance. Every audit repeats raw-file inventory, actual semantic reconstruction and current source checks. Failures do not become a cached success.
- Genuine complete INITIAL may be independently VALID only for INITIAL_SOURCE. METHOD and EXECUTION remain unavailable. Synthetic/software fixtures do not demonstrate genuine INITIAL admission.
- Preserve every assigned failure/blocked record and exact current source/role identities. Missing evidence → UNKNOWN; malformed, drifted, escaped or inconsistent evidence → INVALID.
- Scoped CPU/static checks plus final immutable source/report/review handoff; no commits, whole-project suite or installation. Root coordinates independent review.

## Review Focus

1. Registered path replacement, symlinked roots/files/directories and escaped nested evidence must reject before trusting content.
2. Rehashed protocol/summary/raw omissions must not pass merely because hashes match.
3. Current role/collector bytes or any raw file changed during/between audits must invalidate the original binding.
4. Mutable registration/result aliases and forged VALID requests must not alter a later audit.
5. INITIAL_SOURCE validity must never imply risk, finite-weight selection, ordinary mode or physical execution admission.

## Typed Interfaces

```python
AdmissionScope = Literal["INITIAL_SOURCE", "METHOD"]
AdmissionStatus = Literal["VALID", "INVALID", "UNKNOWN"]

@dataclass(frozen=True)
class InitialSourceRegistration:
    evidence_root: Path
    protocol_path: Path  # exact owner-registered protocol.json, separate from evidence root
    current_role_binding: RoleRuntimeBinding
    current_source_hashes: Mapping[str, str]  # exact collector inventory from released T8

@dataclass(frozen=True)
class ResearchAdmissionResult:
    requested_scope: AdmissionScope
    verified_scope: Literal["INITIAL_SOURCE"] | None
    status: AdmissionStatus
    initial_source_status: AdmissionStatus
    reasons: tuple[str, ...]
    protocol_hash: str | None
    role_bundle_hash: str | None
    raw_file_hashes: Mapping[str, str]  # evidence:<relative> and protocol:<registered file>
    current_source_hashes: Mapping[str, str]
    inventory_hash: str | None
    method_admitted: Literal[False] = False
    execution_admitted: Literal[False] = False

class InitialSourceAdmissionAuditor:
    def __init__(self, registrations: Mapping[str, InitialSourceRegistration]) -> None: ...
    def audit(self, evidence_id: str, *, scope: AdmissionScope = "INITIAL_SOURCE") -> ResearchAdmissionResult: ...
```

Registration keys are exact opaque owner IDs, not paths. `audit` rejects unknown IDs and invalid scope values. The constructor detaches nested source/role structures and stores an immutable registration map. No verifier callback or acceptance receipt is accepted. Current role identity comes from the registered immutable RoleRuntimeBinding; this source audit does not claim an actual current planner or execution snapshot.

`current_source_hashes` must equal the immutable T8 collector source inventory recorded in original `source-hashes.json`; every named relative path is validated and compared against the actual repository source bytes. Current cloud/edge/device sources are read from the registered role binding's repository root and checked against that binding. `initial_spec_from_evidence` itself retains its current/archive and complete raw acceptance checks. The frozen protocol must be explicit `ced.research.v2`, stage INITIAL, selected_n=None; comparing canonical `model_dump(mode="json")` values checks all fields, including unexpected method/final fields.

METHOD returns UNKNOWN with `method_risk_source_verifier_unavailable`, `method_weight_selection_verifier_unavailable`, and `execution_owner_registration_unavailable` after recording the independent INITIAL result. It cannot return VALID or set either admission field true even if INITIAL is VALID. Rejected/missing INITIAL reasons remain present.

## Task 1: Safe registration, inventory and rejected/missing audit

**Files:** Create `research/admission.py`; create `tests/test_research_admission.py`.

- [ ] Write failing tests for unknown ID, unsupported scope, empty/missing roots/protocol, symlink root/nested file/protocol, relative source escape, malformed/hash-drifted protocol, v1/FINAL protocol, mutable registration/result aliases and no callback/flag acceptance.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_research_admission.py`; save qualified missing-feature RED after fixing fixture/import mistakes.
- [ ] Implement the typed interfaces and read-only detached registration/inventory. Include all regular raw files, reject symlinks/escape and retain structured missing/error results. Do not write evidence or invoke shell commands.
- [ ] Run the same tests, save GREEN. Every final result uses immutable mappings and tuple reasons; no internal cache.

## Task 2: Independent INITIAL reconstruction and closed METHOD scope

**Consumes:** Released immutable T8 `research.freeze_evidence.initial_spec_from_evidence(directory: Path) -> ProtocolSpec`; `research.protocol.load_protocol(directory: Path) -> FrozenProtocol`; existing RoleRuntimeBinding data and source identities. Dependency release must be saved before GREEN.

- [ ] Write RED tests using the actual final T8 verifier for rehashed metadata-only/raw-omitted evidence and current collector/role source drift. Reuse released T8's negative/source fixtures where practical; do not fabricate a positive actual acceptance case.
- [ ] Add explicit software unit coverage of spec/hash/current-role comparison without a production injected verifier or treating those fixtures as actual valid INITIAL. METHOD must remain UNKNOWN/false/false. Preserve the real verifier's rejection in the ordinary public path.
- [ ] Implement full frozen spec comparison against independent reconstruction, current source/role checks and before/after complete raw inventory comparisons. Missing actual inputs yield UNKNOWN; malformed/drifted/semantically inconsistent input yields INVALID. Any INITIAL-only verified result remains source scoped.
- [ ] Run own tests plus released T8 pilot/freeze/resource targeted tests through an explicit immutable source overlay; save all exact commands and logs. Run scoped Ruff and native mypy.

## Task 3: Freeze and independent review handoff

- [ ] Recheck the original runtime composition manifest remains unchanged.
- [ ] Save ownership, pre-implementation baseline, RED/GREEN/static logs, two owned source copies and all exact immutable dependency references, SHA256 manifest and review diff in this directory.
- [ ] Report exact tests and limitations: no genuine complete actual INITIAL exists locally, METHOD/EXECUTION never enabled, current actual owner/planner/native bounds remain unavailable. Do not label the research core complete.
- [ ] Send immutable release and exact scoped overlay command to root for independent review; fix findings only in owned files via a preserved baseline and RED/GREEN regressions.

## Self-review

The task implements INITIAL source admission only. Actual calibration/risk, full finite selection, current owner registration and native certificate integration remain separate owner tasks. Original planned requirements versus derived same-version grounding cannot be erased by this auditor and it does not implement the registry/dispatcher. All five review-focus items map to explicit tests above. User authorization and root ownership override skill defaults for location, additional approval, broad suites and commits.
