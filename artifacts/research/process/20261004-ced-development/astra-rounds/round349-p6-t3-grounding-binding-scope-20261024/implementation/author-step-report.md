# R349 single-literal source correction

Actual author: `/root/p6_t3_sol`, GPT-6.1-sol. ROOT activated actual Astra R349 plan SHA `4614b9e3d85cd17bde87a91db2fe8e39453886fdb18f5b2c6755df1f96c33800`; activation SHA `22224a2f12fc5ba012f70263dfaa576ad5e8e641a1c5e1dec10adc88a6667029`. All 28 input pins matched before editing.

Only `owner_registration.bind_step_grounding`'s local producer dictionary at line1176 changed: `binding_scope` now emits `SOURCE_BINDING_ONLY` instead of `DURABLE_BINDING_ONLY`. Every other product byte is unchanged. The frozen full before snapshot remains intact.

The successor is exactly **49,121 bytes**, SHA256 **`bc3b8eab7d3059a40edc81453b15d37777f4d6c4f12ac59344c316636041ff80`**, matching the actual plan prediction. Its function segment SHA is `198b6093c90e1598005239c16f8f20a374c52e91b1da394a7715de62da5cda35`, using `ast.get_source_segment` without an added trailing newline.

Source-only verification completed with 19 recorded checks true. Before/after AST and symtable parsing succeeded. Recursive whole-file AST comparison found exactly one `Constant.value` difference under the local body dictionary's `binding_scope`; restoring that one constant restores the entire prior AST. The full successor equals the frozen before bytes with exactly the one planned UTF-8 substitution. The real producer and untouched decoder still have the same 18 grounding fields.

The `StepGroundingBinding` SOURCE contract, `LocalStepGroundingBinding` inheritance/tag, legacy return path, strict local decoder, publication DURABLE/NOT_INCLUDED producer and guard, private runtime caller/publication/frame/TTL checks, original app/lease bounds, generation/revision joins, envelope body/original-time copy, job-before-event transaction path and COMPLETE receipt decoding remain unchanged. Source reasoning therefore retains grounding→SOURCE and publication→DURABLE; the old wrong grounding DURABLE payload remains rejected. No parser was invoked and no compatibility exception was added.

The historical R346 gate remains byte-exact. Of its 347 pins, 346 remain exact and the only source difference is this planned owner file. All other 27 R349 inputs, original run evidence, runner/helper/test/plugin files and ROOT/AUTHOR ledgers are unchanged. Both ledgers retain `t3_01` SPENT1/0 and `t3_02` through `t3_09` HELD0/1. Exact observed HEAD remains `729bce11bbd55a4a869e25e52174da3d0db1825b`.

Evidence:

- `source-proof.json`: 126,968 bytes, SHA `571e25412cf69838ecd21fcc98123bff59c630f8716f3d3b8c6c58076d728db0`.
- `owner-registration.diff`: 825 bytes, SHA `ec7d1baf2e0765fca3e947d69dfdcc4a17ecfd7be8db2702dedeef9a58116084`.
- Product successor SHA observation: tool chunk `6adc84`, exit0, `sha256sum` only.
- Source proof/diff generation: tool chunk `8eafd3`, exit0, stdlib bytes/AST/symtable/JSON/hash/diff and finite Git metadata only.

No test, collection, probe, product/helper/parser import or invocation, DB semantic read, or runtime command occurred. This correction does not establish that the failed node now passes. The original R346:t3_01 wrapper1/child1 failure remains a failure, not a timeout; original missing case completion and retained evidence remain unchanged. No attempt is refunded, reused or implicitly continued.

All author writes stop here. ROOT must independently accept the exact source correction. A separate actual Astra finite execution and lineage plan must explicitly decide any replacement attempt and how unused slots may continue against a new versioned generation; R349 allocates zero runtime attempts and does not rewrite the failed generation's gate.
