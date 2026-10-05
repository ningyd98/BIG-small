# R03 source-only RESET prefix software slice

Status: quiet for independent review. This closes the authorized P1–P4 software scope; no actual clock, renderer, native physics, model or calibration trial ran.

The application creates a genuine SQLite job/lease/attempt and enters the existing worker before planner construction. The privately owned source/worker/capture registry rejects copied public objects, mutated assignment/source/asset/config/verifier state and lost leases. One observer preserves exact original clock tuples, RESET BEGIN/END, cached frames, commands, physics, failures and separate sequence denominators. It freezes the slab before B, exports unbound originals and publishes the receipt/catalog only after source/lease checks and durable writes. The existing worker changed in three bounded hunks (`worker.diff`).

The default formal camera/noise configuration is unchanged. Future genuine RESET and SETTLE invoke cached camera updates: cached CAPTURE/RGBD originals must be measured and retained. Only explicit RGB-D acquisition, planner/model construction and action requests are intended zero. No cache/noise suppression exists in this slice.

Historical A/B intervals can describe only originals frozen before B. They do not provide current UTC after verification or consumer feasibility. Issuer accuracy stays UNVERIFIED; native/current UTC stay UNAVAILABLE. The TTL field is a necessary historical-width comparison only. No role binding, adopted RawV3 identity, empirical finite admission or independent calibration group was obtained. The public offline reader hashes originals and checks raw joins; signature/causal replay belongs to the owned publisher through R2. Trusted-process ownership is not a defense against arbitrary code execution.

## Verification

- Four owned CPU files (including the root-owned CLI tests): **31 passed in 10.11s**, `owned-quiet-green.log`.
- Seven explicitly selected existing raw/worker-owner tests: **16 passed in 4.22s**, `narrow-regression.log`.
- Ruff and format: PASS for eight Python files. Mypy: PASS for the two new modules and bounded worker source.
- Default CLI: `INPUTS_ONLY` / `NOT_RUN`, no requested output directory created.
- All final logs were read. Exact commands and unchanged input pins are in `report.json` and `source-hashes.json`. Overlapping earlier runs are not added to the final count.

CPU fixtures use real SQLite/observer APIs with SOFTWARE_ONLY backend RESET/120-step/camera/network inputs. One wire rejection uses the real pinned Go request/verifier with substituted UDP; no live packet is evidence. These fixtures establish software graph/authority checks, not native provenance or UTC precision.

## RED and retained failures

Qualified RED was recorded for missing recorder/publication/worker seams and for original assignment/callback, actual asset/cached-failure denominator, copied-verifier and premature-catalog-publication gaps. Each precise log remains unchanged; minimal fixes are covered in final GREEN. The final catalog write regression keeps raw originals and no live catalog on OSError. The worker correctly classifies that as BLOCKED_BY_ENV.

Original fixture/setup failures (scenario serialization, missing config, invalid CLOUD enum and an incorrect FAILED-versus-BLOCKED_BY_ENV expectation), the real mappingproxy serialization failure, and original Ruff/mypy failures remain in their original logs. They are distinguished from qualified RED in `report.json`; no initial log or frozen R02/design/preparation was rewritten.

## Frozen source

| Path | SHA-256 |
| --- | --- |
| `src/cloud_edge_robot_arm/research/native_reset_capture_v2.py` | `a22ce81503a1dd7d6aa9b81a57eb61cebcbda64ec58228a5c4dbe21da1e41f5a` |
| `src/cloud_edge_robot_arm/research/native_clock_publication_v2.py` | `3eed8c44c4bb0657741a3f9ab113f9f035b3d73d5aa8ed8ca4c5c24fca880105` |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `e1facb79224d58e92b3e48a00806c32468a45174742b280575304a3d8036b008` |
| `configs/research/native_clock_authority_v2.json` | `9102ed5cc8db26700bd7a5bf6ec61bd45dcf75ead62a35f62d44f563a17a615a` |
| `tests/test_native_reset_capture_v2.py` | `551d080e6eb33d2bcc6183e3be044224aa903c4691066946d0d52775a584f7b8` |
| `tests/test_native_clock_publication_v2.py` | `a57b3a1a7ffb8e0c4afb28b96cf355e83c3b52e93317ae17e151667528fa147f` |
| `tests/test_native_clock_prefix_worker_v2.py` | `fbfa14e5596bdba70d5263b7f770dd689bdda342e56389da16985f417bc20b7b` |
| `scripts/run_native_clock_prefix_v2.py` | `c9630134e1fa0039dfb040bbf92e1e0401d175efe34e0c46939ec47de22ada83` |
| `tests/test_native_clock_prefix_cli_v2.py` | `0df55934ca677b03a67dc186bfe14d989561f79bd27c6718ce79f8cc7effbae0` |

The seven frozen non-worker input pins and original worker bytes were checked. Root-owned CLI sources exactly match its quiet handoff. R2 sources/tests, upstream Go sources/binary/metadata and prior preparation remain unchanged. The source manifest includes the validated startup inventory and every retained log hash. No Stage/Git or old raw/asset/consumer/source was changed.

## Next root-owned pilot

After scoped independent software review, root can launch one fresh excluded prefix with the command in `report.json`. It uses A → genuine native RESET/120 SETTLE → freeze originals → B → guarded publication. No actual launch occurred here. Candidate issuer response/key/protocol support and independent UTC precision remain unproved; any failure is preserved with UNAVAILABLE output. This pilot is a source-only diagnostic and does not supply the nine independent calibration groups or activate any native consumer.
