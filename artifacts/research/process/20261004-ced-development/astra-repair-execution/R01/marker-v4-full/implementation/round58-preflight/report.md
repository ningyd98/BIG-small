# Round58 marker full preflight implementation

Only three authorized owned sources changed. prepare_full.py retained SHA256 6f8d7982a85a5e1cff488a5a2204fd0fe64a2c54725bebf22935de6f0f47f550. Original four sources, paused manifest, prior RED/GREEN/static logs and 26 other input pins remain preserved.

The fixed V3 adapter accepts only the frozen V3 protocol and long SHA fields, preserves all original END metadata, and never requires a nonexistent original_sha256 in the old readout. New recorder return, persisted END and inherited coordinator.saved are identical; the reader still compares full records. The production reader rejects teacher ordinals outside native int 1..9/duplicates and enforces exact nine teacher/eighteen action inventories. The four static fixes preserve behavior; adjacent-time zip explicitly uses strict=False.

New fixtures: RED 38 failed / 2 existing rejection tests passed (1.24 s); same 40 fixtures GREEN (0.89 s). Final owned suite: 131 passed, zero failed (9.66 s). These are overlapping test identities, not additive independent samples. Ruff check, four-source formatter check and in-memory compile passed. Exact commands, command/log hashes and before/after source pins are in report.json.

No real full-protocol freeze, actual, model, renderer, real detector, old raw image decompression, old raw reproduction audit or Git operations occurred. The existing CPU test uses only a /tmp freeze fixture. This report does not establish full4807 observability, sampling admission, physical equality or formal/native acceptance.

Handoff: root must review fresh-process source/live/archive/import-origin closure before authorizing the first exclusive real freeze. Frozen-byte independent review precedes the one allowed actual and one new full readout. Existing resource, source pin and no-existing-attempt gates remain mandatory.

Ruling: user/plan owned-only and no-Git scope takes precedence over generic skill global-test/commit/workspace defaults; cost if wrong is narrower regression evidence, explicitly limited to owned software. Deferred minors: none.
