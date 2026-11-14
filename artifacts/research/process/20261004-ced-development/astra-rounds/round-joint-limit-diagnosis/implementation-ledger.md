# SDD ledger — plan: /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-joint-limit-diagnosis/plan.md

Base: 23d2f2780571138ea2ec7061696c06b756cb7ac9. Existing isolated linked worktree, codex/molmo-flat-interior-20261111. No tracked edits at start.

Scope: diagnose three historical hard-limit samples with zero model or cloud calls. No controller, evaluator criterion or dataclass changes. Preserve original evidence bytes and original plan.

Pre-flight interface: step 1 writer consumes live PhysicsStepObservation; step 2 must rerun physics, since stored PhysicalSample has no joint values. Step 3 consumes writer JSON plus replay fidelity and online coverage evidence.

Ruling: online check reads seven arm joints at 1e-6 tolerance; independent evaluator includes two fingers at 1e-4. The plan's “both nine and same tolerance” statement contradicts frozen source. Compare actual implementations without changing either.

Ruling: backend SHA256 is d6bf8cc360328187ee7bf6c5b3fb78149b4e4302ee7380e2c4a3fcd7fabae452, matching latest user correction. Use current tested runtime, not the plan's stale commit 025c5389.

Ruling: freeze_evidence is not in the live component callback. Add a standalone opt-in diagnostic writer there and call it from the offline replay script, leaving production execution untouched.

Ruling: replay recorded resolved actions/contracts through the existing executor/controller; do not call models, derive actions from truth, or attempt to recover joint numbers from compressed old samples. Compare full recorded physics evidence and action step boundaries, not only violation counts.

Ruling: create a new output root, never append diagnostic files inside frozen original episode directories. Original files are rehashed before/after.

Ruling: A/B/C can remain unconfirmed or mixed. A large finger excursion in metres is not proof of an unreachable arm trajectory in radians. Do not use the plan's already-checked B example as a conclusion.

Ruling: external plan uses Chinese steps rather than the skill's Task parser; retain this ledger with explicit per-step commands/results rather than rewriting the original plan for tooling.

Baseline: component safety and full-horizon sampling tests: 23 passed in 1.70s, existing .venv Python, no network.

Tasks: 1 diagnostic writer and tests; 2 deterministic recorded-action replay; 3 evidence-backed A/B/C analysis; 4 source/original integrity, regression, whole-change review and delivery.

Task 1: complete. Initial eight missing-feature tests failed; writer tests now cover finite values, units, bounds, accumulation, corrupt structures and normal no-write behavior.
Task 2: complete. Final three-case replay reproduced 5137/5607/2974 physical samples exactly except fresh episode ID; all action boundaries and 5/54/426 violation steps match. Original sample manifests and 584 bound files rehashed unchanged.
Task 3: complete. All cases support A for missed finger monitoring; arm violations not observed. Overshoot dynamics and relationship to GRASP_LOST remain unresolved.
Final review: one fresh gpt-6-astra review. Three findings reproduced with 16 failing tests plus three units/structure negatives; one fix pass; final related suite 190 passed in 3.41s, Ruff clean. No second independent approval claimed.
Task 4: validation complete. Bare pytest --maxfail=1: 94 passed then unchanged Chinese-docstring audit failure; baseline HEAD source independently reproduces seven missing docstrings. No controller/evaluator/dataclass changes, model calls, cloud requests or hardware dispatch.
Final: Ruling: follow existing AGENTS commit/push direction on the current research branch; no main merge or PR, and explicitly retain the independently reproduced unrelated full-project baseline failure rather than claiming all-project green.
Final: Ruling: external plan is not the skill Task/Review Focus format; the precise working-change review package explicitly includes new untracked files, source plan, ledger and actual outputs instead of an empty HEAD..HEAD diff package.
