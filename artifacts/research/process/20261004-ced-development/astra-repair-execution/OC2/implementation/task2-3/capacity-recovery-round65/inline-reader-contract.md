# Inline OC2 reader working contract

Owner is the existing implementer; this is not independent review. Static extraction used pinned RawV3 and native reader fragments plus approved round60/readiness.

- exact prereg schema/policy/config/source inventory/recipe/scene bytes
- application/source-session/OC1 domain/worker job/run/lease/attempt/fencing historical joins
- all boundary operation IDs BEGIN/MARK/END and original S BEGIN/END including RESET old/None to new
- backend ledger and D attempts bijection, nested capture own token, all frame allocations including failed
- legacy RESET journal/pairs remain MONOTONIC/UTC; new D never inferred from tuples
- RESET1, physics/control steps1..120, sole SETTLE0..120, explicit acquisition1, total actual CAPTURE3 for normal fresh recipe
- frame observation/camera/physics/pass-state hashes and persisted RGB/depth/mask/instance/source metadata SHA+bytes
- current receipt after original acquisition MARK, same D owner/event links, integer age=max(0,nminus-cplus)..nplus-cminus; TTL upper<=5000000000
- cached return uses original source acquisition and bracket without new capture age
- manifest complete exact files, no missing/extra allocation/pair, no observer/audit/export/prefix failure or late event for positive completeness

Reader is historical only, recomputes from originals and SHA+bytes, rejects path/symlink/schema/allocation tamper, and never trusts PASS flags or restores live authority. Old R03 reader is not an OC2 verdict because it requires explicit acquisitions zero. Source completeness and five-second recorded age are separate.
