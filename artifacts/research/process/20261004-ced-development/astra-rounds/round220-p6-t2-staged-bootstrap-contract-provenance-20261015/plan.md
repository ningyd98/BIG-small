# R220 — staged bootstrap contract provenance

Actual planner: gpt-6-astra, /root/astra_status_plan. Status: frozen plan, ROOT input/contract gate pending.

The source contract is incompatible with the frozen T2 sequence: original_time is saved before the future planner contract exists, while the old codec requires its provenance hash to equal that later complete contract. This is a source-level finding, not a failed T2 GREEN. The original RED is spent; GREEN remains held.

Keep the existing outer tags, six envelope fields, nine original-time fields, exact payload field sets and four-field history. Preserve old LOCAL_APP_PRODUCED and EXTERNAL_UTC behavior and every frozen test byte. Do not invent a future hash, rewrite original_time, fabricate UTC or turn detached decoding into permission.

Use two explicit new nested provenance kinds. LOCAL_BOOTSTRAP_SOURCE_V1 retains the two fields kind/content_sha256 in original_time, committing to the canonical domain-tagged exact bootstrap definition payload. LOCAL_BOOTSTRAP_ADOPTED_V1 occupies the already existing original payload provenance field, with exactly kind/content_sha256/bootstrap_record: the actual complete contract hash and genuine pre-promotion record. Decode/replay that nonterminal, promotion-free record, bind its definition/immutable original/CAS/spent budget/draft, and retain all existing compiler/source/camera/requirements checks. No cycles or hash-only substitute. The detailed exact schema and joins are in plan.json contract.

Focused source paths: `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py`, `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/operational_windows.py`, `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/worker_runtime.py`, `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/worker_owner.py`, `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/owner_registration.py`, `/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py`. All are within the original 19-product T2 scope. Existing remaining T2 work retains its parent scope; this round adds no other feature. The three current foundation drafts are preserved.

ROOT first checks the 25 current/archive pairs and protected211 and reads the full plan. The same actual gpt-6.1-sol author then performs source-only implementation, records full before/after, exact diff and provenance checklist. ROOT reviews both new and all old dispatch paths and the complete source/resource contract. Only a separate original GREEN gate can release the existing unused seven-node command, unchanged, once.

No new test/static/import/AST/probe/SQL/Git/network command, review seat or retry is granted. The exact inherited GREEN command and resource limits are recorded in JSON. No source mutation tests have run; any need for extra validation requires a finite next plan. Source gates and prior T1 results do not establish current T2/B/T12/native/formal acceptance.

All original evidence, 25 physical archives, roles and raw remain history. Mutable future role/gate state requires ROOT before archives and CAS; STATE/PHASE are not falsely pinned as immutable here. Test, runner, fixture-map original and protected files remain fixed.

Inputs and all full SHA256 values are enumerated in plan.json and input-observation.json. Source before/current pairs were independently checked by db2186, exit 0, 25/25 equal. No product command was run. New failure, drift or scope expansion stops related work for genuine Astra planning.
