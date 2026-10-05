# Verifier association fix round 1

Status: READY_FOR_INDEPENDENT_POST_FIX_REVIEW; actual episode NOT_RUN. Three P2 findings/four independent counterexamples are corrected in the verifier only. Full saved/index JSON equality, terminal and measured source identity/time, capture clock containment, and action ownership derived from all complete spans now reject the mismatches.

Qualified CPU RED preserved: eight variants were accepted before correction, while the complete baseline passed. Final bounded CPU GREEN: 27 passed in 0.51 s (17 recorder + 10 script cases); scoped Ruff/AST passed. All authority remains blocked.

The initial verifier/header/manifests/reports and exact REQUEST_FIX are in `baseline`; initial source-before archive and 68 protected original files remain unchanged. Future execution pins now reference 32 files/408064 bytes, reusing 31 unchanged archived inputs and the corrected verifier in source-final. `execution-archive-index.json` resolves all 32 and all live/archive hashes match. Runner/controller/backend/teacher/module/old raw inputs are unchanged; no actual invocation or attempt directory exists.

Final verifier SHA256 `19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f`; runner `addc33e7031bdeb55d03a476b9d4c1ad97a789c43251ac1be79ff53c5596537a`; future source manifest `1b51ff53e4c40cf9943dcfcfe68e835ad95e0228315b51a3cf2285089c058aaf`; future header `51a1adb25759a3a9d46583cf84eb351de5bdcb72d083863bf709d15751bd387d`. Independent post-fix review is pending; original READY/REQUEST_FIX history is retained.

Independent post-fix review: **PASS in the bounded excluded teacher association scope; all three P2 findings CLOSED.** Ten CPU checks passed in 0.44 s. The complete baseline verified; all original four and new four binding mismatches plus the camera-clock variant were rejected. Review: `../independent-runner-fix1-review.md`, SHA256 `d8aab41c9e95a24f488ffc53a97db1e6c307f114732f9db9a5bce51bf34dd307`. Initial REQUEST_FIX review, original source/archive/report bytes and module review are preserved.

Final current status: REVIEWED_SCOPED_PASS_ACTUAL_NOT_RUN. Source/header/manifests stay quiet for root’s separately reviewed sole actual invocation. Actual source authenticity, native/formal admission, between-step and future stability remain unavailable; no episode has run.
