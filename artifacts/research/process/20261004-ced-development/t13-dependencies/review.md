# T13 dependency graph independent review

Verdict: **PASS for the released graph-only scope**. No blocking counterexample found. This does not close T13, enable LOCAL_RECOVER, or accept actual recovery execution.

Reviewed exactly `src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py` and `tests/test_visual_local_repair.py` against their two-file immutable `source-hashes.json`/`source/` snapshot. Both saved and working copies match the registered SHA256 values. Base/head remains `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. Read original roadmap Task13 at `docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md:387` and v2 T13 at `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:182`. Root explicitly restricted this handoff to the dependency graph; its broader implementation report was still forthcoming during review. No production/test/shared-document changes were made.

The module preserves the exact StepDependency and RepairWindow positional contracts and adds optional keyword parameters for current plan/command versions to `find_repair_window`. Omitting them fails closed; it does not fabricate versions absent from StepDependency. Versions reject Boolean, negative, missing, and zero command identities.

The graph requires unique ordered step identities and earlier dependencies, rejecting missing/forward/cyclic references. Input dependency/evidence sequences become immutable copies. Invalid evidence propagates through dependents, including through a completed step, but only unfinished affected steps enter replacement. Completed effects remain preserved even when their own evidence is invalid, disconnected pending steps remain preserved, and a physical effect ID cannot be reused under another step identity. Unknown invalid evidence yields an empty replacement. Replacement/preserved identities stay disjoint, unique and ordered, and first_affected agrees with the first replacement.

The docstring correctly describes a candidate window. Fresh confirmation of preserved effects, separately identified compensation, online evidence/safety checks, budget/restart lifecycle, stale-patch rejection, stage/ACK/CAS activation/resume and actual execution receipts are outside this module. The graph supplies no proof that those gates passed and has no dispatch or robot/model entry point. Keeping LOCAL_RECOVER disabled until those integrations and real recovery acceptance are complete is consistent with this review.

Independent validation:

- `.venv/bin/python -m pytest -q tests/test_visual_local_repair.py`: **14 passed in 0.14s**, exit 0.
- Ruff on those two files: **All checks passed**, exit 0.
- Temporary CPU check enumerated **4096** combinations of four-node ordered DAGs, completion masks and one invalid evidence seed, comparing replacement/preservation with independently computed graph reachability; all matched.
- No network/provider/model/GPU/render/physics execution, actual recovery, broader project suite or physical acceptance was attempted. Software checks support only this graph contract.
