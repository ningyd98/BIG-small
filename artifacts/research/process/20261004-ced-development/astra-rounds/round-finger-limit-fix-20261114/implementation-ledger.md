# SDD ledger — plan: artifacts/research/process/20261004-ced-development/astra-rounds/round-finger-limit-fix-20261114/plan.md

Base: 52df1594ab888038adf7bd21586e691da671817c; reused verified linked research worktree. User supplied the detailed implementation direction; executing inline.

Pre-flight: Task 1 produces the guarded live check; Task 2 consumes it and must expect first-violation truncation.

Ruling: retain original diagnostic replay pins; build a distinct bounded verifier for the new guard. The old script must continue refusing changed runtime bytes. Cost if wrong: a new verifier could misstate faithfulness, bounded by exact-prefix comparisons and source hashes.
Ruling: no new paid or native model calls; use recorded-action replay and label 12 no-action records evidence-only. Cost if wrong: fresh planning behavior is not validated; no new end-to-end success claim is made.
Ruling: keep stricter arm tolerance, fixed finger tolerance and unchanged evaluator/controller. Cost if wrong: overshoot remains a stopped failure, not a recovered task.
Ruling: five actual visibility failures include two PLACE cases; GRASP_LOST is separate and one of the three finger cases. Cost if wrong: prioritization may be distorted; report original mutually exclusive terminal reasons.

Task 1: baseline 34 passed; new guard tests RED: 11 failed,17 passed. Failure is DID NOT RAISE ComponentStopped for both fingers, nonfinite readings and active-batch abort.
Task 1: complete (commits 52df159..52df159, tests: /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -B -m pytest -q tests/test_finger_limit_fix.py tests/test_sol_molmo_component_safety.py tests/test_joint_limit_diagnostics.py -p no:cacheprovider --basetemp=/tmp/finger-limit-task1 → 62 passed in 2.10s)

Task 2: verifier RED 16 missing-feature failures; GREEN 16 passed. First 40-case replay: all verified,28 action replays +12 evidence-only,20 retained successes,3 first-step stops at1189/1198/1777,485/485 frozen bad snapshots caught.119921 physical samples match required full/prefix evidence;6656 original case files including40 manifests rehashed unchanged. Six actual occluders remain refused; two normal controls retained and one table-edge refusal retained.
Task 2: initial broader suite reached650 passed then renderer initialization selected GLFW before a test set MUJOCO_GL=egl. Rechecking that node with EGL set before imports. Bare project check reaches94 passed then known unchanged encrypted_secret_store Chinese-docstring audit failure.

Final review: one fresh gpt-6-astra high review; no Critical or Minor findings, one Important original-runtime pin binding gap. Review source snapshot and input hashes are preserved before the fix.
Final: fixed original runtime source binding — nine RED tests then87 targeted GREEN in2.87s; final737-test suite GREEN in163.65s, no second independent review.
Final: Ruling: retain controller/overshoot,GRASP_LOST recovery,fresh model planning,existing arm tolerances,initial settling coverage,and baseline docstring audit outside this bounded fix; verify publication separately. Cost if wrong: those behaviors remain unresolved and this round cannot certify recovery,full-runtime safety,project-wide green,or fresh end-to-end success.
Task 2: complete (uncommitted changes based at52df1594, final-suite-command.json ->737 passed in163.65s; replay-v3 ->40 verified,485/485 caught,119921 exact physical samples,20 retained successes; original6656 files unchanged).
Delivery uses one explicit final commit; task1 tool range52df..52df records its pre-commit checkpoint, not separate task commits. No controller/evaluator/model/dataclass changes.
