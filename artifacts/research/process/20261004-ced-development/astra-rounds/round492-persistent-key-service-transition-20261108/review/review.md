# R492 scoped static review

HEAD: `3b2a698baa03abf7b588ef079157e6d303a55bdb`.

Critical: none. Important: none. Minor: none.

Reviewed only the R492 default-path calculation in secret_store.py and new default-path tests, temporary XDG fixture, and corruption-target adjustment against canonical plan.md/plan.json. Source pins are recorded separately. No tests, runtime API/process actions, runtime vault/key/database reads, product edits, or Git mutations were performed. Only these review artifacts were written.

The factory preserves SESSION_ONLY and explicit override precedence. Its default uses nonempty absolute XDG_DATA_HOME or the home data directory, rejects relative XDG with the fixed sanitized error, and hashes the specified normalized absolute DB path into a full 64-character namespace. It does no filesystem creation/probing in the factory and continues to delegate permission/symlink enforcement to the existing store. No migration or alternate fallback is introduced.

Tests cover actual set/get and independent-process recovery with a shared0775 DB parent left unchanged, absolute-path/cwd/dot stability, separate DB namespaces, unset/empty XDG fallback using a mocked temporary home, invalid XDG with override/session precedence, lazy initialization, and unsafe XDG rejection without fallback. Autouse isolation supplies a private temporary XDG directory inherited by test subprocesses. The corruption test identifies exactly one temporary ciphertext and still checks the fixed API failure.

No code-review blocker for the scoped change. Final readiness requires the parent's focused and adjacent check results for these exact source bytes. This software review does not approve or perform service transition: the canonical plan explicitly reserves that for subsequent R493 planning and readiness checks. Live key persistence remains unvalidated.

Considered but not independently judged: actual test execution and durability (execution prohibited); deployment/HOME/XDG consistency and launchers (outside requested source scope); old-vault migration and symlink-alias equivalence (explicitly excluded by the defined normalized-path identity); unchanged encrypted-store internals (already reviewed in R489 and not re-audited here).
