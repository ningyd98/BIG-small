# Phase 9 Simulator Architecture

`SimulatorBackend` exposes reset, step, joint state, TCP pose, contacts, sensor frames, joint targets, gripper commands, emergency stop, and physical fault injection.

MuJoCo is the CI and batch experiment backend. Isaac Sim is a separate-process high-fidelity target through ROS 2 or bridge protocol. Ground truth is reserved for evaluation metrics and is not used as formal control input.
