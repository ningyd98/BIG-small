# R297 — selected-event attempt accounting

Actual gpt-6-astra; static source review only. The bca996 candidate has never run.

The complete plugin shows a real accounting gap: `session_identity_reused` records a drop before reaching the increment in `append_record`. Selected snapshot/record-construction errors can also precede that increment. The `sessions6` branch compensates separately, demonstrating that the counter is attached to the wrong boundary.

Only four exact replacements in plan.json are authorized: remove the increment from append_record; add it immediately after exact target/category selection; remove the sessions6 special increment; add one increment after the existing post-unwind hook selection and before exception extraction. No other source byte changes. Both selection paths then count once before their work can fail or drop. Unselected events remain excluded; post-unwind records remain separate attempts.

The original caps/drop/error handling, admitted record ordinal/count/charges and first-witness sampling stay unchanged. Selected errors retain an attempt and existing observer_errors/incomplete. Pre-selection errors cannot establish a selected-attempt denominator and remain unknown. For error-free completed capture, consumer checks attempts=retained+dropped and drops=sum(reason counts). Do not force this equality through fabricated counts on incomplete/error paths. A first-witness-attempt flag is not a retained witness: the actual stored record/session/ordinal must bind; failed or dropped witness remains unknown without retry.

SoleSol saves a new R297 candidate, four-region diff/proof and full physical after, then one native Update of the R296 logical plugin. The original R296 prepared/after/native/diff remain immutable. All receipts and reports are new R297 paths; actual native{} has no numeric exit. ROOT checks full native reconstruction, exact derived SHA and unchanged bytes. Complete prior source reads may cover unchanged regions only with byte proof; changed regions receive full review.

Original bca logical history resolves through R297 complete before or immutable R296 prepared/after, never a whole-path exemption. R296 final source gate binds this supplement and actual new plugin. Independent runner preparation may continue, but final consumer/plugin binding remains held. No product/test/TTL/wait/authority/observation target/cap changes.

The single R296 diagnostic remains HELD0/1. R297 adds zero runtime/static/review/Git/SQL slots. No plugin execution, import, AST, compile, probes or new validator. Future actual counter validation uses only the original R296 gated diagnostic. Source acceptance is not behavior acceptance; T2/T12/native/formal remain false.

Freeze plan and STOP for ROOT review.
