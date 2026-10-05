# Independent provider usage fix1 review

Verdict: **PASS for the bounded software metadata reader**. The three original P2 findings are closed. No new concrete blocking finding was identified. This verdict provides no remote-origin, billing, model-role, INITIAL or physical acceptance.

Reviewed `report.md`, the approved reader/billing design, original immutable 770-file release, and the new immutable manifest `2e84395d6c062f9eb747025aee972afc4c521fcaf26327273d86460d24fc5dcb`. All 770 archive hashes and Python ASTs matched. Exactly the two owned files changed; the 768 frozen base entries remained identical. `independent-incremental-review.diff` compares the two releases directly, supplementing the package's creation diff.

## Findings closed

The unchanged original nine-probe script was run from a separate frozen overlay. Missing/error/foreign/chunk response objects now return UNKNOWN with nullable tokens and preserved denominators. Correct synchronous `chat.completion` remains OBSERVED. Empty inventory now returns UNKNOWN with 0/0 attempts, and all-unsent returns UNKNOWN with 1/0 attempts. Input text70+image70 under prompt100 and output text40+audio40 under completion50 now return UNKNOWN. The original first-round negative evidence remains untouched.

Additional typed fixtures confirm that an `error` member is unsupported even when null. Valid input text60+image40 with cached90 still returns the literal parent100, rather than incorrectly adding cache to modalities. Output text40+audio10 with reasoning30 still returns completion50 and reasoning30, rather than adding thinking twice. Currency remains null, billing UNAVAILABLE and scope ORIGINAL_PROVIDER_USAGE_METADATA in every probe.

## Modality scope

The [official compatible Chat API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions) documents the modality detail fields and that reasoning is contained in output text. It does not explicitly establish a four-field sum equation or mixed image/video non-overlap. The implementation and fixed report correctly describe the sum check as conservative parser sanity. A mixed image40/video40/text20 fixture under prompt100 reports only literal parent token metadata; an image80/video80 fixture under prompt100 returns UNKNOWN. These results are preserved in `independent-boundary-probes.log`.

OBSERVED for the former is acceptable in the declared narrow scope: the reader outputs no modality allocations and creates no verified modality decomposition, tariff, token cap, quota guarantee or currency value. UNKNOWN for the latter is conservative unsupported metadata handling, not proof of an official provider-schema or billing violation. No concrete authoritative counterexample was found requiring an additional mixed-modality gate. Future billing or quota work must establish its own exact request/model/tariff/detail schema instead of reinterpreting this metadata status.

## Independent verification

Separate overlay `/tmp/ced-provider-usage-fix1-review-6z_4h72t`; no moving live input used. **69 scoped CPU tests passed in 3.14s** (`tests/test_provider_usage.py` and `tests/test_research_resource_plan.py`). Ruff and format passed for both owned Python files. Fresh-cache `mypy --no-incremental` passed for the module; its pre-existing unused pyproject-section note is preserved. Original nine probes and five additional boundary probes passed their expected results. All archive/overlay hashes and Python ASTs still matched after tests.

Commands and scope are captured in `independent-review-setup.json`; outputs are in `independent-green.log`, `independent-ruff.log`, `independent-format.log`, `independent-cold-mypy.log`, `independent-original-counterexamples.log` and `independent-boundary-probes.py/.log`.

Read-only review: no production/test edits, no actual model/account/API request, capture, renderer, controller command or full suite. Public primary documentation was read only for schema interpretation. SOFTWARE_ONLY fixtures are explicitly owner-rebound byte/hash registrations and must not be counted as actual provider receipts. All earlier source, wire/hash/request-ID, failed/timeout/unsent denominator and immutable scope boundaries remain intact.
