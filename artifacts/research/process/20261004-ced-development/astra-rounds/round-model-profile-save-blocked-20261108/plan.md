# Astra 计划：模型页保存无响应

Planner: `gpt-6-astra`；仅计划完成，产品实施尚未开始。

## 根因与证据

模型页保存无响应：全局dashboard summary同步全量证据扫描阻塞ASGI事件循环；表单缺少成功/失败反馈。

主线程95.2%CPU且打开历史artifact文件；全局5秒summary→async同步EvidenceIndex.refresh全量扫描。原始失败见 failure-evidence.json；无Python栈采样，不归因Ollama或401。

## 实施

- **S1** Recheck input hashes, running PID/cwd and current scoped git diff. Record any intended pre-implementation differences. Use existing managed test runtime; no secret inspection.
  验收：Scope and evidence still apply; unexpected root cause or broader repair goes back to Astra.

- **S2** Add controlled ASGI concurrency regression: hold EvidenceIndex scan via thread Event, issue summary, then profile GET and profile POST with fake non-sensitive fixture in temporary DB; both must finish before releasing scan. Prepatch RED expected. Add scan single-flight/snapshot correctness tests.
  验收：Single ASGI event loop shared by concurrent requests; timeout cannot hang test cleanup; fake secrets never used against external provider.

- **S3** Offload dashboard routes that actually call refresh/get_detail/runtime(summary) to worker execution (sync FastAPI route or awaited run_in_threadpool), preserving auth and response contracts. Include summary, runtime, evidence, evidence-errors, evidence-detail, evidence-download, evidence-compare. Keep other routes unchanged. Avoid concurrent lazy service initialization producing separate index instances.
  验收：Blocked evidence scan no longer blocks independent model profile routes or /health.

- **S4** Make EvidenceIndex refresh non-reentrant and publish completed records/errors consistently. Concurrent callers share the same in-flight scan result; no implicit TTL or stale cache. Use minimal lock/condition plus generation/snapshot. Preserve file inclusion, ordering, redaction, path/size safety; a later explicit refresh must discover newly added fixture files.
  验收：One active scan per index; no cleared/partially mixed result escapes; error and record snapshot consistent; scan failures wake waiters and do not poison subsequent refresh.

- **S5** Add only minimal save success/failure/pending feedback to existing form with safe fixed/localized messages; catch mutateAsync rejection. Preserve all inputs on failure; clear API key field only after confirmed success. Include accurate session-only key lifetime notice. No key editor or unrelated UI state redesign.
  验收：Successful save is visible; server error/timeout state is understandable and does not leak raw request/secret. Existing create-and-test workflow remains usable.

- **S6** Run focused dashboard/model backend tests and relevant frontend tests/typecheck/build. Review exact diff. Preserve expected RED and GREEN outputs.
  验收：Behavioral concurrency regression and existing evidence security/contracts pass; frontend validation passes.

- **S7** Capture original backend invocation/cwd and required environment in memory without printing secrets; controlled restart only the identified backend after tests. Do not write secret environment snapshots. Record that InMemorySecretStore loses keys across restart; existing DB secret_present alone is not proof of current key availability. User can create a fresh profile with the existing form.
  验收：Backend serves same DB/config/address; frontend/unrelated processes untouched; historical evidence and DB preserved.

- **S8** With real large artifact root and /models page open, verify /health and profiles GET remain responsive while summary scans. Save a uniquely named RULE_BASED temporary profile without api_key, verify returned profile ID, then delete exactly that non-active ID. Inspect browser save feedback. Actual key remains for user private input. Record observed results; commit/push only verified explicit paths and compare local/upstream/remote SHA.
  验收：Real profile read/save responds promptly (target <2s, evidence scanner may still be slow); UI feedback verified; external model authentication is separately observed or explicitly unverified.

## 边界与前置条件

- No all-model-route async rewrite
- No new existing-profile key editor
- No secret persistence/storage redesign
- No deletion, pruning, or modification of historical evidence/artifacts
- No provider/model/planner changes
- No changes to DB, keys, unrelated processes, controller or hardware
- Existing Python venv and Node dashboard dependencies available; test DB/artifact fixtures isolated from running DB.
- Only identified backend may restart after validation; SESSION_ONLY credentials must be re-entered by user if needed.
- Do not capture browser/API request bodies containing real API key.
- Original real artifact root remains untouched and available for live concurrency check.
- Use .venv/bin/python (pytest/httpx available) and cache/node-v22.23.3-linux-x64/bin/node; system Node18 is not suitable.

仅 allowed_files 和必要的 conditional_files（见 plan.json）。开发验证、真实运行、正式研究验收分开记录；本轮不构成研究或硬件验收。出现新根因/计划外失败须返回Astra。

## 输入 SHA256

- `AGENTS.md`: `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `src/cloud_edge_robot_arm/cloud/api/dashboard.py`: `52dc3f680cc5b7fd7bb163f3f7a4f9bebfc7a36a9f2d682690dd8961477a64ca`
- `src/cloud_edge_robot_arm/dashboard/service.py`: `c6640ddbe6f909d751f1b47a6d0cb23d21e0cbd7ad5688c8397799e767a0cdef`
- `src/cloud_edge_robot_arm/dashboard/evidence_index.py`: `e04fa2984b904a77b2b861668280d1109404d37c3408904420e5b56488d095c3`
- `src/cloud_edge_robot_arm/cloud/api/model_control.py`: `4506e5ea0704e89e547ea3c481210b4a802f21b80da3426450bb01efd6a9a91a`
- `src/cloud_edge_robot_arm/model_control/service.py`: `7eeaacd932542feaaf77ad48b71cab5421edb13e827fd27a49879defad94da39`
- `src/cloud_edge_robot_arm/model_control/secret_store.py`: `3bc779cecb00ab7a2e1b0501d7e7dc24bcd65ec6c85e15e6b47197b9448f41c8`
- `dashboard/src/app/App.tsx`: `741c1e724f5850fe35ac44a79619bd64e72536f117f4a402b81ffa10ce3aba01`
- `dashboard/src/api/queries.ts`: `ddf0293b89e33e5f6da6be5f1773582f03ea5ddd7bb447139f0840f6a8afeb3a`
- `dashboard/src/modelControl/pages/ModelControlCenterPage.tsx`: `848b88c9580205c4b5f320b871714fb4dd4f6429ed294eaead6c294600ab1e49`
- `dashboard/src/modelControl/api/modelControlApi.ts`: `f001becbdff26f897328bb0b2422e498b48b8047a86f53b2bc966225756080e2`
- `dashboard/src/modelControl/api/modelControlQueries.ts`: `96af9472d45d1f253557b2bee74bb45a02348a72677c2136b30b51865b277a4c`
- `tests/test_phase10_2b_dashboard_backend.py`: `052d2ca8847d13fea2f531361e6c864007bdf35389f4607f4bb1ab3b84c82103`
- `tests/test_phase11_2_model_control_backend.py`: `3f793cea250c726f8d91f25ebc2df8c90f283c2defe2a6834070c5a1b07b830c`
- `dashboard/package.json`: `1c68084539ee59484c222b49e92d9f44e00d8766d16f9eb2d312fda263e4edb8`
