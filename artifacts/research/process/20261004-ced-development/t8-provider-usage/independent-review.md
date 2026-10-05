# Independent provider usage review

Verdict: **CHANGES_REQUESTED** for the bounded software metadata reader. No owned production/test source was changed. No model/account/API request, renderer or controller call occurred. Public official API documentation was read for schema verification only.

Reviewed immutable manifest: `23f117d29ecfe3f2736817ac3f7c70693710a75bb08b892e89166b747a6c4125`, 770 files, exact union of the frozen T8b fix3 768-file release and the two owned files. All hashes and Python ASTs match. Separate frozen overlay and commands are recorded in `independent-review-setup.json`; no moving live overlay was used. Scoped tests: **60 passed in 3.11s**. Ruff, format and fresh-cache mypy passed (`independent-*.log`).

## Findings

1. **P2 — unsupported response types are called observed synchronous Chat usage** (`provider_usage.py:309–315`). Only `chat.completion.chunk` is excluded. Owner-rebound exact-hash synthetic originals with missing `object`, `object=error` plus an error member, or `object=response` all return OBSERVED with 150 tokens. The same correctly typed `chat.completion` positive remains OBSERVED and a chunk remains UNKNOWN. Require the supported synchronous discriminator rather than permitting every other JSON shape; error envelopes must remain unsupported even if they carry coincidentally matching metadata. Keep failed-attempt denominators and distinguish an actual compatible Chat response accompanying an ERROR transport outcome from an error envelope.

2. **P2 — no usage is promoted to OBSERVED** (`provider_usage.py:340–348`). An exact empty ledger/wire returns OBSERVED with zero attempts; an exact all-unsent ERROR ledger returns OBSERVED with one original attempt, zero sent attempts and no token values. The reason explicitly says original usage metadata was observed. Require at least one supported sent usage observation; retain the original/unsent denominators and nullable token fields. UNKNOWN is the appropriate evidence label when there is no provider usage.

3. **P2 — contradictory modality breakdowns pass** (`provider_usage.py:198–200`). Each detail is bounded independently, so input text=70 and image=70 under prompt=100 passes; output text=40 and audio=40 under completion=50 also passes. These mutually separate modality components cannot jointly exceed their parent total. Validate documented disjoint modality subtotals while continuing to treat cached input and reasoning output as overlapping subsets; do not add cached or reasoning tokens to the modality total. Missing optional components need not imply an exact equality check.

All nine counterexample/control results are preserved in `independent-counterexamples.py` and `.log`. These are explicitly re-registered SOFTWARE_ONLY owner fixtures, not original remote provider receipts. Original bytes, hashes and request IDs were consistently rebound; none of the findings depends on bypassing the wire inventory.

The supported synchronous discriminator and modality meanings were checked against the [official compatible Chat API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions): synchronous object is `chat.completion`; text output contains reasoning, and cached input is a subset. This review does not derive any tariff or currency amount from that documentation.

## Verified boundaries and limits

Exact original file inventory, current source inventory, role digest, request/response byte hashes and local request IDs are revalidated through the frozen reader. Added/missing/changed files and symlink paths are rejected. Existing tests cover integer/nonnegative totals, cache/thinking ceilings, model drift, missing/error/timeout responses, streaming, detached aliases and evidence changed during reading. Every counterexample still had currency null, billing UNAVAILABLE and ORIGINAL_PROVIDER_USAGE_METADATA scope; no billing, INITIAL admission, token cap or execution authority was obtained.

Opaque response IDs are checked for duplicates within an audited inventory. This bounded per-inventory reader does not establish provider authenticity or a cross-episode invoice identity authority. Raw metadata observation is not real-role/model acceptance or physical success.

Please preserve this 770-file release and add qualified RED cases before a separate fix1 freeze. No extra actual cloud call is needed to reproduce these software findings.
