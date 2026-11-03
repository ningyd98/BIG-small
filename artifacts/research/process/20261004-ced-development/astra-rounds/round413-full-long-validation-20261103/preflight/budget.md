# R413 bounded execution budget

The sums below are worst-case safety ceilings, not elapsed-time forecasts. Estimated actual runtime: hours, potentially extending to the next day. No wait is added when a stage finishes.

| Scope | Initial caps (s) | Contingent never-started tail caps (s) |
| --- | ---: | ---: |
| Python | 605400 | 2794200 |
| Other stages | 29400 | 0 |

Cleanup is bounded at 30 seconds per launched process. Two real dataset nodes are NOT_RUN_EXTERNAL_DATA. Each node may emit STARTED at most once.
