# Ubuntu authoritative deployment plan

Goal: preserve the latest research architecture and migrate Phase13 onto macOS/Sim2Real/thesis lineage.

Safety: no controller contact, hardware writes, servo enable, brake release, or real dispatch. Historical artifacts are immutable. New outputs use unique directories; dirty results are exploratory.

- [x] Fetch all branches and tags; verify supplied SHA and topology.
- [x] Create codex/ubuntu-integrated-deploy from origin/codex/macos-local-dev.
- [x] Review four Phase13 commits; cherry-pick without replacing current CI/thesis.
- [x] Record system and Git inventory; distinguish host GPU from sandbox visibility.
- [ ] Install isolated Python and Node runtimes using declared versions and lockfile.
- [ ] Run Python formatting/lint/mypy/full pytest and Phase13 tests. Diagnose actual failures.
- [ ] Run all dashboard gates including Chromium E2E.
- [ ] Validate MuJoCo assets, adapter, workers, deterministic DR and physics application.
- [ ] Run core phase verifiers into independent evidence directories.
- [ ] Prepare ROS Jazzy/MoveIt; build workspace and planning-only acceptance.
- [ ] Prepare official Isaac Sim 6.0 external runtime and Isaac Lab; run startup/adapter.
- [ ] Run paired MuJoCo/Isaac experiments only if real Isaac runtime works.
- [ ] Validate offline Rerun and Sim2Real APIs/gap report; S3/S4 remain locked.
- [ ] Check model providers, fake smoke, available real provider; isolate fake metrics.
- [ ] Run Phase12 smoke pipeline, then full if resources permit.
- [ ] Rebuild thesis in separate output; verify evidence/references/claims/figures.
- [ ] Add Linux wrappers reusing existing entry points, doctor, startup and test verification.
- [ ] Record final dependency/disk reports and accurate subsystem acceptance.

Review focus: non-ASCII ROS build path; sandbox-hidden GPU; missing sudo; unavailable model endpoint; invalid model output cannot imply task success.
