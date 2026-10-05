# Risk supervision criterion isolation fix

Only owned production/test: risk_supervision.py and test_research_risk_supervision.py. Original reviewed515 closure/artifact bytes remain unchanged.

Finding: registration uses dataclass replace(criteria), preserving mutable workspace_min_m/max_m lists. Auditor copy and concrete RAW copies repeat the same alias.

Plan: (1) qualified min/max caller-list mutation RED through real registered RAW reconstruction plus legitimate tuple/scalar controls; (2) rebuild both workspace sequences as strict finite 3-element detached immutable tuples preserving original numeric values/types, and retain every other CompletionCriteria field; (3) replay the original root counterexample unchanged in the fixed overlay; (4) original37+new owned and full178+new CPU scope excluding the original one dynamics test; scoped Ruff/format2/coldmypy1; (5) exact original515 with owned2 differences only, hashes/AST/artifact preservation, new report and independent review.

No RAW reader, actual admission, simulator state/step/render/capture/provider/network/model/controller action or existing frozen report edits. RISK/METHOD remains UNKNOWN/NOT_RUN.
