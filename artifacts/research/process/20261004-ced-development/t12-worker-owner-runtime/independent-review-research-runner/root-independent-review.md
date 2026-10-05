# Independent review: worker lease source and original-policy compiler

Verdict: **CHANGES_REQUESTED**. One reproducible P2 affects the documented lexical source-root guard. The reviewed software tests and static checks pass; this review grants no actual owner, publisher, METHOD, native, motion, physical or execution admission.

## Frozen scope and integrity

The reviewed original package has 774 sources with manifest SHA256 `f0c84833daf10c8378b8658155b4995b3e9451037cb85a61aa0a70ac155ccfa4`, original report SHA256 `37c79cefb6cc47a455bb9110fb34b71a8a5b82bde9b75c1abff7526fe8cf3791`, and 807 original artifacts with manifest SHA256 `120aba8a1b0c9fda92a2cc4b8c449fd35ce454301a3b2d6f9bd90d826303372c`.

All 772 exact owner-fix1 base sources match their original archived bytes and the unchanged base manifest `0271d4785ef84c7a4f5fdcf4efd0ded0e9baccec02f7351f04d7b9bde4a917d6`. The only additions are `src/cloud_edge_robot_arm/vision/worker_owner.py` and `tests/test_visual_worker_owner.py`. All 774 source bytes, 750 Python ASTs and 807 original artifacts were checked again after the review. No live source drift was found. The review used its own `/tmp/independent-worker-owner-774-6u0u5tvf` frozen overlay; no live dependency replacements were added. The `.venv` link supplied only the existing local Python environment.

No production, test, dataset, asset, collector, runtime integration or historical artifact bytes were modified. All new review evidence is in this directory. No simulator state, stepping, renderer, camera capture, controller, provider, model, account or network operation was performed.

## P2: normalization hides a lexical symlink ancestor

Location: frozen `src/cloud_edge_robot_arm/vision/worker_owner.py:253–255`, `pin_worker_source_inventory`.

The function computes `Path(os.path.abspath(root))` before checking the root and its ancestors for symlinks. `abspath` removes `..` components, so a supplied root such as `/tmp/.../alias/../realroot` loses the lexical `alias` ancestor before the guard examines it. The guard therefore accepts a root that contains a lexical symlink despite the documented promise that aliases are checked before resolution.

The saved SOFTWARE_ONLY probe creates a regular `realroot/source.py` with its actual SHA256 and a directory symlink `alias -> realroot`. A control call using `alias` rejects with `lexical source root/ancestor symlink rejected`. The call using `alias/../realroot`, with identical file bytes and a valid complete one-file inventory, returns the verified mapping. The source checksum succeeds because the normalized path points at the same regular file; checksum consistency does not enforce the separate lexical-root rule.

Reproduction from the independent frozen overlay:

```sh
PYTHONPATH=src:. .venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/t12-worker-owner-runtime/independent-review-research-runner/lexical-root-counterexample.py
```

The exact source and output are `lexical-root-counterexample.py` and `lexical-root-counterexample.log`. This demonstrates a source-binding guard bypass, not an actual permission or robot execution bypass. Preserve the supplied lexical root while examining all original components/ancestors, or reject noncanonical root components before normalization; then validate containment and current byte hashes. Add a qualified regression for a symlink followed by `..`, retaining the direct-alias control.

## Independent validation

The exact declared CPU command from `frozen-overlay-setup.json` completed with **278 passed, 3 skipped in 35.22 s**. The three skips are repository-backend variants declared in the frozen tests: SQLite-only transaction failure, memory-only concurrency, and SQLite distinct-connections. The separate new-module command completed with **37 passed in 8.99 s**. Scoped Ruff for the two new files, format checking for those same two files, and a fresh mypy cache for the one new module with `--follow-imports=silent` all passed. Exact argv and output are preserved in `setup.json`, `cpu.log`, `owned-cpu.log`, `ruff.log`, `format.log` and `mypy.log`.

The final `independent-matrix.py` exercised **27 SOFTWARE_ONLY probes** against the same immutable overlay. These cover current attempt rereading rather than stale attempt zero; pre-acquisition/pre-attempt time, expiry, naive time, boolean attempt, malformed state hash and lease subclasses; complete original contract aliases, immutable source maps, full eight-skill ordered graph, original condition semantics, calibration, sensors, tolerances, original timeout/retry/duration, minimum safe height and absolute deadlines; exact bound XYZ inputs with boolean, oversized integer, string, nonfinite and extra-axis rejection; original hash preservation and check-input-only output; changed source bytes, noncanonical/traversal filenames and direct root/file/ancestor symlinks. Expected rejection or preservation passed in each case. The distinct `alias/../realroot` counterexample remains accepted and is the requested change above.

The concrete repository reader and compiler outputs stay within `WORKER_LEASE_SOURCE_ONLY` and `SOURCE_BINDING_ONLY`. Original typed data, local repository status and caller-supplied consistency hashes are not independently authenticated publisher or clock authority. This package does not create the later actual worker factory, require a real source certificate, produce ActionEvidence, admit a physical command, establish METHOD, or report actual cloud usage/billing. The current `worker.py`, `evaluation.py` and `execution.py` integration remains outside this two-file scope.

## Retained review setup failures

The first counterexample write used an artifact path relative to the frozen overlay and failed before creating a probe; the corrected command used an absolute artifact destination. Two additional matrix checks initially used incorrect shared dataclass field names (`predecessor_step_ids` and `compiler_source_hashes`); their failed source/log copies are retained separately. A corrected matrix was also initially invoked from the repository workdir; that output is retained as `independent-matrix-live-setup.log` and is not used as frozen-review evidence. The final matrix was rerun from the exact immutable overlay. These are review setup errors, not product findings; `probe-setup-errors.json` records them explicitly.

Final source/base/artifact checks are preserved in `postcheck.py`, `postcheck.json` and `postcheck.log`. The historical owner release, original 774 source package, original report and original 807 artifacts remain unchanged.
