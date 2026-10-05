# R02-PIN-01 targeted independent re-review

Decision: **PASS_SCOPED_SOFTWARE**. The reproduced R02-PIN-01 defect is closed for persistent binary/source drift before subprocess result consumption. No new qualified defect was found in this targeted re-review.

The production diff is exactly one added `self._revalidate()` immediately after the real `subprocess.run()` returns, before any return-code or stdout consumption. Current live source SHA is `bccb34516d395f51554f4dd94a6fab8ee5def4cadbeebad5240688a76711fa0c`; test SHA is `647ad6bb338a488a2260dab9ab45e6b9eb7d7cfd72947d4db7f288254b9816f8`.

The initial review's exact script was replayed without changing its bytes (SHA `ac55f28aded5fe89ade390c6193e75b7de11088692c718f37d7a5c434646e7fb`). It now exits **0**. The unchanged official ELF positive control still gives **2 intervals and no reasons**. At the same final-B interleaving, the appended ELF has the exact original counterexample SHA `5c674edfa295231f0ec7888f04b94dc3b9c13675b4ee05cc2ec03104a057f3c5`; the corrected result gives **0 intervals**, with `pinned verifier binary changed`. The original script's printed `QUALIFIED_RED_OBSERVED` label remains intact, while its rejection assertion is now GREEN.

Independent checks:

- **20 CPU tests passed in 0.49s**, comprising the original 18 cases and two final-B drift cases.
- The binary and pinned `main.go` source drift cases both use transparent calls to the real Go process. Each records two real, successful draft08 subprocess results, then returns **0 intervals and a nonempty pin reason**. Each retains the healthy two-interval control. No stdout or signature verdict is fabricated.
- Owned **Ruff, format and mypy pass**; mypy has only its existing unused ament/rclpy config note.
- All **28 targeted before/after pins match**, including both live Python files, quiet fix report/manifest, preserved original R02 and initial review reports, and fixed Go source/fixture/binary/compiler/build metadata. The unchanged Go suite/build and full 101-file audit were not repeated.

Counts are not added to the author's runs, the initial review, or the overlapping exact-script replay. The author-preserved two-case RED was read; it remains unchanged. Full commands, outputs and the exact original script are in [independent-review.log](independent-review.log); all targeted hashes and results are in [independent-review.json](independent-review.json).

The scope and contract are unchanged. These remain SOFTWARE_ONLY signatures and conditional causal intervals: native authority and UTC calibration are `UNAVAILABLE`, issuer accuracy is unverified, and the 6-second fixture interval still exceeds the read-only default 5-second TTL. This pass establishes the finite pin-consistency fix, not actual UTC accuracy, native provider ownership or consumer deadline feasibility.

No UDP/provider/model/physics/renderer calls, calibration groups, downloads, Git operations, implementation edits or old-report/original mutations occurred. Only these three new fix-round-1 review files were written persistently. Test/cache files and isolated original binary/source copies used `/tmp`. The review does not itself authorize R03 execution.
