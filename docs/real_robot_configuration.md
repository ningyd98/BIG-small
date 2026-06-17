# Real Robot Configuration

Real robot configuration is separate from simulation configuration. Do not copy
values from `configs/phase9/*` or `configs/safety/test.yaml` into a hardware
profile.

Use `configs/real_robot/example.yaml` only as a template. It contains
placeholders and is intentionally rejected by the loader until replaced with
site-specific values.

Required fields include vendor, model, serial, controller address, ROS
namespace, planning group, links, joint names, low velocity/acceleration scales,
workspace limits, payload limit, emergency stop topic, and hardware status
topic. The loader records a configuration source and stable configuration hash.

No real IP address, serial number, secret, or credential is committed in this
repository.
