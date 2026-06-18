# Simulation Runtime Architecture

Phase 11.1 adds asynchronous orchestration under the Simulation Workbench:

```text
FastAPI /api/v1/simulation
  -> SimulationWorkbenchService
  -> SimulationRuntimeService
  -> SQLiteSimulationJobRepository
  -> SimulationJobDispatcher
  -> SimulationWorker
  -> allowlisted Mock / MuJoCo / blocked backend runner
  -> artifacts + persisted events + metrics
```

`POST /api/v1/simulation/runs` returns immediately with `status=QUEUED`. Workers advance jobs in the background and persist every transition, event, metric set, attempt, lease, and artifact path. WebSocket replay reads the persisted global stream sequence, so restart does not make old runtime events invisible.

The dispatcher never accepts arbitrary shell, executable, script path, module name, or environment input. Browser clients submit high-level experiment drafts only. Real hardware remains out of scope.
