# R167 Role-Specific Held Ledger Metadata Recovery Plan

> **For agentic workers:** Retain the existing sole Sol author and ROOT gating workflow. No new agent or execution method is needed.

**Goal:** Complete the three missing preparation receipts through one new metadata action.

**Architecture:** Preserve the distinct author/ROOT ledger states and the already-prepared test/runner bytes. A new R167 action verifies the original R166 invariants and creates only the missing derived reports.

**Tech Stack:** Project `.venv/bin/python`; stdlib pathlib/json/hashlib/difflib only.

**Spec:** /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013/plan.json; exact paths, full input pins and check contract are in this plan.json.

Actual author: **gpt-6-astra**, `/root/astra_status_plan`. Pending ROOT activation; no recovery action has been executed by the planner.

## Original failure and cause

The original R166 metadata action `0cafa4` actually exited **1** at line 42 with AssertionError. It required ROOT's slot to be `HELD`. Independent full ledger reads confirm author=`HELD`, ROOT=`HELD_PENDING_ROOT_GATE`; both are authorized1/used0/remaining1. ROOT has no schema_version field. The failure is a role/schema assumption, not a product failure.

Original command/source and combined return remain in `original-failure.json` (131360 bytes, SHA256 `7736cab8f1c07af7e5cd499bd3888e3fa8ff217fc2feab9e3ab3b759b8ff9e8c`). Independent process streams were not captured. Earlier checks precede the failed assertion, but no completed receipt can be claimed. All three planned output files remain absent.

## Bounded recovery

- [ ] ROOT reads the plan and verifies its 26 current input pins. Keep all test/source/runner/report/ledger bytes unchanged.
- [ ] Sole `/root/p6_stage_b_sol` prepares one direct stdlib metadata action following the exact ordered contract in plan.json; ROOT reads and hashes the complete source before reserving the new allowance.
- [ ] Preserve all original delta, A-prefix, 22-production, 211-protected, immutable input and absence checks. Use author state `HELD` and ROOT state `HELD_PENDING_ROOT_GATE` separately, compare their full command configurations, and fail closed on any other state/schema. Do not edit ledgers to satisfy a check.
- [ ] Execute the new action exactly once. After every check succeeds, exclusive-create the original three missing R166 change-report/diff/verification outputs, explicitly recording **producer R167** and the original failed action. Print a short receipt summary and retain the actual tool return.
- [ ] ROOT reads the completed delta/receipt and records R167's local step report. Recovery success merely returns to the original R166 ROOT control gate.

## Budgets and acceptance

Original R166 metadata: **1 used / 0 remaining, exit1**, immutable. New R167 metadata: **1 total**, no retry. R166 legacy_control remains **0/1 and held**; original R158 remains **2 spent / 13 held**. No test, static, AST, product import, SQL, probe or Git is authorized. No new helper execution layer is required.

Do not replay the old failed script or rewrite any original artifact. A schema mismatch, unexpected file, output collision or new failure stops for another actual Astra plan. Metadata recovery is not a control PASS, T1 GREEN, B9 completion, or native/physical/actual/formal acceptance.

