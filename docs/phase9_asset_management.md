# Phase 9 Asset Management

Assets are tracked in `assets/manifest.yaml` with path, SHA256, source, version, license, and SI units. Large assets, local caches, videos, image frames, ROS build outputs, and Isaac caches are gitignored.

The committed MJCF is a small BIG-small reference asset for deterministic CI physics validation, not an official Franka model.
