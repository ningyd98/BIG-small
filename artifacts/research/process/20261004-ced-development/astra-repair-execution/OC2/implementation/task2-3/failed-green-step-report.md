# OC2 Task2/3 first GREEN failure report

Status: PAUSED_UNPLANNED_FIRST_GREEN_FAILURE_ASTRA_REQUIRED.

Expected RED ran once: 21 named new cases failed on missing Task2 runner, 40 original Task1 deselected. The first complete owned CPU run observed 57 passed, 4 failed, 0 skipped (61 unique cases), pytest 401.24 seconds, exit1. No independent acceptance is claimed.

Four failures: RESET and CAPTURE error cases lacked prefix-failures.json; export and catalog error cases had BLOCKED_BY_ENV instead of test expected FAILED/CANCELLED. Full original output and current implementation are preserved; no follow-up repair, static check, R03 regression or test retry was performed. ROOT notified before this evidence freeze. The existing worker terminal mapper was not edited.

Eight owned paths and the separately authorized worker branch were copied byte-exact into failed-green-source-freeze/. Original77 input entries were checked: only authorized owned/worker deltas, no unowned drift. CPU originals remain under /tmp/bigsmall-oc2-task23-green; the denominator manifest does not claim a complete remote raw/DB package. This check does not claim the whole shared repository is unchanged.

Next Astra plan is pending; Task2/3 software, scoped static/narrow regressions, independent review, ROOT unique actual and public reader remain incomplete. Real renderer/physics/camera, model/provider/network and Git are zero.

Evidence SHA256/bytes and exact paths are in failed-green-step-report.json and failed-green-freeze-manifest.json.
