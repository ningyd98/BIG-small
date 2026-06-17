# Dashboard Architecture

The Phase 10.2B dashboard is a browser console for software evidence, simulation jobs, and safety acceptance review. It is not a robot control surface.

## Components

- Backend API: `src/cloud_edge_robot_arm/cloud/api/dashboard.py` exposes the `/api/v1/dashboard` read model, software experiment allowlist, evidence APIs, audit events, and WebSocket stream.
- Dashboard service: `src/cloud_edge_robot_arm/dashboard/service.py` composes summary, runtime, safety, acceptance, comparison, review-note, and event-stream data.
- Evidence index: `src/cloud_edge_robot_arm/dashboard/evidence_index.py` scans artifact files under the configured artifact root and rejects path traversal, root-escaping symlinks, oversized files, and unsupported extensions.
- Job manager: `src/cloud_edge_robot_arm/dashboard/experiment_jobs.py` runs only allowlisted software adapters and writes job evidence under `dashboard_jobs`.
- Frontend: `dashboard/src` is a React console generated against the backend OpenAPI schema.
- Local dev app: `src/cloud_edge_robot_arm/cloud/api/dev_dashboard_app.py` starts the API with the deterministic mock planner.

## Data Flow

The browser reads one dashboard API. It does not parse artifacts directly and does not connect to ROS 2, MoveIt, `ros2_control`, vendor SDKs, or controller addresses.

Software experiment requests pass through the backend allowlist. The request body names an experiment kind, scenario, seed, and control mode; it does not accept commands, scripts, executables, environment variables, or arbitrary paths.

WebSocket events are emitted by the shared `DashboardEventStream`. Events have monotonically increasing sequence numbers, replay by `last_sequence`, and heartbeat messages.

## Hardware Boundary

Phase 10.2B keeps:

- `real_robot_validation=NOT_STARTED`
- `highest_acceptance_level=NONE`
- `hardware_write_operations=[]`
- `hardware_motion_authorized=false`

The dashboard can start software-only experiments and record safety review notes. It cannot authorize or trigger physical motion.
