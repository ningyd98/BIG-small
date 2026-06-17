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

The highest passed level is persisted with evidence path and timestamp. Skills
above the current level are rejected. Current repository evidence has no passed
physical level; real hardware validation is `NOT_STARTED`.
