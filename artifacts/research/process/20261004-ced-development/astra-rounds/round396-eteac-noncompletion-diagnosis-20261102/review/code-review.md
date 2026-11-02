# R396 final independent evidence review

**Ready for exact selected delivery: Yes — C0 / I0 / M0.** Candidate manifest SHA256 `1dc43bfce1b30e1d16c7777ea96ccf3cef27c2cae8389498efb879cf60994ed7`; independently verified all 45 payload files and 233068 bytes against their listed SHA256. Executed driver matches approved SHA256 `3919f5ed871a8ff5d9ae000e7981856a6c5c5be86ff1f8e6f0ef6dc7deee3775`.

## Strengths and evidence

The current replay supports **H1_CONFIRMED_IN_CURRENT_REPLAY**. Exact original request semantics, actual recorded runner configs and the approved environment match. One real native PCSC poll succeeds in 6.015125242 seconds; one ETEAC poll does not return. Four independently inspected frame snapshots at 5/15/35/65 seconds and matching faulthandler stacks show MainThread127611211866240, repository127610451227424 and ordinary lock127610430543232 unchanged. Outer sqlite.py:976 is inside its :973 lock context; inner protocol.py:215 is get_retry_budget dispatch, scope None, waiting on that same locked lock. Pinned construction and control flow establish ownership together with frame identity; no unavailable C acquire event is claimed.

The 71 boundary rows show ETEAC runner.run, harness.submit_contract and initializer each entered once without return, and no ETEAC close entry. No suppression, observer/reporting error or denied operation obscures the evidence. Timeout checks bracket the synchronous native call; a separate lease thread remains visible. Serial dispatcher source supports the downstream queue explanation. The report correctly avoids claiming every historical browser problem shares this cause or that thread presence proves each heartbeat DB write.

All 35 source/evidence pins match before, after and current bytes. Tracked product diff and index are empty at review. At 75-second ETEAC cap the supervisor terminates only its verified PID73/start8146371/session73 group, reaps it, records no owned leftovers and 0.008175488-second cleanup. Total diagnostic time is 81.62271104 seconds. This is diagnostic truncation, not native timeout/cancel success or product completion.

## Issues

Critical: none. Important: none. Minor: none. Static findings R396-I1 and R397-I1 remain resolved.

## Delivery approval

Approve exactly the unchanged candidate payload plus its three listed metadata paths: candidate-manifest.json itself and reviewer-generated review/code-review.md and review/code-review.json. Executor may freeze the actual metadata bytes/hashes after this write; do not rewrite payload or introduce hash self-reference. DB/WAL/SHM, generated runtime raw, caches, tmp, nested gitlinks, old trace duplicates and before-driver snapshots stay excluded. This selected evidence is not a complete remote reproduction package. Original single commit/push/exact-remote verification and total time limits still apply; this review does not claim delivery has happened.

## Declined to judge and acceptance boundary

- Product repair correctness and full browser/formal research acceptance: no such work was requested or performed.
- Original R377 internal stack or every historical failure's root cause: no original internal stack; current replay strongly supports common cause only within the stated inference.
- Actual commit/push/remote equality: must be confirmed after delivery; reviewer performed no network or Git write.

The causal report, acceptance and step report respect these limits. Only this current replay diagnosis and exact selected evidence delivery readiness are approved. No product code was changed, runtime repeated, SQL opened or original evidence edited during review.
