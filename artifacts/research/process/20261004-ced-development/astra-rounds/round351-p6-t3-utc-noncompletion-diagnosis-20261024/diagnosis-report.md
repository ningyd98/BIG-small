# R351 bounded offline diagnosis

Author/operator: actual `/root/p6_t3_sol`, GPT-6.1-sol high. This report uses the single authorized `R351:offline_db_01` result, its retained JSONL, frozen source, and ROOT's independent disposition. It establishes persisted observations and evidence limitations. The cause of R350 UTC-memory noncompletion remains unproved.

## Execution and acceptance

Reservation `6bb19e16-7eb7-4017-8495-7a72c4add358` was used once. The reviewed transport launched the exact planned timeout/inspector argv and environment. Actual tool chunk `ceaeff` returned exit 0 without a session or retry. Transport status records exit 0, no signal, no timeout, no transport errors, and 0.796029121 seconds elapsed. Inspector elapsed time was 0.765984956 seconds. Both raw wrapper streams are empty and preserved.

All 30 fixed query opportunities executed and recorded `OBSERVED`; no unavailable query, SQL error, or unvisited opportunity was recorded. Both permitted connections closed. Product runtime polls were zero. Original, retained, and disposable DB bytes matched their expected hashes before/after; the observed source DB siblings remained absent. These checks do not make the retained files a transactionally consistent backup.

ROOT independently accepted the bounded forensic record with 17 checks true in `root-diagnostic-disposition.json`. This is separate from behavioral or root-cause acceptance, which remains false. The original `result.json` deliberately remains unchanged with `ROOT_accepted=false`; ROOT's later disposition records acceptance. Both diagnostic ledgers are now SPENT, used 1, remaining 0. R350 remains three SPENT and six HELD, with no further launch released.

## Actual persisted SQL observations

All statements below refer to the fixed queries over the new read-only disposable copies. They are not live authority checks or recovered process state. Recorded sequence and rowid ordering are database order; no UTC causal ordering is inferred.

The selected runtime records agree on job `job-0cbf03d3c4c84062`, run `terminal-test`, attempt 1, worker `worker`, and lease `lease-7c04307129674c9d`:

| Query | Observed values |
|---|---|
| `jobs` | One row; status `RUNNING`, `completed_at=null`, empty error code/message. |
| `leases` | One matching row; `released_at` empty. |
| `attempts` | One matching row; result `RUNNING`, empty `ended_at` and error. |
| `operational_lease` | One matching row; lifecycle `ATTEMPT_BOUND`, generation 43, row revision 43, durable phase `COMMITTED`, empty terminal reason. |
| `event_counts` / `last_events` | Five events: one created, one queued, one leased, two started; persisted sequences 1–5. The final selected sequence records STARTING → RUNNING. No terminal event type appears in the returned count groups. |
| `local_publication_counts` | One group: `COMPLETE`, count 11, first rowid 1, last rowid 11. |
| `confirmation_counts` | Zero returned groups. |

The fixed latest-publications query returned 11 rows, below its limit of 24. Each has the same job/attempt/lease/epoch and phase `COMPLETE`. The following is an ascending-rowid presentation of those actual records. Operation labels abbreviate the retained strings; opaque identifiers are not assigned a semantic operation from their hash alone.

| Rowid | Recorded operation label | Generation / revision | SQL-reported payload length | Payload included |
|---|---|---|---:|---|
| 1 | `bootstrap-init:51d8a79e…` | 5 / 5 | 216005 | yes |
| 2 | `worker-reserve_initial_capture-0` | 5 / 5 | 246134 | yes |
| 3 | `worker-complete_capture-1` | 6 / 6 | 333324 | no |
| 4 | `worker-reserve_plan-2` | 6 / 6 | 417762 | no |
| 5 | `worker-complete_plan-3` | 7 / 7 | 511698 | no |
| 6 | `worker-adopt-4` | 9 / 9 | 2276987 | no |
| 7 | `grounding-bind:625c6c96…` | 14 / 14 | 108533 | yes |
| 8 | `grounding-publication:6772f9af…` | 16 / 16 | 379157 | no |
| 9 | opaque `563a05f8…` | 22 / 22 | 3786601 | no |
| 10 | `supervision-init:software-shared-backend-episode` | 28 / 28 | 1024005 | no |
| 11 | opaque `5ed276c1…` | 40 / 40 | 2005588 | no |

The length column is SQLite `length(payload_json)` as recorded by the literal query, not an independently measured UTF-8 byte count for omitted text. Eight payloads were explicitly omitted by the planned 256 KiB selection boundary. No larger payload was fetched afterward. The three included publication JSON values were available for the inspector's bounded JSON parsing. The raw JSONL retains the actual identifiers, selected fields, payload omissions, and hashes.

The stored `COMPLETE`, `COMMITTED`, generation values and receipt-hash strings are observations. This diagnostic did not evaluate current lease authority, validate receipts through product interfaces, reconstruct the publication transaction, or establish successful final publication. An operational-lease revision of 43 and latest selected publication revision of 40 are not sufficient to identify a missing operation or the interrupted call.

All seven planned events-side data queries returned zero rows: local category counts, local tasks, local publication counts, latest local publications, bootstrap, supervision, and owner publication. Schema and required-column queries were available. The memory fixture had closed its initial SQLite event repository and switched to the actual in-memory repository. Consequently, this retained `events.db` cannot recover the RAM event state or prove that the process performed no event-side work. Its empty rows must not be used to synthesize a failed receipt join.

## Source implications and unresolved hypotheses

The frozen UTC-memory test defines successive −1-day, +1-day, and late-hard-bound scenarios. Only the first `memory-1` directory was observed in the interrupted R350 evidence. The first callback's source includes ground/route followed by the full supervision sequence; `_b_t3_supervision` calls `initialize_supervision` and retains the original 300 ms cadence and owner-counter advance. The recorded grounding and supervision-init labels are compatible with those source boundaries. They do not show that the enclosing calls returned, which assertions ran, or what stack was active when the deadline fired. The later opaque publication row is deliberately left unidentified here.

There is persisted work beyond bootstrap and multi-megabyte publication text. This makes repeated source/history/envelope processing a reasonable hypothesis to distinguish in a future plan. Size alone does not demonstrate repeated processing, excessive CPU time, or a performance root cause. UTC-dependent admission/wait and synchronization remain alternative hypotheses. No stack sample, call duration, CPU profile, lock-owner observation, or in-memory event snapshot was recovered. The fast offline readout measures this forensic operation only and cannot explain the earlier live execution cost.

The original R350 evidence remains a bounded 600-second `DeadlineExpired`, child −15 and wrapper 1, alongside the original `timed_out=false` field. These facts have not been reconciled by editing history. There is no completed t3_03 JUnit, case result, or resource sidecar. Genuine failed-node worker allocations and poll counts remain UNKNOWN. The first two R350 passes remain results for their exact version and nodes; neither they nor this diagnostic establish UTC-memory success or T3 completion.

## Proposed boundary for the next actual Astra plan

No product repair follows from R351 alone. A next actual Astra plan should first decide whether finite source analysis can identify the opaque operation labels without executing product code. If live evidence remains necessary, it should specify one separately budgeted diagnostic with fixed observation points around ground/route, supervision initialization and subsequent supervision operations. Useful discriminators would be bounded monotonic entry/exit records, independently bounded stack samples, and finite size/call-cost observations at the source/history validation boundary. Those measurements should distinguish active repeated work from waiting or synchronization without weakening cadence, authority, generation checks, or deadlines. Observation limits, storage, cleanup, actor, command, and missingness rules require their own explicit plan and ROOT gate.

The deadline-exception versus `timed_out=false` classification concern remains a separate source-planning issue. Any future correction should retain the originating timer classification and define signal/monitor/storage precedence while preserving all old results. R351 authorizes neither that repair nor a live retry, and releases none of the six held behavior nodes.

## Evidence pins

Paths are relative to this R351 directory. Full raw evidence is retained; this report is a derived account.

| Artifact | Bytes | SHA256 |
|---|---:|---|
| `diagnostic/offline_db_01/result.json` | 1335 | `0e6ae61f8db5ade0c55795a8c4ddff5492cb51aa25bdaa228f9530234b6aaf70` |
| `diagnostic/offline_db_01/query-results.jsonl` | 655727 | `a62ee78c27a94763814a24397771b9b69441cf9fb9e1f91991c09f96ec8d9935` |
| `diagnostic/offline_db_01/queries-index.json` | 27222 | `88bfa0852974990aa124f73890ac3624afe514f82681caf94cc92aeec4572c01` |
| `diagnostic/offline_db_01/source-after.json` | 288176 | `f3dbf873bf5d88a66613741b66eb69e968a15924af53d99835f4909ac4af6984` |
| `diagnostic/offline_db_01/wrapper-status.json` | 2800 | `9cda2569e6267068fa7d7747f726be0e88ea5e29a32fa48ea6e42205947eef22` |
| `root-diagnostic-disposition.json` | 9934 | `9febdaaf5898ded3a472c90b6a2555d9bb2358f141f43aefdcce5b8b91b370e2` |
| Runtime DB, each original/retained/disposable copy | 13467648 | `e74d5f5da1785c33b0a55a5a3e38bd12d14d4176a3c767850de3b6f104dc5a47` |
| Events DB, each original/retained/disposable copy | 327680 | `851199f0503d55c003d9fc1b638846e4a9e4b43474aaf4c95fb5bb453af506a8` |

ROOT verified all 441 before/after/current immutable pins and unchanged HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`. The inspector, source proof, product/test/helper/runner sources, old evidence, and historical ledgers remain frozen. After the single diagnostic, report preparation used JSON/text reads only and performed no database-engine reopen, query, test, import of project code, or runtime poll. This report is the final authorized author write for this step.
