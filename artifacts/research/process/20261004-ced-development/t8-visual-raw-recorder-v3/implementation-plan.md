# Actual Raw-v3 Recorder Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this parent-assigned scoped implementation; each unit uses RED/GREEN and immutable independent review.

**Goal:** Record complete real operation sources and actual paired clocks through the sole backend/capture/executor without granting actual authority.

**Architecture:** A narrow independent backend observer emits detached BEGIN/END and a minimal failure/allocation ledger. A new recorder consumes those actual events, wraps existing capture/executor exactly once, persists complete sources and rebuilds the existing strict raw-v3 graph.

**Tech Stack:** Python3.12, existing dataclasses/Pydantic, pathlib/json/hashlib/time, existing MuJoCo interfaces, pytest/Ruff/mypy.

**Spec:** design.md in this artifact directory; exact seven-source baseline in design-source-hashes.json.

## Global Constraints

Only new recorder/test and explicitly authorized backend observer edits. Original raw-v3/risk/owner/runtime/executor/camera unchanged. Scope SOURCE_CONSISTENCY_ONLY, no actual method/clock/native acceptance. No experiment/model/render/controller command; one explicit passive render-disabled source test allowed. Keep all partial/exception/refused allocations. Root later installs true worker path. Raw reader formula/time compatibility is pending root correction; never rewrite actual sources.

## Review Focus

- An observer exception during hard stop must preserve the actual stop and failed-source denominator.
- RESET/implicit camera operations before planned identity must remain recorded without placeholder owner.
- Same-step commands and delayed effects must retain exact ordered ranges and previous state joins.
- Genuine source/UTC/frame bytes cannot be edited to satisfy old reader equalities.
- Later flush must reread source/frame files and invalidate stale COMPLETE.

## Task1: Backend readonly boundaries

- [ ] Write qualified missing API and actual passive event ordering/coexisting legacy observer/recursive mutation/hard-stop failure tests.
- [ ] Run RED and archive exact test source/log before production change.
- [ ] Implement BackendOperationBoundary and observe_operation_boundaries plus readonly failure/allocation/overhead ledger, preserving unhooked behavior.
- [ ] Run focused GREEN; inspect truthful actual two passive step events and no renderer/controller commands.

## Task2: Recorder binding/journal/graph

- [ ] Write missing module RED with full concrete instance/source/path/clock and incomplete bootstrap assertions.
- [ ] Implement VisualRawRecorderV3 context, source inventory check, clock samples, purpose ranges and identity/source binding, consuming real events.
- [ ] Write and watch qualified RED for full software control/physics graph, action actual returned/rejected/partial results and acquisition/allocation/file joins.
- [ ] Implement exact existing capture/executor wrappers and immutable result/flush, keeping the full failed denominator and reraising original exceptions.
- [ ] Run focused GREEN and corrected-reader compatibility when root frozen handoff is available.

## Task3: Frozen scoped handoff

- [ ] Run owned and related CPU scopes; no fullsuite or actual experiment. Ruff/format3 and cold mypy2.
- [ ] Snapshot exact reviewed base plus owned3; clearly pin any corrected reader dependency release rather than moving root integration.
- [ ] Rerun scoped commands in independent overlay, hash/AST/source/file/old-release checks.
- [ ] Write report/json/ownership/source manifests/diff and exact RED/GREEN logs, freeze production then request independent review via parent. No commit.
