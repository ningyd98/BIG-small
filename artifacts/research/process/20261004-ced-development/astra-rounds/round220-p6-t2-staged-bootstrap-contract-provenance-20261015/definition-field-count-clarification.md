# R220 definition-field count clarification

Actual author: gpt-6-astra, /root/astra_status_plan.

The frozen plan incorrectly says “existing nine FIELDS entries” in contract.bootstrap_original_provenance.content_sha256 and “all nine definition fields” in verification.source_obligations[1]. Both counts mean **eight**, as confirmed by local_temporal.py line 21, SHA256 8e45024610b9813f094ddc15e8a8be3cab0d798d0a30ffc38e36876431f30ce4.

Exact fields: `scope`, `episode_id`, `user_instruction`, `task_timeout_s`, `verification_limits`, `role_bundle_hash`, `model_snapshot_hash`, `source_hashes`. The canonical bootstrap-definition projection includes all eight, without additions or omissions. The separate original_time schema still has nine fields.

Original plan.json SHA256 80bf1bc8504a90ce4b9263db158c078ddaa823631204195e253d9cfe8a4ff5d2 and plan.md SHA256 cc5930bfca147af05656ef3a0b82614c926b0e1c1f638f8f62ab998e0ce3f91a remain unchanged. This separate clarification corrects only the two textual counts. Scope, modes, budgets and all other contracts remain unchanged; no source edits or product/test/runner execution are authorized. ROOT must include this clarification in its pre-implementation gate.
