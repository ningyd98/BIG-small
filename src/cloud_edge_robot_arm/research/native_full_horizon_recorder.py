"""Single live source recorder with bounded frame spooling and original OC1 events.

Large image/instance arrays are saved once at acquisition, before another physics
step. Their exact bytes are referenced by a complete inventory; summary rows are
never substituted for those originals by the independent reader.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from contextlib import contextmanager
from dataclasses import asdict, fields
from typing import Any

from cloud_edge_robot_arm.research.native_calibration_collection import canonical, digest
from cloud_edge_robot_arm.research.native_calibration_collection import detached as _plain
from cloud_edge_robot_arm.research.raw_episode_v3 import RawEpisodeIdentityV3
from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary
from cloud_edge_robot_arm.simulation.mujoco.native_horizon import FullHorizonExecutionReceipt
from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3, _error

_ISSUER = object()
ENCODED_FIELDS = {
    "rgb_png_base64": "rgb.png",
    "depth_float32_base64": "depth.f32",
    "valid_mask_base64": "mask.u8",
}


class NativeFullHorizonRecorder(VisualRawRecorderV3):
    def _before_executor_attempt(
        self, *, contract: Any, step: Any, attempt: int, grounding: Any
    ) -> None:
        """仅 v7 在真实执行器入口消费应用绑定的 PRE；旧采集路径保持原样。"""
        from cloud_edge_robot_arm.vision.owner_registration import RegisteredCollectionStepBinding

        if type(grounding) is RegisteredCollectionStepBinding or (
            getattr(self.application, "protocol", {}).get("schema_version")
            == "native.calibration.operational.v7"
        ):
            self.application._validate_registered_dispatch(
                self, contract=contract, step=step, attempt=attempt, binding=grounding
            )

    def __init__(
        self, *args: Any, application: Any, owner: Any, _token: object | None = None, **kwargs: Any
    ) -> None:
        if _token is not _ISSUER:
            raise TypeError("live collection application must issue this recorder")
        super().__init__(*args, **kwargs)
        if callable(getattr(self.capture_session, "transform_observation", None)):
            raise ValueError("collection requires original untransformed acquisitions")
        self.application, self.owner = application, owner
        self.operational_events: list[dict[str, Any]] = []
        self._pending: dict[int, tuple[dict[str, Any], Any]] = {}
        self.capture_receipts: dict[str, tuple[Any, Any]] = {}
        self.inventory: dict[str, dict[str, Any]] = {}
        self.frame_sources: dict[str, str] = {}
        self.horizons: list[dict[str, Any]] = []
        self.hold_mappings: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.failures: list[dict[str, str]] = []
        self.bytes_written = self.render_passes = 0
        # R439's registered explicit + implicit capture budget, including failures.
        self._render_attempt_limit = 12976 + 12962
        self._render_attempts: dict[int, dict[str, Any]] = {}
        self._render_overflow_count = 0
        self._first_unrecorded_capture: int | None = None
        self.control_sources: dict[int, dict[str, Any]] = {}
        self._published = False
        self._sample_slot = 0
        self._capture_roles: dict[int, dict[str, Any]] = {}
        self.grounding_sources: dict[int, dict[str, str]] = {}
        self.shield_config_source: dict[str, str] | None = None

    @property
    def render_accounting(self) -> dict[str, Any]:
        attempts = list(self._render_attempts.values())
        unknown = [row["operation_id"] for row in attempts if not row["complete_return"]]
        if self._first_unrecorded_capture is not None:
            unknown.append(self._first_unrecorded_capture)
        exact = not unknown and not self._render_overflow_count
        return dict(
            schema_version="native.render.accounting.v1",
            known_completed_passes=self.render_passes,
            exact_passes=self.render_passes if exact else None,
            status="EXACT" if exact else "LOWER_BOUND" if self.render_passes else "UNAVAILABLE",
            attempt_count=len(attempts) + self._render_overflow_count,
            unknown_operation_ids=unknown,
            unrecorded_attempt_count=self._render_overflow_count,
            attempts=_plain(attempts),
            provenance="CAPTURE_END_RETURNED_PASSES_BEFORE_PERSISTENCE",
        )

    def _begin_render_attempt(self, event: BackendOperationBoundary) -> None:
        if event.operation_id in self._render_attempts:
            raise RuntimeError("duplicate capture BEGIN")
        if len(self._render_attempts) >= self._render_attempt_limit:
            self._render_overflow_count += 1
            if self._first_unrecorded_capture is None:
                self._first_unrecorded_capture = event.operation_id
            raise RuntimeError("registered capture accounting budget exhausted")
        scheduled = (
            self.backend._step_capture_active
            and self.backend._step_capture_count == self._sample_slot + 1
        )
        self._render_attempts[event.operation_id] = dict(
            operation_id=event.operation_id,
            expected_pass_count=3 if self._explicit_capture or scheduled else 2,
            returned_pass_count=None,
            end_seen=False,
            complete_return=False,
            result_source="PENDING_CAPTURE",
        )

    def _end_render_attempt(self, event: BackendOperationBoundary) -> None:
        attempt = self._render_attempts.get(event.operation_id)
        if attempt is None:
            raise RuntimeError("capture END without accounting allocation")
        if attempt["end_seen"]:
            raise RuntimeError("duplicate capture END")
        attempt["end_seen"] = True
        hashes = (event.result or {}).get("pass_state_hashes")
        if isinstance(hashes, (list, tuple)) and all(isinstance(v, str) for v in hashes):
            attempt["returned_pass_count"] = len(hashes)
            self.render_passes += len(hashes)
            attempt["complete_return"] = (
                event.error_type is None and len(hashes) == attempt["expected_pass_count"]
            )
        attempt["result_source"] = (
            "CAPTURE_END_RETURNED_PASSES"
            if attempt["complete_return"]
            else "CAPTURE_END_WITHOUT_COMPLETE_RETURN"
        )

    def require_clean_reset(self) -> None:
        """Veto retained RESET source failures before entering the first-step guard."""
        self._require_open()
        if self.failures or self._audit_failures or self.backend.operation_observer_failures:
            raise RuntimeError("reset source has retained observer or audit failure")
        metadata, result = self._reset_metadata, self._reset_result
        operations = self.operational_events
        if (
            self._reset_count != 1
            or not metadata
            or not result
            or self.backend.total_physics_steps != 0
            or self._pending
            or [row["kind"] for row in operations] != ["RESET", "CAPTURE"]
            or any(row["error_type"] or row["bracket"] is None for row in operations)
            or result["physics_state"]["episode_id"] != self.backend._episode_id
            or result["physics_state"]["physics_step"] != 0
            or metadata["config"] != _plain(self.backend._config)
            or metadata["scenario"] != _plain(self.backend._scenario)
            or metadata["asset_hash"] != self._current_asset_hash()
        ):
            raise RuntimeError("reset source is incomplete or inconsistent")
        capture = operations[1]
        aid = capture["acquisition_id"]
        if (
            self._allocated_frames != [aid]
            or set(self.frame_sources) != {aid}
            or aid not in self.capture_receipts
            or self._capture_roles[capture["operation_id"]]["role"]
            != "IMPLICIT_SENSOR_CACHE_UPDATE"
            or self.render_accounting["exact_passes"] != 2
        ):
            raise RuntimeError("reset source lacks its complete two-pass acquisition")
        interval_id = f"operation-{capture['operation_id']}"
        operation = self._operations.get(capture["operation_id"], {})
        interval = operation.get("row")
        intervals = [row for row in self._intervals if row["interval_id"] == interval_id]
        if (
            not isinstance(interval, dict)
            or len(intervals) != 1
            or interval != intervals[0]
            or interval["interval_id"] != interval_id
            or operation.get("acquisition_id") != aid
            or interval["kind"] != "ACQUISITION"
            or interval["disposition"] != "COMPLETE"
            or interval["error"] is not None
        ):
            raise RuntimeError("reset source acquisition conversion did not complete")
        frames = [row for row in self._frames if row["acquisition_id"] == aid]
        if len(self._frames) != 1 or len(frames) != 1 or frames[0]["interval_id"] != interval_id:
            raise RuntimeError("reset source frame identity is incomplete")
        payload = frames[0]["observation_payload"]
        identity_fields = ("observation_id", "checksum_sha256")
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(key), str) or not payload[key] for key in identity_fields
        ):
            raise RuntimeError("reset source observation payload is incomplete")
        source_frame = None
        for name, expected in self.inventory.items():
            try:
                raw = (self.directory / name).read_bytes()
            except OSError as error:
                raise RuntimeError("reset source original is unavailable") from error
            if (
                len(raw) != expected["bytes"]
                or hashlib.sha256(raw).hexdigest() != expected["sha256"]
            ):
                raise RuntimeError("reset source original changed before first step")
            if name == self.frame_sources[aid]:
                try:
                    source = json.loads(raw)
                except (ValueError, UnicodeDecodeError) as error:
                    raise RuntimeError("reset source frame metadata is invalid") from error
                if not isinstance(source, dict) or not isinstance(source.get("frame"), dict):
                    raise RuntimeError("reset source frame metadata is incomplete")
                source_frame = source["frame"]
        if (
            source_frame is None
            or source_frame.get("acquisition_id") != aid
            or source_frame.get("interval_id") != interval_id
            or not isinstance(source_frame.get("observation_payload"), dict)
            or any(
                source_frame["observation_payload"].get(key) != payload[key]
                for key in identity_fields
            )
        ):
            raise RuntimeError("reset source original observation identity is incomplete")

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self._observer_context.__exit__(exc_type, exc, traceback)
        finally:
            self._open = False

    def _write_blob(self, name: str, raw: bytes) -> str:
        if self._published or name in self.inventory:
            raise RuntimeError("original output cannot be overwritten or extended after freeze")
        if self.bytes_written + len(raw) > self.application.policy["raw_bytes"]:
            raise RuntimeError("registered original output budget exhausted")
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
        sha = hashlib.sha256(raw).hexdigest()
        self.inventory[name] = dict(bytes=len(raw), sha256=sha)
        self.bytes_written += len(raw)
        return sha

    def _write_original(self, name: str, value: Any) -> str:
        return self._write_blob(name, canonical(_plain(value)) + b"\n")

    def acquisition_source(self) -> dict[str, Any]:
        aid, _, _ = self.current_capture()
        name = self.frame_sources[aid]
        return dict(acquisition_id=aid, path=name, sha256=self.inventory[name]["sha256"])

    def record_grounding(self, evidence: dict[str, Any]) -> None:
        index = evidence["index"]
        name = f"grounding/step-{index + 1}.json"
        sha = self._write_original(name, dict(evidence, acquisition=self.acquisition_source()))
        self.grounding_sources[index] = dict(path=name, sha256=sha)

    def record_shield_config(self, shield: Any) -> None:
        config = shield.config
        hard = config.hard_limits.model_dump(mode="json")
        policy = config.operational_policy.model_dump(mode="json")
        for value in (hard, policy):
            if value["low_height_exception_skills"] is not None:
                value["low_height_exception_skills"] = sorted(value["low_height_exception_skills"])
        merged = {
            field.name: (
                sorted(config.merged.low_height_exception_skills)
                if field.name == "low_height_exception_skills"
                else _plain(getattr(config.merged, field.name))
            )
            for field in fields(config.merged)
        }
        name = "shield/config.json"
        sha = self._write_original(
            name,
            dict(
                hard_limits=hard,
                operational_policy=policy,
                merged=merged,
                policy_version=config.policy_version,
                policy_hash=config.policy_hash,
                rule_count=shield.rule_count,
                source_generation=digest(dict(self.source_hashes)),
            ),
        )
        self.shield_config_source = dict(path=name, sha256=sha)

    def check_shield(
        self, shield: Any, context: Any, *, index: int, phase: str
    ) -> tuple[Any, dict[str, Any]]:
        if phase not in {"PRE", "POST"} or self.shield_config_source is None:
            raise ValueError("original PRE/POST Shield configuration required")
        name = f"shield/step-{index + 1}-{phase.lower()}"
        source = dict(
            method=phase.lower() + "_check",
            index=index,
            step_id=context.step_id,
            context=context.model_dump(mode="json"),
            config=self.shield_config_source,
            source_generation=digest(dict(self.source_hashes)),
            acquisition=self.acquisition_source(),
            grounding=self.grounding_sources[index],
        )
        input_sha = self._write_original(name + "-input.json", source)
        try:
            result = getattr(shield, source["method"])(context)
        except BaseException as error:
            try:
                self._write_original(
                    name + "-result.json",
                    dict(
                        input_sha256=input_sha,
                        result=None,
                        error_type=type(error).__name__,
                        error=_error(error),
                    ),
                )
            except BaseException as write_error:
                self.record_failure("shield_exception_recording", write_error)
            raise
        output_sha = self._write_original(
            name + "-result.json",
            dict(input_sha256=input_sha, result=_plain(result), error_type=None, error=None),
        )
        return result, dict(
            input=dict(path=name + "-input.json", sha256=input_sha),
            result=dict(path=name + "-result.json", sha256=output_sha),
            grounding=self.grounding_sources[index],
        )

    def _record_frame(self, event: BackendOperationBoundary, operation: dict[str, Any]) -> None:
        super()._record_frame(event, operation)
        frame = self._frames[-1]
        aid = frame["acquisition_id"]
        payload = frame["observation_payload"]
        aux = self._frame_aux[aid]
        hashes = {}
        encoded = {}
        string_hashes = {}
        if payload is not None:
            for field, filename in ENCODED_FIELDS.items():
                value = payload.get(field)
                if value is not None:
                    name = f"frames/{aid}/{filename}"
                    raw = base64.b64decode(value, validate=True)
                    hashes[name] = self._write_blob(name, raw)
                    if base64.b64encode(raw).decode() != value:
                        self._write_blob(f"frames/{aid}/{field}.original", value.encode())
                        raise ValueError("noncanonical encoded field retained but not qualified")
                    encoded[field] = name
                    string_hashes[field] = hashlib.sha256(value.encode()).hexdigest()
        ids = aux.get("instance_ids", ())
        name = f"frames/{aid}/instances.i32"
        hashes[name] = self._write_blob(name, struct.pack(f"<{len(ids)}i", *ids))
        frame["file_hashes"] = hashes
        # The complete metadata and lossless encoded-field map reconstruct exactly
        # the RawV3 frame. Keep only small identity metadata in the live join table.
        metadata = _plain(frame)
        if payload is not None:
            metadata["observation_payload"] = {
                key: value for key, value in payload.items() if key not in encoded
            }
        source = f"frames/{aid}/source-frame.json"
        self._write_original(
            source,
            dict(
                frame=metadata,
                encoded_fields=encoded,
                capture_source=self._capture_roles[event.operation_id],
                encoded_string_sha256=string_hashes,
                observation_payload_sha256=digest(payload),
                instance_labels=aux.get("instance_labels", {}),
                instance_count=len(ids),
                instance_ids_present="instance_ids" in (event.result or {}),
                instance_labels_present="instance_labels" in (event.result or {}),
                instances_available=bool(ids),
                pass_count=len(frame["pass_state_hashes"]),
            ),
        )
        self.frame_sources[aid] = source
        if payload is not None:
            frame["observation_payload"] = {
                key: payload[key] for key in ("observation_id", "checksum_sha256")
            }
        del self._frame_aux[aid]

    def _on_boundary(self, event: BackendOperationBoundary) -> None:
        row: dict[str, Any] | None = None
        try:
            if event.kind == "CONTROL" and event.phase == "END" and event.error_type is None:
                if event.operation_id in self.control_sources or len(self.control_sources) >= 12961:
                    raise RuntimeError("duplicate or over-budget original CONTROL")
                if event.result is None or "control_state" not in event.result:
                    raise RuntimeError("original CONTROL result unavailable")
                self.control_sources[event.operation_id] = dict(
                    operation_id=event.operation_id,
                    interval_id=f"operation-{event.operation_id}",
                    episode_id=event.episode_id,
                    physics_step=event.physics_step,
                    control_state=_plain(event.result["control_state"]),
                )
            if event.kind == "CAPTURE":
                if event.phase == "BEGIN":
                    self._begin_render_attempt(event)
                else:
                    # Count returned effects before pop, spooling or owner callbacks can fail.
                    self._end_render_attempt(event)
            if event.phase == "BEGIN":
                row = dict(
                    sequence=len(self.operational_events) + 1,
                    operation_id=event.operation_id,
                    kind=event.kind,
                    begin_step=event.physics_step,
                    end_step=None,
                    episode_id=event.episode_id,
                    token=None,
                    bracket=None,
                    acquisition_id=None,
                    error_type=None,
                    error=None,
                )
                self.operational_events.append(row)
                token = self.owner.begin_event(event.kind)
                row["token"] = token.event_identity
                self._pending[event.operation_id] = (row, token)
                if event.kind == "CAPTURE":
                    self.application.check_active()
                    slot = self.backend._step_capture_count
                    if self._explicit_capture:
                        role = "REGISTERED_ACTION_BOUNDARY"
                    elif slot == self._sample_slot + 1 and self.backend._step_capture_active:
                        role = "REGISTERED_PER_PHYSICS_STEP"
                        self._sample_slot = slot
                    elif slot == self._sample_slot:
                        role = "IMPLICIT_SENSOR_CACHE_UPDATE"
                    else:
                        raise RuntimeError("unregistered capture slot")
                    self._capture_roles[event.operation_id] = dict(
                        role=role,
                        sample_slot=slot,
                        operation_id=event.operation_id,
                        physics_step=event.physics_step,
                        instances_requested=role != "IMPLICIT_SENSOR_CACHE_UPDATE",
                    )
                super()._on_boundary(event)
                if event.kind == "CAPTURE":
                    row["acquisition_id"] = self._operations[event.operation_id]["acquisition_id"]
                return
            row, token = self._pending.pop(event.operation_id)
            row.update(end_step=event.physics_step, error_type=event.error_type, error=event.error)
            super()._on_boundary(event)
            if event.error_type:
                return
            if event.result is None:
                raise ValueError("successful source operation lacks returned original")
            if event.kind == "CAPTURE":
                self.application.check_active()
            self.owner.mark_event(token)
            bracket = self.owner.end_event(token)
            row["bracket"] = _plain(asdict(bracket))
            aid = row["acquisition_id"]
            if aid is not None:
                self.capture_receipts[aid] = (token, bracket)
        except BaseException as error:
            if row is not None:
                row.update(error_type=type(error).__name__, error=_error(error))
            self.record_failure("source_observer", error)
            raise

    def record_failure(self, phase: str, error: BaseException) -> None:
        self.failures.append(
            dict(phase=phase, error_type=type(error).__name__, error=_error(error))
        )

    def bind_collection_source(self, application: Any) -> None:
        source = application.recorder_source(self)
        original = source["original"]
        metadata = self._reset_metadata
        if metadata is None or metadata["asset_hash"] != source["asset_sha256"]:
            raise ValueError("original reset asset does not match registration")
        episode_id = self.backend._episode_id
        if not episode_id:
            raise ValueError("actual source episode identity unavailable")
        raw_identity = RawEpisodeIdentityV3(
            attempt_id="attempt-" + digest(source["attempt_basis"]),
            assignment_id=source["assignment_id"],
            assignment_hash=digest(source["assignment_basis"]),
            episode_id=episode_id,
            source_kind="GROUND_TRUTH_TEACHER",
            owner_identity=original.identity,
            scene_hash=digest(metadata["scenario"]),
            asset_hash=metadata["asset_hash"],
            config_hash=digest(metadata["config"]),
            role_bundle_hash=original.role_bundle_hash,
            model_snapshot_hash=None,
            source_hashes=self.source_hashes,
            clock_domain_id=self._clock_domain_id,
        )
        super().bind_source(raw_identity, original)
        self._write_original("original-plan.json", original.to_payload())
        self._write_original(
            "source-binding.json",
            {key: _plain(value) for key, value in source.items() if key != "original"},
        )

    def current_capture(self) -> tuple[str, Any, Any]:
        aid = self._last_online_id
        if aid is None or aid not in self.capture_receipts:
            raise RuntimeError("original explicit current acquisition required")
        token, bracket = self.capture_receipts[aid]
        return aid, token, bracket

    def record_horizon(self, receipt: FullHorizonExecutionReceipt) -> None:
        self._require_open()
        self.horizons.append(asdict(receipt))

    @contextmanager
    def purpose(self, kind: str) -> Any:
        with super().purpose("HOLD" if kind == "FULL_HORIZON_HOLD" else kind) as interval:
            if kind == "FULL_HORIZON_HOLD":
                self.hold_mappings.append(
                    dict(
                        semantic_kind=kind,
                        raw_kind="HOLD",
                        interval_id=interval,
                        action_span_id=self._actions[-1]["span_id"] if self._actions else None,
                    )
                )
            yield interval

    def capture(self) -> Any:
        self.application.check_active()
        observation = super().capture()
        self.application.check_active()
        return observation

    def freeze(self) -> dict[str, Any]:
        self._require_open()
        if self._published:
            raise RuntimeError("collection originals already frozen")
        registered = (
            getattr(self.application, "protocol", {}).get("schema_version")
            == "native.calibration.operational.v7"
        )
        actions = self._actions
        if registered:
            from cloud_edge_robot_arm.research.raw_episode_v3 import (
                RegisteredCollectionActionSpanV1,
            )

            actions = [
                RegisteredCollectionActionSpanV1.from_payload(
                    dict(
                        schema_version="native.registered.action-span.v1",
                        identity=self._identity.to_payload(),
                        **_plain(row),
                    )
                ).to_payload()
                for row in actions
            ]
        self._write_original(
            "partial-originals.json",
            dict(
                schema_version=(
                    "native.registered.full-horizon.originals.v1"
                    if registered
                    else "native.full-horizon.originals.v1"
                ),
                source_scope="REGISTERED_MODEL_TEACHER_COLLECTION"
                if registered
                else "TEACHER_COLLECTION",
                identity=self._identity.to_payload() if self._identity is not None else None,
                descriptor=self._descriptor.to_payload() if self._descriptor is not None else None,
                reset=self._reset_result,
                reset_metadata=self._reset_metadata,
                reset_count=self._reset_count,
                intervals=self._intervals,
                physics=self._physics,
                commands=self._commands,
                control_sources=list(self.control_sources.values()),
                actions=actions,
                joins=self._joins,
                frame_sources=self.frame_sources,
                allocated_frames=self._allocated_frames,
                allocated_actions=self._allocated_actions,
                allocated_purposes=self._purpose_allocations,
                operational_events=self.operational_events,
                pending_operation_ids=sorted(self._pending),
                backend_operation_ledger=self.backend.operation_ledger,
                observer_failures=self.backend.operation_observer_failures,
                audit_failures=self._audit_failures,
                total_physics_steps=self.backend.total_physics_steps,
                horizons=self.horizons,
                hold_mappings=self.hold_mappings,
                decisions=self.decisions,
                failures=self.failures,
                guard_events=self.backend.execution_guard_events,
                render_passes_observed=self.render_passes,
                render_accounting=self.render_accounting,
                capture_source_roles=self._capture_roles,
                source_hashes=self.source_hashes,
                legacy_utc_mapping="UNAVAILABLE",
            ),
        )
        manifest = dict(
            schema_version=(
                "native.registered.full-horizon.inventory.v1"
                if registered
                else "native.full-horizon.inventory.v1"
            ),
            files=dict(self.inventory),
            file_count=len(self.inventory),
            original_bytes=self.bytes_written,
            inventory_sha256=digest(self.inventory),
            native_qualification="UNKNOWN",
        )
        self._write_original("inventory.json", manifest)
        self._published = True
        return manifest
