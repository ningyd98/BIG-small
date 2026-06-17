# Phase 10.2B Design

Phase 10.2B adds a local dashboard console for evidence review, software experiments, and safety acceptance visibility.

## Goal

Provide a browser UI backed by a typed API that can show current Phase 10 status without implying real-robot readiness or exposing hardware control paths.

## Backend Design

The backend adds a `dashboard` package and FastAPI router. The router exposes dashboard-specific read models instead of making the browser combine lower-level planning, supervision, risk, and artifact data.

The service layer owns summary derivation, safety snapshots, acceptance snapshots, comparison metrics, and review-note events. Evidence indexing is centralized so path safety and redaction happen in one place.

The experiment manager is a software-only allowlist. It records lifecycle state, stdout/stderr, exit code, blockers, and evidence paths. Jobs run asynchronously and publish audit/event-stream updates.

## Frontend Design

The React dashboard consumes generated OpenAPI types. Pages are API-backed and use TanStack Query for polling and mutation invalidation. The WebSocket hook is used as live status acceleration, while polling remains the fallback.

The UI deliberately repeats the hardware boundary in visible text:

- real robot validation is not started
- highest hardware acceptance level is `NONE`
- hardware motion is forbidden

## Security Design

The browser cannot send raw paths or commands. Token mode avoids URL tokens; WebSocket auth can use a same-origin cookie. Role checks are enforced by the backend.

## Verification Design

Phase 10.2B is accepted only when backend tests, generated schema drift check, frontend unit tests, build, and Playwright E2E pass. The verifier writes `artifacts/phase10/phase10_2b/phase10_2b_verification.json`.
