# R351 bounded offline UTC noncompletion diagnosis

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Same actual `/root/p6_t3_sol` is the sole script author/operator after ROOT activation. ROOT reviews metadata and results. Independent review remains unused.

## Findings and uncertainty

`R350:t3_03` did not complete its UTC memory node within the original bounded600s operation. Session93248/finalchunka813fc recorded wrapper1 at about600.7267s and child−15; cleanup reaped the leader and left no process group. Preserve the contradictory original `timed_out=false` alongside the actual `DeadlineExpired: bounded operation exceeded 600.000s`. Source/HEAD/monitor drift and cleanup failure were not observed.

All381 source pins match. There were2501 accepted HEAD samples, maximum gap0.26175s; no exit-tail observation. No completed JUnit, resource sidecar or case exists. Only `memory-1` is observed; genuine failed-node allocations and polls are **UNKNOWN**. ROOT verified40 retained files/15,227,476bytes and two DB byte copies. These are not a transactionally consistent backup.

The earlier startup-grounding memory/SQLite children passed in315.17s and316.63s through cleanup. Those values neither explain the first UTC scenario nor establish that three completed scenarios accumulated beyond600s.

Finite source review shows sequential −1day,+1day and late-bound scenarios. The first callback includes ground/route and a full supervision sequence. No child stack locates where it stopped. Repeated source/history validation cost, UTC-dependent admission/wait, or synchronization remain hypotheses. The memory fixture closes its initial SQLite event repository and switches to an actual in-memory event repository: retained events.db may be empty/stale and cannot recover that RAM state.

## Scope and one diagnostic allowance

No product repair is justified yet. Allocate **one fresh offline diagnostic attempt**, `R351:offline_db_01`, separately from all behavior slots. It authorizes zero product worker polls and zero live test attempts. Three R350 slots remain SPENT and six remain HELD; the R346 transfer overlay is unchanged. No retry/refund, missing-sidecar reconstruction or historical rewrite.

Create only a new stdlib inspector, source proof, actual binding, diagnostic ledgers/gate, new output and diagnosis report under R351. No product/test/plugin/helper or existing runner edits. Preparation is source-only; do not import/run the inspector, open a database, collect tests or run help before ROOT has reviewed the script and reserved the diagnostic slot.

Exact future launcher:

```text
/usr/bin/timeout --signal=TERM --kill-after=5s 90s /usr/bin/python3 -I -B /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round351-p6-t3-utc-noncompletion-diagnosis-20261024/implementation/inspect-retained-db.py --command R351:offline_db_01
```

Use explicit PATH=/usr/bin:/bin, LANG=C.UTF-8 and PYTHONDONTWRITEBYTECODE=1. ROOT reserves before launch; the script validates the gate and consumes AUTHOR before copying/opening databases. Rejection after reservation spends this diagnostic attempt without retry.

## Genuine input copies and read-only access

Bind both genuine retained DB pins from the intake:

- events.db:327,680bytes, SHA `851199f0503d55c003d9fc1b638846e4a9e4b43474aaf4c95fb5bb453af506a8`.
- runtime.db:13,467,648bytes, SHA `e74d5f5da1785c33b0a55a5a3e38bd12d14d4176a3c767850de3b6f104dc5a47`.

Original and retained source files are byte-read/hash-only. Create exclusive byte-identical disposable copies at `R351/diagnostic/offline_db_01/disposable/{runtime,events}.db`, then make files read-only. Open only those new paths through SQLite URI `mode=ro&immutable=1`, timeout0. No original/retained-source database engine opens, backup/recovery API, WAL replay, checkpoint, migration or project repository construction. Existing inventory contains no associated WAL/SHM/journal; a newly observed sibling or source pin change rejects rather than being ignored.

Set query_only and a restrictive SQL authorizer; allow only the exact schema/read queries and harmless required built-in functions. Deny writes, DDL, attach/detach and extension loading. Use per-query progress-handler deadlines. Close connections in finally and rehash copies and original/retained source bytes afterward. Empty event tables do not prove absent in-memory work.

## Finite queries and bounds

`plan.json.query_contract.exact_queries` specifies all **30 query opportunities** with literal SQL, database identity, row cap and3s limit. No adaptive additional query is permitted.

Schema discovery is limited to seven named runtime tables and five named event tables: at most12 sqlite_master rows, then at most64 column rows per allowed table. Missing table/column is recorded as unavailable and its planned query skipped; never substitute guessed schema or enumerate unrelated tables. Other SQL errors are retained and stop query work without retry.

Read bounded job/lease/attempt state, event-type counts and latest32 events, operational-lease phase/revision, publication phase counts and latest24 runtime publication records; read bounded event-side categories/tasks/publications/bootstrap/supervision metadata. Exact selected columns and limits are frozen in the plan. Included JSON payloads are capped at256KiB each and parsed only by stdlib JSON. Larger payloads remain explicitly omitted with recorded length, not silently truncated into valid evidence.

The entire inspector has60s, with queries stopped by50s to leave10s for close/hash/report; each query is at most3s. Outer guard90s pluskill5 is an emergency boundary, not extra query time. Maximum two DB connections,16MiB diagnostic output and64MiB total new storage. Retain incremental query output, raw wrapper streams, errors and partial results; never truncate prior evidence to meet a cap. No point-in-time or receipt-authority certification follows from this readout.

## Preparation, execution and next boundary

1. ROOT verifies this plan and exact input applicability, then activates same Sol to write the new inspector only.
2. Sol supplies AST/symtable/import/query-whitelist and path/control-flow proofs, fresh binding and HELD diagnostic ledger. ROOT creates its matching ledger and reads the complete script, including read-only opens, bounded queries, CAS, cleanup and evidence retention.
3. Freeze a new diagnostic source gate and ROOT acceptance. Recheck exact HEAD729bce11 and existing interpreter filesystem identity without a new version/startup probe. Preopen raw logs, reserve the single diagnostic allowance and execute only the literal command.
4. Settle both diagnostic ledgers SPENT and preserve original bytes. ROOT reviews metadata/query outputs only; no database engine open by ROOT. Sol reports observed persisted boundaries, source implications, unavailable/truncated fields and unresolved hypotheses.
5. **Further actual Astra planning remains required.** If evidence establishes a repair, obtain its concrete source-repair plan before changes. If it remains insufficient, obtain a finite instrumented live-diagnostic plan with its own explicit runtime allowance. R351 authorizes no live rerun and no resumption of the six held nodes.

## Independent classification issue

The runner's deadline exception and false timed_out flag are a separate issue. Source currently classifies using a later monotonic comparison rather than carrying a typed timer origin; the exact signal-time relationship was not captured. Preserve both raw facts. R351 records this concern but does not change any runner. A separate actual Astra source plan must define future wall-vs-monitor/storage classification before repair, without rewriting old results.

Diagnosis success means a bounded, truthful forensic record—not a passing test, proven root cause, reconstructed RAM state or T3/B/C/native/physical/formal acceptance. Prior two passes remain version-specific. Any unplanned diagnostic failure or expanded scope stops for actual Astra.
