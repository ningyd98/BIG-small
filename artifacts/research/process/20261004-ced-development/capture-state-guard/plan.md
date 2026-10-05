Bounded SOFTWARE_ONLY state-guard repair for a future new collector. Existing collectors, 32/33 source freezes, raw attempts, controllers, camera and Git remain unchanged.

1. Reproduce the legacy aggregate's false difference on changing legitimate null-allocation getters, and its acceptance of unknown owning arrays, using deterministic CPU fakes.
2. Extract solver/dual/island getter names, shapes and types from the frozen MuJoCo 3.3.7 header bytes. Validate exact header/binding pins and runtime version; do not import MuJoCo or invoke its APIs.
3. Capture each ndarray once and immediately copy bytes. Hash complete data-backed bytes and all structural/support records; known null-allocation storage is explicitly unsupported, never evidence of stable live values. Empty known fields retain structure. Unknown owning storage fails closed. Compare support, shape, dtype and inventory as part of the digest.
4. Expose a separate composition API which retains all required original model/options/controller/RNG/cache/camera/step/command/noise/time/physics protection and detaches the caller's payload.
5. Run bounded fake/original-snapshot RED→GREEN, Ruff/mypy/static checks and preservation hashes. Freeze small sources/logs/report for independent review; no actual acquisition or certification.
