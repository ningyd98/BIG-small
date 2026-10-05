# T8 billing source design audit

Status: **DESIGN_ONLY / NOT_RUN**. Checked official public Alibaba Cloud documentation on 2026-10-04, at 14:13 UTC. No account, invoice, model endpoint, credential, console, or cloud project was accessed. No production file was changed. Fix3 source remains frozen at manifest `db5ab161b94d4ee1c49b3f527cd4203b99475781d6cd2023148600f60bee2b22`.

The smallest viable implementation can produce a source-bound **published-tariff planning bound**, while keeping actual invoiced money unknown. The reviewed public interfaces do not establish a per-inference settled-charge join. A planning bound requires a separately versioned budget rule; it cannot silently satisfy the existing measured-money requirement. Neither route establishes physical success, method acceptance, INITIAL, or FINAL.

## What official sources establish

The compatible Chat response supplies a unique `id`, returned model, and input/output/total usage; streaming usage requires the final usage chunk. Thinking is part of generated usage. `max_tokens` generally excludes thinking, whereas `max_completion_tokens` covers both, with a documented possible ten-token difference. These are usage/cap contracts, not settled-currency fields. [Official Chat API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions).

Provider audit logs expose request identity, time, model, API Key, status and token usage, and support exact Request ID searches and JSON details. Logs are distinct from original local transport bytes. The reviewed page describes console access; it does not document a stable public per-request audit-export API schema. [Official model telemetry](https://help.aliyun.com/zh/model-studio/model-telemetry). Monitoring data is explicitly informational rather than a billing basis. [Official rate-limit FAQ](https://help.aliyun.com/zh/model-studio/rate-limit).

Inference bills are grouped by API Key, workspace, model, input/output category, channel and quota flag. Minute-level bill appearance is distinct from monthly settlement and actual deduction. This establishes aggregate cost attribution, not a per-inference paid amount. [Official billing guide](https://help.aliyun.com/zh/model-studio/bill-query-and-cost-management).

`QueryInstanceBill` queries monthly/daily instance or billing-item summaries. Its top-level `RequestId` is the billing API operation's ID, not a documented inference identifier inside a line. `DescribeInstanceBill` separately exposes usage/unit, gross, payable and cash/payment amounts, currency, pagination, refunds and adjustments. None of the reviewed line schemas supplies an inference Request ID. [Official QueryInstanceBill](https://help.aliyun.com/zh/user-center/developer-reference/api-bssopenapi-2017-12-14-queryinstancebill), [official DescribeInstanceBill](https://help.aliyun.com/zh/user-center/developer-reference/api-bssopenapi-2017-12-14-describeinstancebill). This is a conclusion limited to the reviewed schemas, not proof that no private/custom provider facility exists.

The model page currently lists `qwen3.8-max-0902`, also named `qwen3.8-max-2026-09-02`. Beijing list prices are CNY12 input/CNY36 output per million tokens; explicit-cache creation is CNY15 per million input tokens. Regions, deployment scopes and cache modes differ. These are public list prices, not our actual profile, a historical effective-date certificate, or a paid invoice. [Official Qwen3.8-Max model page](https://help.aliyun.com/zh/model-studio/qwen3-8-max). Request IDs may appear in a response header or body; the error guide does not establish a universal Chat-ID prefix transformation or header-name mapping. [Official error-code guide](https://help.aliyun.com/zh/model-studio/error-code/).

## Three separate money views

| View | Authority and join | Allowed claim | Missing-source behavior |
| --- | --- | --- | --- |
| `DECLARED_LEDGER` | Original settled CostLedger row, local attempt ID, original row hash | The collector/record declares this amount; its currency may be absent | Preserve original value, never authorize a budget |
| `PUBLISHED_TARIFF_BOUND` | Original provider usage or independently justified complete token caps; official tariff retrieval; exact region/model/mode; all original attempts | An explicitly conditional gross planning bound under the frozen tariff/cap policy | Unknown; never substitute byte count, reply text length, zero, or an arbitrary floor |
| `PROVIDER_SETTLED_AGGREGATE` | Original provider billing pages/export, complete pagination, account/workspace/API-Key/model/category/period closure, settlement evidence | Source-qualified payable/paid totals for that aggregate, with amount types retained | Unknown; never allocate a total to requests by token share and call it invoiced |

The reviewed provider does not offer a proven fourth view, `PROVIDER_SETTLED_PER_REQUEST`. It must remain unavailable. A general tax invoice covering a month or several products also cannot establish individual model charges. Cash, payable, gross and adjustments retain their own labels; they are not interchangeable scalar amounts.

## Original identity and usage reader

The current pilot's `request_id` and `response_request_id` both refer to the local CostLedger attempt. The private collector joins these correctly, but those fields are **not provider IDs**. `vision/planner.py` stores original request/response bodies and creates a local UUID; it currently omits response HTTP metadata and does not normalize provider usage or ID. No settled row should be edited to add these facts.

Proposed separate immutable evidence contains: episode/assignment/role/model snapshot; local attempt ID; request/response SHA and lengths; observed endpoint origin/region/workspace reference; HTTP status; allowlisted original response metadata; exact response body's provider response ID; optional native/header provider request ID; original usage subtree; streaming completion/terminal evidence; and the collector/source version. Credentials are excluded. A fresh source-bound observer records the body and HTTP metadata on the same transport operation, including HTTP failures; a caller-made JSON receipt cannot impersonate this observer.

The reader reparses all fields from original bytes, checks the current role binding and complete settled-attempt inventory, and rejects duplicate IDs or reuse across episodes/roles. Chat completion ID, native request ID, local attempt UUID and billing-operation RequestId retain separate fields. Do not strip a `chatcmpl-` prefix as proof. An audit-row join needs the exact provider ID in independently obtained original metadata, or a separately verified mapping. Missing or ambiguous mapping remains unknown. Missing provider audit data does not become paid-charge evidence.

Token counts must be finite nonnegative integers with internally consistent totals and modality/cache details. Input totals already include applicable image tokens; generated totals already include applicable thinking. Do not add those subsets twice. Provider tokens cannot be inferred from serialized bytes or visible output. Malformed, partial, absent or empty response bodies remain original failed attempts; their usage remains unknown unless an independent original usage source or proven cap supplies a bound.

A locally imported audit JSON/file is diagnostic unless its provider origin and complete query scope are independently established. The public docs reviewed here are not a signature specification. A future read-only retrieval adapter must retain exact query/response bytes, pagination and trusted observer origin; a hash proves unchanged bytes, not remote authorship. This audit did not enable log delivery, create billing subscriptions, or fetch private evidence.

## Minimum tariff-bound route

First implementation scope: synchronous pay-as-you-go compatible Chat, a date-bound Qwen model, a verified region/workspace, text and registered RGB-D image inputs, no separately billed tools, no explicit cache creation, no Batch/Responses/managed-agent or dedicated deployment charges. Reparse the whole request to prove scope. Automatic discounts/free credits are ignored when calculating the gross planning bound; this changes no account setting. Cache creation must be rejected or separately priced because its list rate can exceed ordinary input.

For a completed original usage record with inputs I and outputs O, use exact decimal arithmetic:

`bound = I * max_applicable_input_rate / 1_000_000 + O * max_applicable_output_rate / 1_000_000 + independently_verified_extra_charge_bound`

The maximum must cover the frozen mode and any applicable tier. Caching is not subtracted without a complete disjoint-category contract. For the restricted Beijing example above, ordinary list-price arithmetic is `(12*I + 36*O)/1_000_000`; that is an example under the stated scope, not an actual charge. Explicit-cache input cannot use that example. Outward rounding to a planning quantum is a versioned conservative rule, not provider invoice rounding.

For a timeout/cancel/error without complete usage, keep every sent attempt and use only independently supported model/input/output caps and frozen mode limits. A response-size limit, watchdog duration, declared `max_tokens`, or HTTP failure does not prove zero cost. The present Max adapter's `max_tokens` alone does not bound thinking. A future total-output cap must be in the actual sent body, source-bound to the supported provider contract, and include the documented tolerance; otherwise the bound stays unknown or uses a separately justified larger model-wide cap. Hidden prompts, image processing and retained history cannot be guessed from message character count.

A published tariff capture needs official URL, retrieval time, original public response bytes/headers, parser/source hashes, exact model/region/mode/currency/unit, documented applicability and any known effective period. An arbitrary archived HTML plus rehashed receipt is not authority. Before a new real stage, independently revalidate official origin/prices and freeze the result; rate/region/model drift refuses the old admission. Current docs do not certify historical rate windows or future prices. This design has **no production tariff snapshot**: `public-doc-sources.json` is a research-source index, not a pricing certificate.

Per-request tariff bounds do not prove a complete future pipeline ceiling. P99 successful B0 cost multiplied by every method is an extrapolation, not a deterministic JOINT/B1/B2/B3/B4/B5 request bound. The strict route additionally freezes and enforces role/method attempt quotas and input/complete-output caps for selection, foundation, power120×7, chosen/worst formal N×7, fixed G3, G4, verification/reproduction, calibration/data generation and rerun reserve. Any unbounded phase or unknown non-model charge remains INCOMPLETE. Existing20% reserve is separately labeled planning reserve and cannot repair unknown charges.

## Aggregate invoice route

If future original exports/API responses are supplied, retain all zero-charge lines, discounts, package/coupon offsets, refunds/adjustments and complete pagination. Recompute aggregate scope from original fields, not a declared `settled` flag. Preserve provider settlement/payable/cash evidence separately; an early minute bill is not a closed-month paid invoice.

An aggregate can be attributed to a research phase only when independently checked audit/transport inventories establish the same account, workspace, API-Key, model/category and closed billing period, with no unrecorded or unrelated calls. Shared keys or overlapping periods invalidate exclusive attribution. A dedicated identity is a future workflow option, not something created by this task. Aggregate money may supply phase sunk totals after verification; per-success B0 monetary P99 still needs an actual per-episode source or the separately authorized tariff-bound rule. Allocating aggregate fees proportionally does not satisfy that requirement.

## Proposed API and ownership

These are proposed Python signatures, not implemented functions. Paths passed by trusted CLI/registry adapters are confined to a non-symlink evidence root; no path, account operation or shell command is accepted from report metadata.

```python
read_provider_usage(evidence_root: Path, *, binding: RoleRuntimeBinding) -> ProviderUsageInventory
read_official_tariff(public_capture: Path, *, usage: ProviderUsageInventory) -> TariffView
bound_request_money(usage: ProviderUsageInventory, tariff: TariffView,
                    *, caps: FrozenInferenceCaps) -> MonetaryBoundView
read_settled_aggregate(evidence_root: Path, *, usage: ProviderUsageInventory) -> AggregateMoneyView
compile_monetary_evidence(evidence_root: Path, *, binding: RoleRuntimeBinding,
                         caps: FrozenInferenceCaps) -> MonetaryEvidenceView
```

`MonetaryEvidenceView` contains basis-tagged decimal currency amounts, exact complete local/provider identities, unknown-attempt IDs, original usage refs, tariff refs, aggregate refs and deterministic diagnostics. It has no caller-controlled acceptance flag. Reproduction reruns all readers. CostLedger originals remain append-only and unchanged; views are derived sidecars.

| Future owner | Smallest responsibility | Excluded from that scope |
| --- | --- | --- |
| Provider/transport owner | Backward-compatible typed metadata observer; actual complete-output/call caps; raw HTTP and failed-attempt identity | Billing charges or method/physical success |
| Billing reader owner | New `research/billing_evidence.py` and dedicated software tests; usage/tariff/aggregate readers and money view | Updating settled CostLedger values or accessing private accounts without an assigned retrieval task |
| Resource/protocol owner | New monetary basis schema and explicit initial budget rule; full phase/cap coverage; import derived views | Retrofitting historical frozen protocols or calling a bound measured payment |
| Reproduction/API owner | Reread original monetary sources and expose the three labels and missing fields | Positive physical badges or summary-flag acceptance |

Existing `resource_plan.v1`/fix3 keeps remote money UNKNOWN. Proposed `ced.monetary-evidence.v1` and `ced.resource-plan.v2` separate `measured_money` from `planning_money_bound`; a new budget-selection rule hash must bind whether complete conservative planning bounds are allowed for INITIAL. The existing research success/safety goals and statistical family are unchanged. This rule is **PROPOSED_NOT_ADOPTED**; a design report is not an accepted resource receipt.

## Regression matrix for future implementation

| Group | Required counterexamples | Expected behavior |
| --- | --- | --- |
| Original source integrity | Edited ledger fee; changed/rehashed body/header; empty-present payload with stale SHA; absent payload with a hash; narrowed original inventory | Declared amounts remain diagnostic; source drift rejects; all originals retained |
| Identity | Local UUID used as provider ID; arbitrary Chat-prefix stripping; repeated provider ID; swapped role/model/episode; billing API RequestId treated as inference ID | Reject/unknown; no inferred settled-charge join |
| Usage | Missing/null/partial terminal usage; negative/fractional/bool counts; inconsistent total; duplicated image/thinking/cache subsets | No invented usage; no double counting |
| Tariff | Foreign/unproved origin; unknown region/currency; stale historical rate; alias drift; explicit creation priced at ordinary input; Batch/Responses/tools silently ignored | Unknown or reject until exact applicable source is verified |
| Bounds | Timeout charged zero; `max_tokens` used as thinking cap; output tolerance omitted; unknown input overhead; P99 B0 substituted for all-method hard caps | UNKNOWN/INCOMPLETE; enforce proven caps and complete quota coverage |
| Bills | Missing page/zero lines; duplicate lines; refunds dropped; payable equated to cash; incomplete month; shared API-Key; unrelated phase calls | Preserve amount kinds and uncertainty; no exclusive phase or per-request claim |
| Numerics | Decimal million-token units; boundary/tier tests; maximum rate; outward rounding; mixed currencies | Deterministic exact calculation; currency or mode mismatch refuses sum |
| Admission/export | Rehashed receipt with positive scope flag; tariff-bound labeled paid; missing one failed attempt; reproduction without originals | Actual budget remains closed; export same basis and denominator |

All numerical fixtures must explicitly be SOFTWARE_ONLY and cannot return actual money/physical acceptance. Future genuine integration tests require fresh real transport and independent applicable source data. No such integration ran here.

## Remaining uncertainties and immediate sequence

Unproven: stable public audit-export API/schema; universal Chat body/header-to-audit-ID mapping; per-request settled-fee API; historical tariff effective-date certificate; provider-signed exported rows; account-specific discounts/taxes/packages; closed billing scope; future price stability; actual per-method hard caps; monetary costs of calibration/data/verification. None can be resolved by adding a JSON `available` flag.

First implement the original usage/identity reader and strict explicit basis view in isolation. Then add a public-origin tariff reader and cap contract, with all unsupported/missing cases closed. Only after the separately versioned INITIAL planning-bound rule is accepted should the resource reader consume that bound. Account invoices can be added later as separately labeled aggregate reconciliation. Until then fix3 remains the applicable conservative behavior, and actual research remains **NOT_RUN**.
