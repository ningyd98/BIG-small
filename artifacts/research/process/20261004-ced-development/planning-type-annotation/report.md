# Planning sufficiency annotation

The resource release's cold mypy run exposed a pre-existing inference error: the first branch assigned a string to `insufficiency`, while `check_scene_sufficiency` returns `str | None`. Root added the explicit local annotation. Five inherited E501 lines were wrapped without changing their strings or control flow. The AST is identical to the saved baseline after removing the new annotation.

Cold mypy for the source file and Ruff pass. The two existing planning suites pass: 47 tests in 1.59 s. Four warnings remain in that run: existing Starlette deprecation and a dry-run negative test's missing-DISPLAY/renderer-cleanup warnings. That test returns an unavailable dry run; the result is not renderer acceptance. No successful capture, model request, controller command or task action occurred. There are no new tests that mirror the annotation.

`baseline.py`, `baseline.json`, `source.py` and exact check logs are preserved. Updated source SHA256: `9545baf29af3fe5388565283cd3fa7e196f78a0071d9129729d3e0d665ed8d75`. Scope: SOFTWARE_ONLY; no actual research gate is opened.
