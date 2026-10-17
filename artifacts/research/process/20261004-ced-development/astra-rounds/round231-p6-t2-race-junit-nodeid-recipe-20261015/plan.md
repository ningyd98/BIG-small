# R231: JUnit classname to nodeid recipe

Actual planner: /root/astra_metadata_recovery, gpt-6-astra. Plan only; no runner edit or execution.

The frozen R223 runner line323 prepends tests/ to classname.replace('.', '/'). Existing real R158 XML has classname tests.test_operational_runtime_closure, so the expression forms tests/tests/test_operational_runtime_closure.py::name. This is a source-supported recipe defect, not a failed R223 run. All six R223 commands remain HELD0/1. Original ROOT source finding, author observation, full before runner and prior XML are pinned.

Only sole Sol may change the names comprehension inside junit: remove the literal tests/ prefix and retain every other token/byte outside this line. No fallback or normalization. Preserve testcase order, parameter suffixes and names == expected; missing/duplicate/unknown/extra/reordered nodes remain rejected. RED stays exactly3 failures with its original assertion/real bootstrap/resource conditions; GREEN exactly9 passes. Resource lifecycle, cleanup, raw capture, argv/env, timeouts and budgets remain byte-identical.

After ROOT full source/input gate, permit one scoped source edit and one ordinary bounded stdlib bytes/hash readback. Require the entire after file to equal the frozen before file with precisely the approved single-line replacement; preserve tiny diff, full after pin, actual receipt and step report. This is human text review, not AST/import/compile/static tooling or a parser test. Do not execute runner or any new validation probe.

ParentS2 work may continue; changing product/test drafts are not permanent R231 inputs. R230 is a separate test-interface root cause. Later real R223 execution still requires its original complete gates, parent bootstrap readiness and independent R230 acceptance. This plan releases no R223 command and no original GREEN. Future unexpected XML must fail exactly and return to Astra, never trigger broader normalization. R229 Git allowance is spent; no Git/delivery authority here.

Any drift, nonunique replacement, expanded diff, partial write or new failure stops with evidence and new Astra planning. Source-only correction is separate from real RED/GREEN, resource evidence, native/formal research and T2/T12 completion.
