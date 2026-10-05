# T3b fix round 2 independent review

Date: 2026-10-04. Reviewed prior `fix-round-1-review.md`, exact `fix-round-2.diff`, appended handoff report, and six-file `source-manifest-fix-round-2.json`. All six current files match the submitted SHA-256 values. The planner raw-byte hook is unchanged from round 1.

**Scoped software/specification verdict: PASS.** The reproduced alternate-escaping credential leak is fixed. No new P1/P2/Minor finding was identified in this round. This verdict grants no actual Max-role, profile/key, edge, physical, or complete T3b acceptance.

Independent synthetic CPU command:

`.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py -k 'alternate_escaped_credential or sensitive_readable or sensitive_malformed or profile_failure_name or secret_store_failure_name or preserves_exact_wire_response or raw_observer_failure'`

Result: **26 passed, 41 deselected, 0.55s**. External HTTP is intercepted by in-memory boundaries and observations are existing fixtures. No real credential, network/socket, renderer, GPU, physical experiment or full suite was used.

The raw observation guard captures hashes/counts from untouched bytes, then inspects detected Unicode text and decoded JSON keys/values before either raw or parsed artifact is written. The inspected regression cases include alternate Unicode/surrogate, quote, solidus and backslash escapes, nested/repeated escaped strings, UTF-16 text, non-JSON bodies, and HTTP-error bodies. Remaining opaque escape layers after the bounded inspection are conservatively withheld. Benign escaped bodies retain their exact raw bytes/hash.

Credential-bearing bodies stop the attempt before parsed response/evidence fields escape. Derived attempt/error dictionaries and the top-level report have an additional guard; sensitive details are replaced with an explicit BLOCKED suppression record and details hash. Only strict nonnegative numeric counts are retained, with malformed/unknown counts represented as null. An unavailable SecretStore keeps arbitrary exception class names opaque. No suppression branch enables nominal acceptance or writes a role freeze.

Round 1 full role/config/request revalidation and exact `.raw` evidence remain present. Request observer failure records no sent call; response observer failure retains the actual attempted-call count and received-byte count. Sanitized observer errors do not retry or fall back.

Real provider registry/date availability, real nominal S01 and missing-target/distractor reliability, edge capability acceptance, physical outcome, typed planner/execution/frozen-loader integration, and cancellation/zero-dispatch acceptance remain separate pending work. Software fixtures and this PASS must not be promoted into a real accepted snapshot. Only this review file was added; source/test code was not changed.
