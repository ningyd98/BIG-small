# OC1 round59 independent source review

**PASS_SCOPED_SOFTWARE_OC1.** No open P1/P2 finding was identified in the authorized OC1 SOFTWARE scope. Final production SHA256: b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b. Final test SHA256: ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f. Both remain byte-identical before/after the independent probe.

Both complete owned files, round57/58/59 plans, implementation/static reports, precise diffs and AST evidence, root's final test output and new CPU receipt were reviewed. A parallel read-only lifecycle review also found no scoped P1/P2 and executed no project code. The reviewer changed no production/test source, old reports, root documents, original evidence or Git.

## Software verification

The root-owned final full-file pytest run is the single complete 60-case rerun authorized in round59. It returned exit 0, **60 passed, 0 failed, 0 skipped in 0.11s** on the exact final source/test pins. It used normal tmp_path and fresh /tmp/bigsmall-oc1-r59-6yj2n4gm/pytest basetemp, PYTHONPATH=src:. and PYTHONDONTWRITEBYTECODE=1. full60-command.json and full60.stdout.txt agree. This one run serves output-isolation validation and independent review. Historical full60 and round58's two existing tests are not added; the unique denominator remains **60**. This reviewer did not rerun pytest, a whole-repository suite or the real factory.

One small CPU script, scoped-probe.py, ran once with exit 0 and **19 passing scenarios**. The planned private seam supplies only raw counter readings and startup identity; actual owner public event/current/age/deadline APIs determine all verdicts. No verdict is mocked. Raw inputs, outputs and exception chains remain in scoped-probe.json; its command/stdout/stderr are saved beside it. The scenarios are not additional pytest cases or calibration groups.

The probe covers MARK→current→END overlap [100,200]/[150,180] → age[0,80]ns; TTL equality/+1ns/midpoint misacceptance at 100 and 2**60 bases; deadline −1/equality/+1ns at both bases; fixed key nonrefresh; foreign/reconstructed/copy/deepcopy/pickle rejection; missing MARK/complete receipt; wrong direct causal linkage; actual decreasing-clock exception cause and closed-owner rejection; namespace-offset drift and permanent revocation. Source-flag kwargs reject before the zero-parameter factory body. This script performs zero real factory body calls and zero BOOTTIME reads.

The review independently recomputed exact AST equivalence. Round58 source allows only the exact typing additions and sole __reduce_ex__ annotations, preserving its rejection body. Round58 tests allow only the target from-import name order; the adjacent path constant is equal. Round59 allows only the sole tmp_path: Path parameter and first artifact assignment. All remaining nodes, assertions, parameterized cases and write payloads are equal; both writes share the tmp_path artifact. Final test-only Ruff check/format records are exit 0. Preserved round58 source Ruff and source-only mypy are exit 0 on the unchanged production pin. Static commands were inspected, not rerun.

## Contract findings

| Contract | Result and source/test anchors |
| --- | --- |
| Causality and legal overlap | PASS. Source 321–369, tests 87–175: event MARK precedes the linked current occurrence; END may follow current. Roles/direct original-token linkage are checked before age clamping. No event upper ≤ current lower requirement. |
| Integer age and TTL | PASS. Source 28–38, 160–176, 354–380; tests 136–165, 210–239: strict int rejects bool/float, age [max(0,n−−c+), n+−c−], TTL upper ≤ limit. Fraction is display only. |
| Fixed original deadline | PASS. Source 188–195, 382–424; tests 242–327: positive integer budget fixes original lower + budget; current upper < deadline, equality rejects. Duplicate key returns exact original; changed origin/budget reject. |
| Live provenance/lifecycle | PASS. Source 46–56, 260–310, 414–431; tests 178–207, 266–327: exact registered objects/domain are required. Equal descriptors, reconstructed, foreign, copied or closed handles do not authorize. |
| Actual Linux source identity | PASS. Source 76–95, 228–289, 447–523; tests 357–496, 559–631: actual boot/PID/start ticks, both thread IDs, thread time namespace dev/inode and both offsets are bound. Comm parsing handles spaces/right parentheses; identity is checked at startup, read before/after and public boundaries. |
| Unsupported source/diagnostics | PASS. Source 119–127, 277–289, 485–536; tests 329–355, 442–459, 498–556: zero-argument BOOTTIME only, source/proc/invalid/decreasing failures reject and revoke as appropriate, no fallback/source flags. Resolution grants no accuracy or authority. |
| Evidence isolation | PASS. Test 559–631 and exact round59 AST: both receipt branches write native tmp_path. Root full60 validates normal fixture behavior; 70 original OC1 artifacts remain unchanged. |

## Real CPU source evidence

New receipt: PASS_REAL_LINUX_STARTUP_CPU_ONLY, SOFTWARE_ONLY, simulation.operational-time.v1, Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME). Top-level/domain field sets match the frozen historical receipt. It records **five real BOOTTIME reads by root's pytest process**. The unique real tmp receipt and new review copy have equal SHA256 e5d702452ce7536df88159695131fbc9622f9998025ae9f0deef3593c11bbba2, 1721 bytes. Old receipt remains SHA256 e5030d84836af43fc79b9a93a356b32f8b567bfa5413c4ad4445bff9fa05fbb5.

The receipt records Linux 7.0.0-38-generic/Python 3.12.3, boot 79fd5afd-e55e-49a5-af98-683b9571e373, pytest PID 2225553, start ticks 34643479, namespace dev/inode 5/4026531834 and both zero offsets. The reviewed passing test asserts PID/start/thread/namespace at test time. This reviewer corroborates present boot/namespace/offsets, not the exited pytest process PID. Event [346435035682305,346435036269739], current [346435036632091,346435036818063], age [362352,1135758] are exact integers consistent with the conservative formula.

The planned BOOTTIME API suspend-inclusion contract differs from this actual CPU-reading evidence. No real suspend, restart or VM hostpause experiment ran. No network/model/camera/physics/provider/render/decode/hardware, fork or host clock adjustment ran in this independent review. Two read-only review tooling failures are preserved faithfully in review-tooling-observation.json: a list/dict formatting assumption raised AttributeError, and a report command's JavaScript Markdown backtick raised SyntaxError before shell. Neither changed files or executed project code. Root confirmed they require no product-plan expansion; no verification was repeated to hide them.

## Acceptance boundary and protection scope

before_deadline proves only checkpoint mathematics at the recorded current bracket. It does not guarantee an action after arbitrary blocking, dispatch/publication, or an unknown full future D/S horizon. Single-thread trusted same-process usage does not promise resistance to malicious same-process mutation, administrators, kernel changes or virtual-clock attacks. Startup nonce/descriptor is not worker/job/lease/fencing authorization. New owner/process cannot restore old live capability; real recovery/deadline-ledger closure remains OC3.

UTC/SI accuracy remains null/UNVERIFIED; native/worker/lease authority UNAVAILABLE; future horizon UNKNOWN; real restart/suspend/VM hostpause NOT_TESTED_OC3_GATE; formal_accepted=false. OC2/3/4, downstream consumer/dispatch integration, native, R4/R5/G1 and formal research gates are not accepted by this SOFTWARE result. Old UTC/native routes are not imported into this module or relaxed.

The final 70-file protection check covers **41 OC1 implementation and 29 OC1 static-fix artifact files**, including frozen source, logs, reports and manifests. Plan59, root before/after and present SHA/bytes agree for those same paths. It is not new before/after proof for all repository sources or old actual raw bytes; historical reports' 667-file checks remain attributed to their historical runs. No complete raw batch, run database, credentials, model weights or SDK was inspected or packaged. A manifest/report is not a complete remote raw reproduction package.
