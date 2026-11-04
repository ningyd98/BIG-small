# R426 rotated-vertex oracle correction Implementation Plan

> **For agentic workers:** use `superpowers:executing-plans` inline. Actual `gpt-6-astra` authored this plan after reviewing the new failure. No implementation, tests or Git mutation is performed by this planning turn.

**Goal:** Correct the R425 planner's incorrect 90-degree expected displacement, preserving the correct completion implementation and original failure evidence.

**Architecture:** Change only the existing `test_pointwise_sum_and_rotated_vertices` test node. Preserve both production modules and every other existing source/test byte. Add a mathematically independent 180-degree control inside that same node.

**Tech Stack:** Existing Python/pytest/Ruff; existing bounded validation supervisor.

**Spec:** R425 completion plan and R91 metric design remain frozen. This round supersedes only R425's incorrect numerical oracle for the 90-degree vertex rotation; no metric, physical threshold or acceptance semantics changes.

## Original failure and root cause

`R425/validation/green/stdout.log` reports 1 failed, 23 passed; the failing assertion at tests/test_native_completion_v2.py:86 expected sqrt(8) for each 90-degree rotated vertex but obtained 2.0. The bounded result reports exit1, no source drift or remaining live processes. Exact original paths and SHA256 pins are in plan.json. Original R425 plan, tests-at-failure pins and evidence must remain preserved.

For a vertex `(x,y,z)` with x,y in {-1,1}, a 90-degree z rotation yields `(-y,x,z)`. Squared displacement is `(-y-x)^2+(x-y)^2=2(x^2+y^2)=4`, hence distance2. A 180-degree rotation yields `(-x,-y,z)`, squared displacement `4x^2+4y^2=8`, hence sqrt(8). With p=rc=rt=original vertices and G=0, U=M=0 and C=L=endpoint distance. The product's math.dist calculation agrees with this independent derivation. The incorrect value came from the R425 Astra plan, not a physics implementation defect.

## Scope and exact change

Only modify `tests/test_native_completion_v2.py::test_pointwise_sum_and_rotated_vertices`:

1. Change its 90-degree point assertion to `assert result.point_l_m == (2.0,) * 8`.
2. Change its 90-degree maximum assertion to `assert result.completion_error_m == 2.0`.
3. Immediately afterward construct `rotated_half_turn = [(-x, -y, z) for x, y, z in vertices]`; invoke the same `completion_metric_v2` with G=0 and command/capture-reference/terminal-reference arrays all equal to the original eight vertices, and actual points equal to this half-turn array. Assert `point_l_m == pytest.approx((math.sqrt(8),) * 8)` and `completion_error_m == pytest.approx(math.sqrt(8))`. Also assert u_m==m_m==0 and endpoint_error_m approximately sqrt(8). Keep the preexisting different-point-maxima control intact.

No production API changes; no tolerance widening for the original wrong90-degree oracle. Do not edit R425 plan.md/plan.json or original RED/GREEN outputs. Round-local fresh manifest/spec/wrapper/step-summary evidence is allowed. Preserve legacy UNKNOWN, all numerical qualification thresholds and current research boundaries.

## Review focus

- Check the two rotations independently from the coordinate algebra, not by using math.dist itself as the expected-value oracle.
- The corrected assertion still covers all eight vertices with coincident centers, and the 180-degree control retains the original sqrt(8) nonzero lever-arm challenge.
- Both product modules and the separate calibration test file must remain SHA-identical to intake pins; no behavior change is hidden in this test correction.
- Preserve the original failed run as observed RED; do not rewrite or rerun it.
- All24 selected tests must pass in one fresh bounded run, retaining four legacy UNKNOWN/coordinate compatibility nodes.

## Implementation and validation

- [ ] Before editing, recheck every plan.json input pin and unchanged checkout/source context. Record the current test preimage. Any relevant drift or new root cause requires another actual Astra plan.
- [ ] Apply exactly the node-local correction and half-turn control. Format only the changed test if needed.
- [ ] Run ` .venv/bin/python -m ruff check tests/test_native_completion_v2.py` and `.venv/bin/python -m ruff format --check tests/test_native_completion_v2.py` once on the frozen changed test. Existing production Ruff/mypy results remain valid because product bytes are unchanged; no repeated type/full-suite check is required.
- [ ] Treat the already observed R425 1FAIL as this round's observed RED. Run exactly one full24 GREEN with the argv frozen in plan.json, through the R425 implementation/run_validation.py/R413 bounded supervisor mechanism redirected to a fresh R426 context and output tree. Do not first run the changed node separately: the incoming intake's suggestion of two runs is explicitly simplified by this plan to one grouped GREEN. No new RED invocation, profiling, per-node supervisors or R424 runner.
- [ ] Use a fresh immutable stage spec, changed-test/source manifest, stdout/stderr/JUnit/events and result paths under R426/validation/green. Keep unchanged R413/R235 prerequisites, empty tracing/profile channels, original stage process cleanup. Runtime budget remains600s with30s cleanup. No physics/render/network/model/hardware call. Pin the actual selected runner and all relevant stage inputs; an adapter may redirect ROUND/paths, never rewrite old artifacts.
- [ ] Require all24 passes with zero skip/xfail and no source drift/process leak. Record observed node denominator and original failure linkage. Root then requests one fresh combined R425/R426 review and exact-path commit/push with local/upstream/live remote SHA equality under existing authorization.

## Acceptance and boundaries

Accept only the corrected mathematical oracle and passing software evidence. Original R425 failure is still a real recorded unexpected GREEN failure. Product-source and unrelated-test SHA equality is mandatory. Any unexpected failure, timeout, environment error, relevant drift or broader required fix stops this correction and goes to the next Astra round; it is not absorbed by relaxing assertions.

Actual collection remains NOT_STARTED, native admission HOLD, formal research acceptance NOT_STARTED. Once accepted, continue the same T7b original-data producer/reconstruction entry already stated in R425; this round adds no runtime readiness claim.
