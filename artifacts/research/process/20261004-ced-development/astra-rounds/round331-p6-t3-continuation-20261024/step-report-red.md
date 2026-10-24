# R331 exact RED gate

ROOT reviewed the full appended test source, runner/helper, existing startup prerequisite, fixture/argument/resource maps and finite migration matrix. All 267 frozen pins matched; all 254 original inputs other than the append-only test remained unchanged. R332–R335 source corrections were independently accepted before reservation.

The single R331:t3_red invocation completed with pytest exit 1 and nine expected assertion failures: four missing `remaining_app_seconds`, five missing `get_publication_summary`. JUnit reports zero errors/skips. All nine resource sidecars record no entered behavior and zero worker allocations. The prerequisite was accepted, source-before/after matched, raw hashes matched, and the owned process group was reaped. Runner elapsed time was 2.124711665994255 seconds.

`root-red-acceptance.json` accepts expected RED only. Both ROOT and AUTHOR RED ledgers are spent with no retry/reset; GREEN remains unused and held. `root-product-activation.json` releases original R331 Task 2 implementation to the same single Sol author. T3 behavior, complete B, C, native/physical and formal research are not accepted.

The current checkout also contains unrelated proposal-PPT planning artifacts and two pre-existing dirty nested physics workspaces. They are outside this delivery scope and remain untouched.
