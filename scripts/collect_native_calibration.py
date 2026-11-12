#!/usr/bin/env python3
"""Three exclusive, bounded development collection entry points; no batch or retries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloud_edge_robot_arm.research.native_calibration_collection import (
    collect_native_calibration_once,
    prepare_native_calibration,
    verify_native_calibration_collection,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--collect-once", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--prepare-registered-protocol", action="store_true")
    modes.add_argument("--prepare-registered-collection-protocol", action="store_true")
    modes.add_argument("--prepare-registered-occlusion-collection-protocol", action="store_true")
    modes.add_argument("--prepare-registered-step", action="store_true")
    modes.add_argument("--verify-registered-step", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--assignment-id")
    parser.add_argument("--context", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registered = (
        args.prepare_registered_protocol
        or args.prepare_registered_collection_protocol
        or args.prepare_registered_occlusion_collection_protocol
        or args.prepare_registered_step
        or args.verify_registered_step
    )
    if registered:
        from cloud_edge_robot_arm.research.native_calibration_collection import (
            ROOT,
            load_json,
            prepare_registered_grounding_protocol,
            read_protocol,
            regular,
        )

        if (
            args.prepare_registered_protocol
            or args.prepare_registered_collection_protocol
            or args.prepare_registered_occlusion_collection_protocol
        ):
            if any(
                value is not None
                for value in (
                    args.config,
                    args.protocol,
                    args.assignment_id,
                    args.context,
                    args.prepared,
                    args.repository,
                )
            ):
                parser.error("registered protocol preparation requires only output")
            if args.prepare_registered_occlusion_collection_protocol:
                from cloud_edge_robot_arm.research.native_calibration_collection import (
                    prepare_registered_collection_protocol_v2,
                )

                result = prepare_registered_collection_protocol_v2(output=args.output)
            elif args.prepare_registered_collection_protocol:
                from cloud_edge_robot_arm.research.native_calibration_collection import (
                    prepare_registered_collection_protocol,
                )

                result = prepare_registered_collection_protocol(output=args.output)
            else:
                result = prepare_registered_grounding_protocol(output=args.output)
        else:
            if (
                args.protocol is None
                or args.repository is None
                or args.config is not None
                or args.assignment_id is not None
            ):
                parser.error(
                    "registered preparation/readout requires protocol and existing repository"
                )
            registration = read_protocol(args.protocol)
            if registration["schema_version"] != "native.calibration.operational.v6":
                parser.error("registered preparation requires v6 protocol")
            if (
                args.prepare_registered_step and (args.context is None or args.prepared is not None)
            ) or (
                args.verify_registered_step and (args.prepared is None or args.context is not None)
            ):
                parser.error("prepare step needs context; verify step needs prepared record")
            from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
                SQLiteSimulationJobRepository,
            )

            # Existing concrete reads retain schema/lock bookkeeping.
            # No job or lease mutation is called.
            repository = SQLiteSimulationJobRepository(regular(args.repository))
            if args.prepare_registered_step:
                from cloud_edge_robot_arm.research.native_collection_application import (
                    RegisteredGroundingPreparationApplication,
                    registered_preparation_context,
                )

                app = RegisteredGroundingPreparationApplication.from_protocol(
                    args.protocol, source_root=ROOT
                )
                context = registered_preparation_context(load_json(args.context))
                result = app.prepare_step(repository=repository, **context, output=args.output)
            else:
                from cloud_edge_robot_arm.research.native_full_horizon_originals import (
                    verify_registered_prepared_step,
                )

                result = verify_registered_prepared_step(
                    args.protocol,
                    args.prepared,
                    repository=repository,
                    source_root=ROOT,
                    output=args.output,
                )
    elif any(value is not None for value in (args.context, args.prepared, args.repository)):
        parser.error("registered preparation arguments require a registered mode")
    elif args.prepare_only:
        if args.config is None or args.protocol is not None or args.assignment_id is not None:
            parser.error("prepare requires only config and output")
        result = prepare_native_calibration(args.config, output=args.output)
    else:
        if args.protocol is None or args.config is not None:
            parser.error("collect/verify require protocol and no config")
        if args.collect_once:
            if args.assignment_id is None:
                parser.error("collect requires exactly one assignment")
            result = collect_native_calibration_once(
                args.protocol, assignment_id=args.assignment_id, output=args.output
            )
        else:
            if args.assignment_id is not None:
                parser.error("verify retains all preassigned groups in its denominator")
            result = verify_native_calibration_collection(args.protocol, output=args.output)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    if result.get("status") == "COLLECTION_PARTIAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
