# Astra 源漂移负控夹具签名修复计划

模型：gpt-6-astra；HEAD：`5a5b47baaa1b2136295a6281308b0e71091a90fa`；仅测试夹具计划。

Correct EGL environment replay: 1 failed, 2 passed; source-drift fail_gate=2 stops with unexpected diagnostic keyword before intended second source gate.

TypeError: test_authority_source_drift_stops_before_construction_or_action_dispatch.<locals>.<lambda>() got an unexpected keyword argument 'diagnostic'

Workflow-only _collection_guard stub accepts positional *args only, while existing product _collection_guard has keyword-only diagnostic=None and caller passes diagnostic=diagnostic. Baseline reproduction was reported by Sol; local raw result confirms PRIMARY collection_body TypeError. This is fixture API drift, not active-check repair evidence.

## 范围与同根因核查

- Only workflow fixture in tests/test_native_single_teacher_release.py; _collection_guard stub must accept actual keyword-only diagnostic=None (prefer explicit signature), retaining nullcontext behavior.
- Audit same fixture check_sources/record_failure/freeze and context-exit stubs against production call signatures. Current inspected source calls check_sources(expected, marker_family_id=..., protocol_schema=...), record_failure(phase,error), freeze(), __exit__(type,error,traceback); fixture already accepts these. No further proven signature mismatch. If same fixture needs extra production keyword compatibility, match exact signature only and retain assertions; unrelated failures require new Astra plan.

## 实施与验证

- Recheck input source SHA and preserve original raw evidence without rewriting. Product source may carry independent active-check edits; no product edit authorized here.
- Apply minimal fixture signature repair. Preserve every existing outcome assertion, two source gates, zero dispatch/actions, UNKNOWN and non-admission, final lifecycle and owner closure. Do not catch TypeError or alter expected failure text to mask issue.
- Run both source-drift parameters, then three previous EGL replay targets with PYTHONPATH=src MUJOCO_GL=egl PYOPENGL_PLATFORM=egl using existing project Python. Preserve RED and GREEN logs and exit codes.
- Run full test_native_single_teacher_release.py plus targeted fixture lint; record software-only results and source hashes. No physical/real research trial.

## 验证目标

- tests/test_native_single_teacher_release.py::test_authority_source_drift_stops_before_construction_or_action_dispatch
- tests/test_native_checkpoint_diagnostic.py::test_checkpoint_actual_dispatch_captures_fresh_sqlite_read_and_cannot_resume
- tests/test_native_whole_action_diagnostic.py::test_whole_action_dispatch_preserves_real_early_veto_and_exclusive_claim

## 前置

- Use installed project Python and importable source; EGL environment before any MuJoCo/OpenGL imports. Confirm original replay node for whole_action test via pytest collection, do not guess.
- Workflow fixture retains no real sensors, camera arrays or physics operations. Test-created temporary artifacts are software fixtures only.

## 禁止

- No product, source admission, watchdog, 8s gate or historical bytes changes. No actual collection launch or push in this delegated task. No absolute private paths in public plan; private evidence aliases resolve by original SHA.

## 验收

Both source gates fail specifically with synthetic source drift at intended gate, all original no-dispatch/admission/cleanup assertions unchanged and passing; previous two EGL controls remain passing. No runtime speed, source qualification, physical stop or formal admission claim.

## 原始输入 SHA256

| 相对路径或私有证据别名 | SHA256 |
| --- | --- |
| `tests/test_native_single_teacher_release.py` | `aaaba329de9935b22f21af17311c0ff8199ab95555f329ebc756f84743d0b9bf` |
| `src/cloud_edge_robot_arm/research/native_collection_application.py` | `d49b91b870d57ca0d4d3797312108cc7874df15aa74025aa17d491ad6972689e` |
| `src/cloud_edge_robot_arm/research/native_calibration_collection.py` | `8ceecd9239accabf1301b1dc035175f7fb1dce46456339cc2aac558d05dced13` |
| `private-evidence/three-env.log` | `d6a881e551cd57119121fa22988ce24c46da3ad9996975808ca736a1f5c4ed92` |
| `private-evidence/three-env/source-drift/run/collection-result.json` | `f597bfb79943b57d897dfcf1f3c80f8a486a8056ffdeafcbc500a32c6715d1a5` |
