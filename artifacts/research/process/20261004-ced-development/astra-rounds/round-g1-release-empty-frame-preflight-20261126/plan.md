# round-g1-release-empty-frame-preflight-20261126

Plan only. At HEAD `9172d8e17616a0a500d61949f4c369f4baae24cd`, place this round beside `round-g1-release-replay-cleanup-20261126` under `artifacts/research/process/20261004-ced-development/astra-rounds`.

Cold verification of inherited A01 matched all 5,637 dense steps and 502 pose samples. The original A01 was not rerun. The recovery positive check failed before new physics because `backend._sensor_frame is not None` rejects the valid constructor placeholder. Frozen `backend.py` line 318 creates an empty `SensorFrame` named `camera` at time zero with zero width and height. On-demand reset retains that instance.

1. Preserve both failure snapshots byte-for-byte. Sign a new recovery registration before running controls. Limit the change to the diagnostic. Keep backend, safety and application code, experimental values, parent validations and physical score qualification unchanged.
2. Before reset, capture `original = backend.get_sensor_frame()`. Before reset, under on-demand reset, after scope exit and after shutdown, require `backend.get_sensor_frame() is original`. At each checkpoint independently verify name `camera`, frame time zero, width and height zero, and no pixels. Require camera `None`, `q = -0.8`, simulation time and tick zero, no commands, and stable context cleanup across exit and shutdown.
3. Require rejection of a distinct placeholder with the same name and empty fields. Retain the parent’s wrong-sentinel-instance control and genuine body, writer and shutdown failure controls, with their registered outcomes.
4. Keep `replay-02` untouched until every preflight and parent entry gate passes. Then run only two A followed by three B under the parent validations. A failed gate stops progression. Apply the parent’s physical score qualification unchanged.
