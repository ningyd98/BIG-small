# Prepared whole-step RGBD runner

Status: READY_FOR_ROOT_INDEPENDENT_SCRIPT_REVIEW; actual episode NOT_RUN. Only artifact-local `run_once.py` and `verify_offline.py` were implemented. No production/controller/backend/teacher/prior-runner files changed.

26 scoped CPU tests passed in 0.40 s (17 recorder + 9 script cases); Ruff and AST checks passed. Qualified RED histories preserve seven missing-runner failures and all three association counterexamples before correction. The adapter verifies zero noise and unchanged exposed data/model arrays, model options, controller targets, RNG, cache/camera identity and step/command counts across the extra two-pass capture. Original methods and dwell delegate exactly once and restore in finally.

The exact 32-file source-before archive matches all live bytes (398949 bytes); all old 28 pins remain unchanged. Preparation GitHEAD is historical metadata only; execution gates exact source/scene bytes. New excluded group: `dev-marker-continuous-89852ec153489eeea846239a`.

The final recorder persists full observation JSON gzip1 with exact PNG/depth/mask base64, rather than duplicate member files. Offline replay validates both gzip and original hashes, raw member checksums, full step denominator and nominal action/command/control/actuator/physics/acquisition clocks. The decoder receives only saved RGBD plus exact outboard marker registration, after the action window. Setup remains explicitly offline and cannot fabricate raw-v3 RESET/completeness.

Actual capture/runtime/storage remain unmeasured. Original simulation-step budgets are retained; wall time changes. Between-step/future motion, calibrated bounds, formal/native acceptance remain unavailable. No actual invocation is authorized by this preparation artifact.

Code SHA256: runner `addc33e7031bdeb55d03a476b9d4c1ad97a789c43251ac1be79ff53c5596537a`; verifier `bec19e9c8d2b7141299bfcdab462d28e786e0f97ee0d0a26a8ba624e706bb42a`. Manifest `08bebf77fb36db8e521937ad5296b8e0471059b66a773633e6bccb6880fa6495`; header `da1a17c74414db46f26fdf5435d7e241b84cd70cdae9def7d66d69a911126795`. Full metadata, tests, rulings and source hashes are in `implementation-report.json`.
