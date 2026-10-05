# Worker source string validation fix2

Implemented and frozen; independent re-review pending. The complete fix1 review closed the lexical symlink finding but found a new P2: a `str` subclass could override equality and make a wrong SHA256 compare equal to the actual source bytes. The original review and counterexample remain immutable.

The worker now requires plain string path names, SHA256 values and required-path entries before copying the source map and invoking existing source validation. The compiler uses the same detached boundary. The source-root lexical checks remain in place. Only the worker source module and its dedicated test changed; no policy, lease, camera, deadline or native permission changed.

Four qualified RED failures cover the SHA subclass, filename subclass, required-path subclass and compiler registration boundary. The dedicated suite is44 PASS. The exact frozen related suite is285 PASS with3 backend-only skips in37.51s; Ruff/format on2 files and cold mypy on1 source pass. The original SHA counterexample is checked for the explicit `REJECTED` outcome, and the original lexical rejection and27-case matrix still pass. These overlapping test counts are not added together.

The774-source manifest SHA256 is `9bbd1b03f63411ff46b01fcf316269a2ce86088719793f070ebf4f963a73d74e`. The other772 sources match fix1 byte for byte. The first807 release artifacts,23 first-review artifacts,794 fix1 artifacts and20 fix1-review artifacts were verified unchanged; source hash/AST and overlay hashes were verified after tests. Exact commands are in `frozen-overlay-setup.json` and output is in the frozen logs.

Scope remains WORKER_LEASE_SOURCE_ONLY and SOURCE_BINDING_ONLY. Actual factory integration, owner authentication, native admission, physical evidence, INITIAL/METHOD/FINAL and billing are not established. This fix made no new model, capture, simulator, render or controller calls. The overall R&D task remains active.
