# R446 applicability revalidation

Actual reviewer model: **gpt-6-astra**. Verdict: **R446 plan and addendum remain applicable; implementation may proceed within their existing scope and budgets.** No semantic drift was detected.

Original plan pins: **12/14 match**. The only two differences are the reported test import cleanup. Addendum pins: **12/12 match**, including both current test files, the current reader and original T3 evidence. Thus the addendum had already frozen the post-cleanup test bytes. All original product and plan inputs remain consistent with their respective recorded pins.

Exact drift:

- `tests/test_native_collection_authority.py`: unchanged `test_collection_factory_api_required` definition moved from before imports to after imports; unused `import json` removed; associated blank-line relocation. Current SHA256 `ba955ab59aa57310fc85b98a608f664dfe68097222601ea17c2fecb950edb995` (20021 bytes), original `12396c8d8a10e7f982ad8c5e6383014a7674dd4726a5702126e94ed4c980eb7a` (20032 bytes).
- `tests/test_native_collection_grounding.py`: unused `dataclasses.replace` and `datetime.UTC`/`timedelta` imports removed; `datetime` retained. Current SHA256 `f73950e6bdaec68b0c7aec48ab42d68c7af6ce0a265e433eccbef8fd7c2efa7b` (4840 bytes), original `383a15f00d7f7c455576962eb67ebe4b5e023611d278cb50bdd29cb9d004badb` (4888 bytes).

To substantiate the exact drift without assuming that the reported cleanup was exhaustive, the inverse edits were reconstructed from current bytes. Both reconstructions match their original frozen SHA256 exactly. Those verified reconstructions are stored separately as `intake/applicability-reconstructed-test_native_collection_authority.py` and `intake/applicability-reconstructed-test_native_collection_grounding.py`; they are explicitly reconstructed evidence, not newly claimed historical file copies. Full unified diffs and every original/current pin comparison are in applicability.json. Static AST inspection found all function/class bodies and decorators identical; removed imported names have no load uses. No fixtures, assertions, parametrization, expected failures or test count changed. Moving this undecorated no-default-argument API test definition across imports does not run its body during module loading.

ROOT's proposed private handoff helper fits the existing plan: retain B original acquisition/bracket; acquire E once at unchanged S after true R; independently bootstrap E; write dispatch bootstrap and timeline before active tracker replacement. The reader can cache at most the ten registered boundary observations for exact object-identity replay while revalidating source bytes on every read. This cache must remain a faithful view of originals and may not suppress integrity checks or generalize tracker exceptions. The original two R446 CPU cases remain in the unused final stage; consumed T3 GREEN is not rerun.

This applicability record does not replace original plan/addendum or their pins. It documents only why these two nonsemantic changes do not invalidate them. Subsequent product changes must follow R446 and be frozen as implementation/runtime generation before the original final validation. New semantic drift or unexpected failure still requires actual Astra review. No change to TTL, registration chronology, old tracker rules, source authority, UNKNOWN behavior, actual limits or the no-nine-group boundary.

Activities: filesystem reads, SHA256 comparison, source-text/AST inspection and applicability artifact writes only. **0 product imports, tests, physics steps, renders or implementation edits.**
