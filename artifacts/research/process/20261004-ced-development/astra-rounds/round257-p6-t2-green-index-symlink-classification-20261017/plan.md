# R257 — exact GREEN index classification

Actual gpt-6-astra (/root/astra_status_plan), 2026-10-17. Plan only; STOP pending ROOT.

The original ROOT acceptance failed22 of4638 checks: four recorded symlinks were blanket-rejected and18 database index rows with intentional null SHA were treated as ordinary file pins. Author index() records link text and skips initial database hashing; persistent_index() supplies separate full database pins. These are two variants of the same ROOT index-type misunderstanding, not observed product failures.

Readonly full physical comparison covered all548 entries:177 directories,4 links,367 regular files. All exact paths/type/mode/size match; raw index equals result.new_run_index. Every link has its exact recorded text and an indexed nonsymlink directory target inside the same basetemp; no link alias was hashed. The18 null-SHA regular DB rows each match their independent full database bytes/SHA;54 sidecars remain absent. All22 original failed labels are individually attributed in input-observation. No byte drift was found. Physical JUnit has the exact9 cases,0fail/error/skip; final behavioral/resource acceptance still needs ROOT's complete existing-evidence review.

ROOT writes a new independent metadata checker under R257; old checker/failure and runtime files stay immutable. Keep fixed() strict. Classify directories by lstat; exact four links by lstat/readlink/target confinement without opening aliases;349 hash-bearing regulars by their own pins;18 deferred-hash DB entries only by exact membership in independent databases.pin. Reject any new/missing/outside/changed/special/null-without-authority entry. Compare full no-follow path set before/after and stable file descriptors while hashing. No SQL or database repair.

Preserve all other actual/session/JUnit/case/resource/source/history/role checks.35 known missing/null and old90 absent sidecars retain their declared limits;12 existing workspace DB/36 sidecars remain strict, separate from18 new DB/54 sidecars. No generic pytest-link allowance, missing-pin waiver or invented historical bytes.

One new ROOT-only120s stdlib metadata recheck of the same runtime is permitted after complete durable source/SHA/argv/input gate. Use exclusive new receipts/full raw streams in R257 and bounded<=6000 UTF-8 summary. A failure preserves raw and stops without retry. No GREEN rerun or original budget reset. Only after all checks and ROOT full-read may an exclusive canonical R251 root-green-acceptance.json refer to the original runtime pins plus new metadata evidence. It does not mutate roles. Original root_settlement remains0/1HELD until its own subsequent R251 gate.

No product/fixture/author/runtime-script/47-input-contract changes; no tests/static/import/AST/SQL/Git. This plan does not complete T2/T12. Full exact inputs,22-path attribution and all548 physical observations are preserved in companion JSON files.
