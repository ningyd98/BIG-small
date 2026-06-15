# Phase 9 Report

Status: `PHASE9_CORE_ACCEPTED + ISAAC_VALIDATION_BLOCKED_BY_ENV`.

Environment summary from `verify_phase9.py`:

- OS: Linux 7.0.0-22-generic x86_64
- CPU: AMD Ryzen 7 5800X
- GPU: NVIDIA GeForce RTX 4070 Ti SUPER
- Driver: 595.71.05
- Python: 3.12.7
- MuJoCo: 3.9.0
- ROS 2 / MoveIt 2: blocked by environment
- Isaac Sim: blocked by environment

MuJoCo runs:

- smoke: 18
- validation: 2250
- full: 11250
- fixed normal static acceptance: 20/20 illegal-collision-free trials

Full benchmark metrics:

- success rate: 0.92
- mean completion time: 972.0 ms
- illegal collisions: 0
- PCSC/GOOD: cloud calls 3.0, detection latency 100.0 ms, completion 845.0 ms
- ETEAC/SEVERE: cloud calls 1.0, detection latency 640.0 ms, recovery 840.0 ms, retransmissions 3.0
- AUTO/NORMAL: cloud calls 2.0, mode switches 1.0, completion 840.0 ms
- seed 0 vs seed 9: joint RMSE mean 0.262719 vs 0.269485; sensor latency mean 6.369358 ms vs 19.24065 ms

Isaac and ROS results are not claimed; their artifacts record blocked environment reasons.
