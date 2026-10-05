# Original provider usage reader plan

Implement the first usage/identity reader from the separately reviewed billing design. Own only `research/provider_usage.py` and `tests/test_provider_usage.py`; do not change collector, ledger, planner, protocol, resource policy or runtime.

1. Record the qualified missing-module RED.
2. Add owner-registered immutable original/current-source inventories and a read-only auditor. Reuse the frozen original wire/hash/request-ID cost reader, then parse original compatible Chat response metadata. Keep local attempt ID, opaque provider response ID and unavailable native/header request ID distinct. Validate integer token totals and cached/thinking subsets without counting them twice. Preserve failed/unknown attempts.
3. Force currency cost to null and billing status UNAVAILABLE. An observed usage record cannot supply an invoice, tariff, token cap, accepted INITIAL or execution authority.
4. Verify software positives and source/identity/unknown/alias negatives, scoped static checks and an immutable source/fixture package. Obtain independent review before recording software acceptance.

No actual model, network account, capture or controller operation is part of this task. Primary API reference: [official compatible Chat API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions). Its usage fields are provider-reported tokens; they are not settled currency.
