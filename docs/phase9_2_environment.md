# Phase 9.2 Environment

Phase 9.2 requires an Isaac-compatible host:

- Ubuntu 24.04
- NVIDIA RTX GPU
- NVIDIA driver with CUDA visibility
- Vulkan available through `vulkaninfo --summary`
- Isaac Sim 6.0 official standalone runtime or official container
- ROS 2 Jazzy for existing Phase 9.1 runtime paths

Run:

```bash
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

The verifier writes:

- `compatibility_report.json`
- `compatibility_report.md`
- `nvidia_smi.txt`
- `vulkan_summary.txt`
- `isaac_compatibility_checker.log`

The report records OS, CPU, memory, disk, GPU, VRAM/driver output, CUDA visibility, Vulkan status, display/EGL variables, Isaac runtime mode, Isaac Python path, container image/digest when relevant, and ROS environment variables.

If any required host capability is missing, the status is `BLOCKED_BY_ENV`. That is not a pass and cannot be used as Isaac runtime validation.

## Standalone

```bash
export ISAAC_RUNTIME_MODE=standalone
export ISAAC_SIM_ROOT=/path/to/isaac-sim-6.0
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

The checker prefers `${ISAAC_SIM_ROOT}/python.sh scripts/phase9/isaac_standalone_app.py --check-imports`.
For the local Isaac pip/venv runtime it falls back to `${ISAAC_SIM_ROOT}/bin/python`.

## Container

```bash
export ISAAC_RUNTIME_MODE=container
export ISAAC_CONTAINER_IMAGE=nvcr.io/nvidia/isaac-sim:6.0.0
export ISAAC_CONTAINER_DIGEST=sha256:<resolved-digest>
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

Container mode records the fixed image and digest. Floating `latest` tags are rejected by command construction.
