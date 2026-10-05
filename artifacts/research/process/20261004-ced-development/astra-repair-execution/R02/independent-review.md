# R02 independent software review

Decision: **REQUEST_FIX**, for one reproduced binary-pin boundary defect. This decision is restricted to offline software wire validation and conditional causal replay; it is not an actual clock, UTC accuracy, application-owner or native-admission verdict.

## Finding R02-PIN-01 — final B can return intervals after binary drift (P2)

`native_clock_source_v2.py:184-201` checks the binary/source pins only before `subprocess.run`. `verify_causal_slab:348-354` then accepts the final B diagnostics and returns all intervals without another pin check.

The exact counterexample in [independent-review.log](independent-review.log) first obtains the genuine two-interval positive control from an unchanged `/tmp` copy of the official pinned ELF. A transparent call hook appends bytes to that copy at the second, final B subprocess invocation, after the existing pin check, and invokes the original `subprocess.run`. Both request/reply originals and all subprocess outputs remain real. The pinned binary SHA is `930095fe5f13ab9522691fbedba1273f56a6a9f27823038093f4b99de7b6d313`; the actual changed ELF SHA is `5c674edfa295231f0ec7888f04b94dc3b9c13675b4ee05cc2ec03104a057f3c5`. The result still has **2 intervals, `reasons=[]`**. Immediately calling the same existing `_revalidate()` rejects it with `pinned verifier binary changed`. The rejection assertion therefore exits1.

This extends the author's existing appended-byte drift control only by moving its interleaving to final B. It introduces no fabricated signature verdict or new accuracy contract. Appending an ELF trailer leaves the real Go verifier runnable; this counterexample proves stale byte identity acceptance, not a cryptographic forgery. The original binary and all sources remain untouched.

Requested fix: revalidate the frozen binary and source inventory after the real subprocess completes, before consuming or returning its diagnostics. Persistent drift during A or final B must give nonempty reasons and no intervals. Retain the healthy two-pair positive control, detached originals, explicit draft08 and SOFTWARE_ONLY authority. This is a finite source-consistency guard; it does not require resistance to arbitrary code execution inside the trusted process.

## Independent checks

- Python original suite: **18 passed in0.38s**.
- Owned Ruff, format and mypy: **PASS**; mypy has only the existing unused-config note.
- Fixed Go1.22.2, `GOTOOLCHAIN=local`, `GOPROXY=off`: **6 top-level tests and25 parameter subcases passed**, `go vet` and offline build passed. No SDK/dependency download or `@latest`.
- A `/tmp` rebuild with the original trimpath/buildvcs flags has the **same SHA** as the quiet binary.
- **1 new qualified RED** is separate from the repeated original suite. Counts are not added to the author's or historical overlapping suites.

Commands, complete outputs and the exact RED script are in [the log](independent-review.log). Full before/after hashes and machine-readable results are in [the JSON](independent-review.json).

## Contract and evidence boundary

Code inspection and the independent original tests confirm explicit sole draft08, strict original framing/length and ordered unique tags, 32-byte nonce and official chained request creation, wrong key/context/delegation rejection, consumed INDX bits, seconds conversion, timeout rejection, detached pair/exchange aliases, unique ordered pair inventory and same-domain `A.verified_after <= pair.before <= pair.after <= B.send_before`. B binds A's original reply plus the complete declared pair slab and acquisition digest. R2 accepts a caller-supplied journal digest for conditional replay; actual journal ownership/completeness remains the R03 collector/publisher's task. The remaining source-consistency failure is R02-PIN-01 above.

The fixture interval is `[1699999998000000000,1700000004000000000]`ns. Its **6-second** width comprises2s midpoint separation,1s radius per endpoint and1s quantization padding per endpoint. It exceeds the read-only default ordinary TTL of5s. A finite signed interval does not establish issuer accuracy or consumer feasibility. Actual consumers must use conservative `now_upper-observation_lower` against the unchanged TTL/condition ages, and compare `now_upper` plus the authenticated full completion horizon with the unchanged validity/task/verification deadlines. No RTT/2, NTP substitute or threshold change is implied.

## Preservation and scope

All **101** fixed files match their before hashes, including the three supplied quiet report pins, owned Python/test, complete fixed Go source/binary/compiler inventory, historical logs and all21 RESET design inputs. The original14 missing-module RED, two Go RED rounds and author's alias RED were read and preserved. No implementation, original, root document or Git mutation occurred.

This review made0 UDP/provider/model/physics/renderer calls, acquired0 calibration groups and downloaded0 toolchains/dependencies. `native_authority` and `utc_calibration` remain `UNAVAILABLE`; issuer accuracy remains conditional. Persistent writes are only `independent-review.md`, `independent-review.json` and `independent-review.log`. Operational caches/builds and the isolated ELF counterexample used `/tmp`.

R02 remains pending this targeted software fix and root's subsequent decision. This report grants no actual/native or UTC-accuracy upgrade and authorizes no R03 execution on its own.
