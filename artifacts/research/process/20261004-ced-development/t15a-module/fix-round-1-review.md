# T15a fix round 1 independent re-review

Verdict: **REQUEST CHANGES**. The exact schema fix is closed. The failure-penalty fix closes the original nominal cases but can still be bypassed by relabeling provenance.

Reviewed the released `fix-round-1-review-package.diff` against `fix-round-1-baseline/`, its report append, and twelve immutable saved `source/` files. At review start all twelve live files matched the current hashes and saved copies. Manifest byte SHA256: `8d61334ae8bd0496afee131e34752e7041eaa6c179f7f620bfd3d469074dbadf`. Base/head remains `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. No production/test changes were made by the reviewer.

## Remaining P2 — Caller-controlled split labels bypass protocol-aware formal-record validation

Locations: `src/cloud_edge_robot_arm/research/assignments.py:228–232`, `:303–306`, `:466–469`.

The new guards decide whether a record is formal using `provenance.split_role`. That is an untrusted field of the record being validated. Keeping the exact formal assignment/protocol/pool/scene/method binding while changing this field to `selection` bypasses the constructor's required deadline, the serializer's required protocol, and even the loader's explicitly supplied protocol. The CLI's exact assignment equality check therefore cannot detect this relabeling.

Independent reproduction against the released code:

```python
base = record(assignment(pool), "BLOCKED")
changed = replace(
    base,
    provenance=base.provenance.model_copy(update={"split_role": "selection"}),
    duration_penalized_s=0.001,
    frozen_tcap_s=None,
)
payload = changed.to_payload()  # accepts without protocol
restored = episode_record_from_payload(payload, protocol=frozen(pool))
assert restored.assignment.protocol_hash == frozen(pool).content_hash
assert restored.provenance.split_role == "selection"
assert restored.duration_penalized_s == 0.001  # accepted under Tcap120
```

A temporary actual CLI resume reproduction independently confirmed `status="BLOCKED"`, `assigned_denominator=600`, `recorded_assignments=600`, first record `split_role="selection"`/penalty `.001`, and unchanged original record bytes. It did not reject as NOT_RUN. `physical_success=0` and `accepted_task_success=False` remain intact.

Requested correction: classify formal binding from the assignment/trusted protocol boundary, and require compatible formal provenance. Whenever a protocol is explicitly supplied to serialize/load, validate it unconditionally rather than allowing a payload's split label to disable that validation. A bound formal assignment must not be downgraded to a diagnostic selection record. Add a newly hashed relabeling regression through constructor, loader and CLI resume; preserve bytes on rejection.

## Confirmed fixes and verification

- Supported schema is now checked both at construction and raw persisted loading; missing/unknown versions reject even with a matching digest.
- Nominal formal records require valid `frozen_tcap_s`; shortened penalties and a rehashed deadline inconsistent with the supplied protocol reject. Raw hash checks precede semantic loading. MOCK completion labels are now consistent with software-only failure, while accepted_task_success stays False.
- Independent `.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py`: **52 passed in 23.55s**, exit 0. The tests were collected from the released snapshot before the implementer began adding the next regression.
- Ruff over the four immutable modified Python copies passed with the same `pyproject.toml` rules and explicit first-party identities `cloud_edge_robot_arm,tests` to preserve import classification for their archived paths. A later live-tree Ruff saw the implementer's newly added relabel regression with a formatting error; that moving file is outside this released review snapshot. A direct archive-path Ruff initially classified `tests` differently and reported import sorting; the explicit package identity resolved that archive-location artifact without editing any file.
- Counterexamples used only CPU software fixtures and temporary directories. No network/provider/model/GPU/render/physics execution, real credential acceptance, INITIAL/FINAL publication, broad project suite or physical acceptance occurred. Only this review report was written. A new immutable release is required before the next re-review.
