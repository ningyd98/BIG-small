# Roadmap

## Current Stage

Phase 10.2A-R consolidates repository documentation, project structure explanations, verification entrypoints, CI checks, changelog, and contribution rules.

## Next Stages

- Phase 10.2B: Experiment and Safety Acceptance Console.
- Phase 10.2C: Real Robot Level 0 read-only acceptance.
- Phase 10.3: Low-speed motion and real task experiments.
- Phase 10.4: Paper experiments, patent materials, and final result sealing.

## Phase 10.2B Boundary

The Phase 10.2B frontend is not a browser robot remote controller. It may present experiment state, safety gates, operator workflow, and evidence browsing through FastAPI/WebSocket APIs. It must not connect directly to ROS 2 trajectories, MoveIt execute, or a real controller.
