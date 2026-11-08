# R489 read-only review

HEAD: `3b2a698baa03abf7b588ef079157e6d303a55bdb`.

Reviewed scoped uncommitted changes plus new untracked encrypted store and backend tests against the R489 plan and UX supplement. Source SHA256 and byte counts are in source-pins.json. No tests, API calls, runtime DB/vault/key access, installation, restarts, product edits or Git mutations were performed. Test pass counts supplied by the parent were not independently executed. The frontend test file was undergoing the parent's documented fixture correction during review; pins identify the final read snapshot, not a claim of successful execution.

## Confirmed findings

Critical: none.
Important: none.
Minor: none.

## Withdrawn observation and rebuttal

I initially reported that Escape could dismiss a pending credential modal, allowing an old completion callback to clear a newly opened form. That report inspected DialogWrap keyboard behavior but missed the AntD wrapper guard. Parent correctly identified `dashboard/node_modules/antd/es/modal/Modal.js:110-116`: handleCancel returns immediately when confirmLoading is true. The page passes confirmLoading={updateSecret.isPending}, and Dialog onClose is wired to handleCancel at Modal.js:220. I independently read and confirmed the complete chain. The proposed race is therefore not established for the installed dependency. Finding withdrawn; no product repair justified by that observation. A regression test can document the installed behavior, but is not evidence of an existing bug.

## Reviewed behavior with no additional material finding

- Lazy default encrypted store and explicit SESSION_ONLY opt-out; invalid store modes fail closed.
- Directory FD traversal, O_NOFOLLOW, fresh fstat checks, private owner/modes, nonregular and hardlink rejection, root/euid ancestors and sticky temporary traversal.
- Stable flock across decrypt/mutation/replace/fsync, bounded contention, concurrent initialization and independent updates; no cached plaintext map.
- Strict versioned JSON and duplicate-key rejection, bounded master/ciphertext/plaintext, Fernet authentication, exclusive encrypted temporary writes, master preservation, atomic replacement, and pre/post-replace error handling.
- Fixed sanitized store error; actual presence and kind projection on create/update/get/list; write-only profile serialization; omitted/blank PATCH behavior; secret-first profile deletion.
- Existing-profile PATCH has only api_key, encoded ID, profiles/runtime invalidation; settled mutation reset plus immediate inactive GC; successful clear, failed-open retention, explicit cancel/unmount clearing; truthful encrypted/session/absent/unknown status text.
- Service diff leaves R488 visual-planner trusted scope unchanged.
- Source tests exercise fictional isolated vaults, independent subprocess restart and coordinated concurrent writes; no real credential fixture.

## Considered but not independently judged

- Runtime restart recovery, live user key persistence, service deployment and actual filesystem durability: runtime actions prohibited; this review evaluates code and tests statically.
- Same-owner/root compromise, rollback resistance, deletion of the whole vault, interrupted key-only initialization, and missing DB/vault transaction: explicit accepted plan limitations, not new defects.
- Exact final frontend test outcome and overall test readiness: parent was still correcting a detached-node assertion; requires its final verification evidence.
- Unrelated repository changes, formal experiment acceptance and remote delivery: outside review scope.

## Readiness

No confirmed code-review blocker for a scoped research-branch commit. Final commit readiness remains conditional on the parent's required final targeted checks and source-generation reconciliation. Preserve raw failed attempts and do not claim the live key is persisted or deployed. This review did not verify commit/push or remote SHA.
