# Real Robot Acceptance Levels

Phase 10 defines physical hardware acceptance as a single-level-at-a-time
process. The CLI never runs all levels automatically.

| Level | Scope | Motion |
| --- | --- | --- |
| LEVEL_0 | Read joint, TCP, controller, emergency stop, and fault state | No |
| LEVEL_1 | SAFE_STOP and controller enable/disable checks | No displacement |
| LEVEL_2 | Single-joint small motion | Low-speed, independently confirmed |
| LEVEL_3 | Small TCP free-space motion | Low-speed, away from people/obstacles |
| LEVEL_4 | HOME and named safe poses | Verified named poses only |
| LEVEL_5 | Empty grasp flow | No object contact |
| LEVEL_6 | Soft object, fixed position, low-speed grasp | Controlled contact |

The highest passed level is persisted with full history, source tree hash,
config hash, robot identity hash, evidence path, and operator confirmation
metadata. Levels cannot be skipped: `NONE` can only advance to `LEVEL_0`, then
to `LEVEL_1`, and so on. Current repository evidence has no passed physical
level; real hardware validation is `NOT_STARTED`.
