# Task2 independent CPU review

**Decision: REQUEST_FIX.** Reviewed only the three new Task2 files and their necessary source contracts. No author source/test/report, Stage51 material, raw calibration artifact, header, archive or Git state was modified. No renderer, physics, cloud, model or hardware operation was run. This review creates no native source or calibration admission.

## Qualified finding: P2 component identity collision drops UNKNOWN

`src/cloud_edge_robot_arm/research/native_geometry_calibration.py:561` and `:565` key the geometry/action score dictionaries with `"|".join(component)`. Registration validates distinct group IDs but permits `|`. Thus distinct connected components `("a", "b")` and `("a|b",)` have the same key.

The bounded SOFTWARE_ONLY probe calls the real `reconstruct_registered_calibration()` aggregation, replacing only registry revalidation and per-group reconstruction to isolate this arithmetic. Eleven assigned groups form ten independent components. The unavailable `("a", "b")` component is overwritten by the finite `("a|b",)` component. The actual diagnostics report ten independent components but both quantiles report `group_count=9`, `rank=9`, `bound_m=0.001`, no unavailable IDs. A collision-free oracle retains ten components, `rank=10`, one unavailable score and `bound_m=None`.

This violates the required complete denominator and infinity treatment independently of whether current native originals exist. Use unambiguous component encoding or stable component indices for both geometry and every action; check that quantile counts equal reconstructed component counts. Retain the failing component. Add a meaningful regression for these valid IDs and unavailable propagation. Do not fix by deleting the failed component or shortening the denominator.

Evidence: `task2-independent-formula-probe.py` and `task2-independent-formula-probe.log`. The primary reviewer independently reran the probe with exit 0 and identical counterexample output. This probe is an isolated algorithm counterexample, not an end-to-end genuine source fixture or a native admission demonstration.

## Bounded additional consistency observations

`task2-independent-source-link-probe.py/.log` reuse the existing complete SOFTWARE_ONLY RawV3 fixture and the real registry/source reader without monkeypatches. Reconstruction still returns group status COMPLETE with only `clock_mapping_unavailable` when:

- An original identity declares the current backend producer path with SHA `f` repeated 64 times while the registered current producer SHA differs.
- The original identity asset SHA differs from the registered marker asset SHA.
- The registry declares preregistration in 2099 while original clock pairs are in 2026.

These show that existing reader checks do not join original producer/asset metadata or preregistration chronology to the current registered recipe. All probe data stay SOFTWARE_ONLY and all bounds stay unavailable. They do **not** demonstrate a native-source bypass, and do not establish that a future independent authenticated publisher would accept those captures. The future genuine app-registration positive fixture must check those consistency joins and authoritative assignment/history originals; public schema fields alone cannot establish provenance. These observations are retained for that closure and are not counted as a second qualified finite-bound counterexample in this bounded review.

The static review also observed that calibration scores use the registered horizon terminal while online support admits shorter current horizons, and that offline truth goals hardcode clearance/minimum height while owner reconstruction accepts a policy. Those remain unverified candidates, not additional qualified findings. A future positive fixture should resolve exact horizon/recipe applicability rather than assuming it.

## Verified scope and remaining evidence

The eight-vertex/contact/TCP error formula, marker attachment inverse transform, connected-component union and scalar conformal function were inspected. The scalar function correctly uses `ceil((n+1)*0.9)` and unavailable scores as infinity; the defect is the score-dictionary construction after component reconstruction. Shared validity masks are excluded from joint RGBD fingerprints. RawV3 revalidates assigned frames/actions, actual upcoming actuator n, joined originals and owner receipts. Failed/unknown raw records remain unavailable in the normal tested path. Application source construction checks exact source/role types, actual executing repository root, the fixed owned index and separately pinned catalog; no such real index/catalog currently exists.

Independent checks: **33 new Task2 CPU tests passed in 12.68 s**, Ruff passed, and mypy passed for both modules. The author's 184 affected tests already include the new 33; no broad suite was repeated and the counts are not additive. Exact command evidence is in `task2-independent-checks.log`.

No genuine raw/authoritative app-registration positive branch was exercised. There are still no actual app-owned native config/index/catalog, independently authenticated UTC acquisition originals, nine genuinely independent supported calibration groups, or genuine native finite publication. A development episode or nine seeds of one connected source component cannot replace those groups. Required actual basic calibration, conditional finite-branch verification, future contact/mutable reference evidence, consumer integration and scoped real validation remain work after the software fixes. This review and green CPU tests cannot replace them.

Audited input SHA256 values, rechecked unchanged at completion:

| Input | SHA256 |
| --- | --- |
| vision/native_calibration.py | 420a587d75ebfba35ff9d3ceccec6287ec411c9ada125aa90b63c6ac54632f12 |
| research/native_geometry_calibration.py | 5b438aeac0ee74da829b40fcda2d822afa34950ec8c09b9bdb864de8da5f7695 |
| tests/test_native_calibration_source.py | 865771b8db94b7cee1bc33ca63a420eae18b4e3164e643c94c56c0604468b19c |
| task2-implementation-report.json | 84d5e81bc167cd56897981abdeb575f03ed19b250a9077fd22fcc00379003cfa |

The supplied HEAD identity was 501a902405d35d9b7921d402ef44e30b7f3c2f4f. It was not independently queried because all Git operations were prohibited.
