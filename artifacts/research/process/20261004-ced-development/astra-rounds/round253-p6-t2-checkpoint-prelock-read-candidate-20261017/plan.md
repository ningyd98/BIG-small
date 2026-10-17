# R253 — SQLite checkpoint candidate entry order

Actual author: gpt-6-astra (/root/astra_status_plan), 2026-10-17. Plan only; STOP pending ROOT.

The unexecuted R251 SQLite candidate reads `self.get_checkpoint(checkpoint_id)` and may return False before the proposed write lock, BEGIN and local guard. Its inventory lists only the first in-lock statement, so it does not prove R251's required ordering. Original source and five candidate files remain immutable; no runtime reproduction or product application has occurred.

Only `SQLiteEventAutonomyRepository.compare_and_set_checkpoint` may change relative to the candidate. Move the exact six-line prefix (stored read, two-line early-return condition, h, saved, payload) under the existing `with self._write_lock, self._conn`, immediately after the single existing BEGIN and full guard call. Add only four indentation spaces to each moved line. Leave signature, guard arguments, remaining method body, SQL, parameters, predicates and explicit commits byte-identical. Missing/mismatched unbound checkpoints still return False before hash/serialization. Bound inputs now reject before the read, as required.

Actual `get_checkpoint` is excluded from both decorator name sets; its original body has one SELECT and model decode, no lock, BEGIN or commit. Keeping that call inside the real transaction therefore does not reenter the non-reentrant lock. No unwrap, replacement getter, new helper or nested BEGIN is needed. Private registered dispatch and exact negative cancellation remain unchanged.

Sole Sol creates new R253 physical candidate, composite patch, limited diff and truthful values/report after ROOT accepts this plan. Original R251 outputs are not overwritten. Correct only the SQLite CAS inventory entry and associated candidate hashes; other71 entry objects remain equal. The new composite patch combines unchanged protocol/memory candidates with corrected SQLite. ROOT reviews full corrected source, all72 entries and exact three-file before/CAS before releasing original R251 product application.

Normal source proof uses stdlib bytes/text/hash/diff only. All27 current sources and211 protected files matched during planning. Full original finding, five candidates, live SQLite before and current two role snapshots are archived in this round. Current R223 post-activation ledgers retain four used0/remaining1 slots. No new runtime/static/review/Git slots, resets, role/STATE/PHASE edits, tests, SQL, imports or compilation. Independent author script and ROOT settlement drafting remain outside this issue.

Detailed input pins, physical archives, exact sequence, output paths and acceptance limits are in plan.json and input-observation.json. Completion here establishes candidate source applicability only, not runtime correctness or T2/T12 acceptance.
