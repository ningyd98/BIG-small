# SDD ledger — plan: artifacts/research/process/20261004-ced-development/astra-rounds/round-gemini-subpix-marker-ambiguity-review-20261115/plan.md

Authorization: 用户于本轮回复“开始”，授权阶段1–3实施；不授权公开push或新增Sol/Molmo付费实验。

Pre-flight: one marker implementation task, no internal task interfaces. Stage3 consumes the completed marker implementation under a separate Astra plan.

Ruling: 原计划的PLAN_ONLY约束描述规划轮次；用户最新“开始”已授权未来实施。保留原计划字节，执行状态记录在本ledger。

Ruling: 使用新托管工作树并复制8项Gemini修改，591项仓库源码哈希与V3逐字节一致；原工作树和冻结实验保持原状。阶段3以V3的27项成功为回归基线。

Environment note: MCP命名空间的worktree状态查询无法识别native操作；用native状态和附件清单确认创建完成，没有重试创建。

Stage1 baseline: 594 actual source/input files archived and verified; 591 repository files and all8 dirty files reproduced in isolated tree; baseline nine-file pytest 335 passed in11.65s.

Task1 RED: 3 expected identity failures plus1 unplanned 14px absolute-yaw fixture failure. Original source remains unchanged. Pause affected implementation for fresh Astra plan. Raw unified-diff whitespace diagnostics preserved; no frozen artifact bytes will be cleaned. Shell writes to attached worktree need approved escalation; apply_patch is available.

Task1 amendment: Astra round-small-marker-rotation-fixture-20261115 replaces only14px absolute-yaw claim with independently fixed corner quadrants; existing48px test byte-identical. CorrectedRED3failed10passed. GREENpose33passed; nine-file348passed11.68s; Ruff/source whitespacePASS. Production thresholds/safety unchanged. Full-project run pending.

Stage3 Astra: round-v3-offline-27-regression-20261115 copied and38 immutable inputs verified. Chosen original worker/planners with two frozen external output boundaries; no runtime core/AST whitelist changes. Phase2 commit3ef1e028,348 scoped testsGREEN.
Task 1: complete (commits 57c4dc0..8ebad9f, tests: /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/bigsmall-subpix-final-contract-20261115 tests/test_finger_limit_fix.py tests/test_finger_limit_verification.py tests/test_sol_molmo_component_safety.py tests/test_visible_cuboid_geometry.py tests/test_opencv_target_evidence.py tests/test_pose_marker_evidence.py tests/test_pose_marker_visibility.py tests/test_cloud_vision_fallback.py tests/test_molmo_grounded_planner.py -q → 348 passed in 11.72s)

Stage3 plans: actual gpt-6-astra plans and narrow amendments govern role config version2, optional fixed scene, render environment, real safety injection, POST internal PRE counting, frame labels, baseline anchoring, process-wide network guard, full source inventory, output roots, post-cloud phase identity, and final SQLite status verification. Historical RED/unplanned failures are retained in the corresponding plan evidence.

Final review: fresh-context gpt-6-astra astra_offline_code_review. Original seven findings R1–R7 resolved with negative controls and actual-boundary tests; independent-final-code-review.md/json preserve the final disposition. No remaining known scoped code blocker. No deferred minor finding.

Stage3 software: final pure plus existing planner tests 228 passed /11 deselected; real boundary/network nodes 11 passed /85 deselected; original worker/finger/safety tests64 passed. Full repository pytest remains INCOMPLETE:600s timeout exit124, five observed failure markers around2%; no full-suite PASS claim and no unrelated repair.

Stage3 final: original27 fresh-worker offline replay27/27 (fixed10/development9/old held-out8), each one successful attempt and released lease. Final read-only checker02 exit0:141444 physical samples rescored,4806 evidence files verified,432 real PRE/POST checks,540 newly rendered closed-loop frames,599 source items per case unchanged,three entry SHA unchanged,zero new experiment model/network requests. Frozen589 frame audit has zero marker/geometry differences and zero new grounding rejection.

Ruling: do not equate final event with final state — actual Astra final-status plan validates unique successful job, last nonempty status event and job_completed while retaining following artifact_created and every original event; an incorrect event interpretation would invalidate the final evidence gate.

Ruling: preserve all frozen errors and this ledger instead of deleting the skill workspace — user AGENTS preservation requirements take precedence; the cost is retained local scratch, not lost evidence. A tracked ledger snapshot is in delivery/.

Ruling: local commits only, public push and new paid Sol/Molmo runs deferred by the user — any contrary assumption would disclose public material or incur unauthorized experiment cost; neither action occurred.

Ruling: shared editable environment must pin this worktree with PYTHONPATH before imports; matching offline renders require the approved execution environment and EGL initialized before MuJoCo import — otherwise the wrong source or different image can invalidate binding. No rendering, MSAA, controller, evaluator or safety threshold was changed.

Ruling: retain the full-project timeout and five failures as an open verification gap — scoped GREEN cannot establish repository-wide health. Remaining13 V3 failures and new-seed generalization are outside stages1–3; assuming them solved would overstate the research evidence.

Stage1–3: complete within authorized scoped contract; global repository verification and research acceptance remain open. Baseline594 original inputs unchanged and415 active SHA256SUMS entries verified at final delivery. Historical superseded manifest is preserved with its already documented non-self-contained relative references.
