# Marker association first independent review

Verdict: CHANGES_REQUESTED for the registered-source path guard. All results remain DEVELOPMENT_ONLY, NOT_ADMITTED, whole identity UNKNOWN and uncalibrated. The finding does not demonstrate native execution authority.

The exact 39-file manifest `a3e6b97a1a06651bde41cf64260d4009e9e9bd7e03e812aeb9668ff24e259614` and current listed bytes passed independent SHA256 and Python AST checks. The review copied only the previously frozen 768-file T8b fix3 closure plus these exact 39 overlay files into an isolated directory. No moving live source overlay, model call, renderer operation, new capture or controller command was used.

Independent verification passed: 91 scoped CPU tests in 9.61 seconds, Ruff and format for both owned Python files, cold mypy for the new module, and all frozen hashes after testing. These tests establish scoped software behavior and saved static-frame replay, not a complete observed physical object or continuous stability certificate.

Two additional read-only counterexamples reproduce one source-path guard defect. `MarkerObjectRegistration.sources_valid()` resolves its root before inspecting symlinks, so a registered root that is itself a symbolic link still validates and yields OBSERVED_CANDIDATE. `load_marker_registration()` checks only the final registry file for symlink status; reading the same file through a symlink parent directory also succeeds. The report states that symlink sources cannot validate, so these paths must reject before resolution. `root-counterexample-paths.py`, its log and `root-review-setup.json` preserve both exact results; admission remained NOT_ADMITTED and whole identity UNKNOWN.

Requested fix: reject symbolic links in the original root, registry path and their ancestors before resolution, preserve regular-file/hash/containment checks, add qualified negative regressions, and publish a separate fix snapshot. The first immutable source package and counterexamples must remain unchanged. No change to the detector, tracker, camera, controller, existing motion data or native pipeline is requested.
