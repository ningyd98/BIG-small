# R252 — source-preparation pin schema correction

Actual author: gpt-6-astra, /root/astra_status_plan; 2026-10-17. Plan only; STOP pending ROOT.

The actual a63cfa exit1 is a metadata KeyError at generator line29, before the first candidate save. R251 observation has 27 `current_sources` rows shaped `{original, physical}`. The live three-field pin is `row.original`; `row.physical` is separately checked archive identity. This is not a product failure. Original source, invocation and tool result remain immutable; independent streams are null.

The sole Sol author may prepare a durable corrected generator after ROOT accepts this plan. Replace only `next(x ... if x['path']==str(p))` with `next(x['original'] ... if x['original']['path']==str(p))`, plus explicit observed-shape and unique-target checks before outputs. Preserve existing exact bytes/hash/before assertions and all generator transformation semantics. A newly detected downstream defect requires STOP, not an unplanned repair.

The complete failed generator is preserved in `before/failed-generator.py.txt`; original failure bytes and current role bytes also have physical copies. The observed five original candidate output paths are absent. Current27 and protected211 all match. Planning's first display was capped by embedded role base64, not a reader failure; no rendered output was parsed. Bounded schema and complete generator text were then reviewed.

ROOT reviews full new `implementation/prepared-generator.py`, its narrow diff, source pin and exact argv before the sole one metadata preparation attempt. Use repository `.venv/bin/python`, explicit finite environment, 120s boundary; complete actual/streams are preserved, displayed summary <=6000 UTF-8 bytes. The generator writes only original candidate artifacts and new R252 evidence, never live product source. This attempt is source preparation, adds zero validation slots and cannot be retried. ROOT must subsequently review every generated product change and 72-entry inventory under R251 before native application.

R223 original ROOT and author ledgers remain the only budget authorities: prepare_green, ruff, green and root_settlement each used0/remaining1. The current legitimate post-activation role generation is pinned in plan.json; older pins resolve only through ledger-links exact physical history. No role/STATE/PHASE changes here. Original R251 plan, source27, protected211, test/fixture and raw are unchanged. ROOT's independently evolving settlement draft is outside this issue and not frozen as an input.

The JSON plan and input-observation contain exact paths, SHA256, current schema/roles and execution preconditions. Success here means metadata preparation eligibility only, never software or T2/T12 acceptance. No product/test/static/import/AST/SQL/Git execution in this planning turn.
