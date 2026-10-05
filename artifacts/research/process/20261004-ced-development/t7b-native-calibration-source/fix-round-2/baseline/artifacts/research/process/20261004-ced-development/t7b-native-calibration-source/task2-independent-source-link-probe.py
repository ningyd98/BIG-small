"""CPU/SOFTWARE_ONLY review probes; no native publisher or authenticity claim.

Use the existing complete Software RawV3 fixture to isolate whether Task2
reconstruction compares original producer/asset/preregistration metadata to
the registered current recipe. These probes cannot produce a finite bound.
"""

import json
import tempfile
from pathlib import Path

from cloud_edge_robot_arm.research.native_geometry_calibration import (
    reconstruct_registered_calibration,
)
from tests.test_native_calibration_source import digest, registration, rewrite


def probe(kind):
    with tempfile.TemporaryDirectory(prefix="task2-independent-source-link-") as temp:
        root = Path(temp)
        reg, payload = registration(root)
        envelope_path = root / "case-1/envelope.json"
        records_path = root / "case-1/records.json"
        envelope = json.loads(envelope_path.read_text())
        records = json.loads(records_path.read_text())
        identity = envelope["identity"]
        detail = {}
        if kind == "original_producer_drift":
            name = "src/cloud_edge_robot_arm/simulation/mujoco/backend.py"
            identity["source_hashes"][name] = "f" * 64
            detail = {
                "producer_path": name,
                "original_sha256": identity["source_hashes"][name],
                "registered_current_sha256": payload["source_hashes"][name],
            }
        elif kind == "original_asset_mismatch":
            identity["asset_hash"] = "f" * 64
            detail = {
                "original_asset_sha256": identity["asset_hash"],
                "registered_asset_sha256": payload["geometry"]["pose_marker"][
                    "marked_asset_sha256"
                ],
            }
        elif kind == "post_capture_preregistration":
            payload["preregistered_at"] = "2099-01-01T00:00:00+00:00"
            detail = {
                "declared_preregistered_at": payload["preregistered_at"],
                "first_original_pair_utc": records["intervals"][0]["start"]["utc_at"],
            }
        else:
            raise AssertionError(kind)
        for name in ("intervals", "physics", "commands", "actions", "frames", "joins"):
            for row in records[name]:
                row["identity"] = identity
        envelope_path.write_text(json.dumps(envelope))
        records_path.write_text(json.dumps(records))
        payload["original_file_hashes"]["case-1/envelope.json"] = digest(envelope_path)
        payload["original_file_hashes"]["case-1/records.json"] = digest(records_path)
        reg = rewrite(reg, payload)
        result = reconstruct_registered_calibration(reg)
        group = result.groups[0]
        assert result.source_scope == "SOFTWARE_ONLY"
        assert group.status == "COMPLETE"
        assert result.geometry_quantile.bound_m is None
        assert result.action_quantiles["MOVE_ABOVE"].bound_m is None
        return {
            "probe": kind,
            "scope": "SOFTWARE_ONLY; offline consistency guard only",
            "detail": detail,
            "accepted_original_status": group.status,
            "reasons": group.reasons,
            "finite_native_bound": False,
        }


if __name__ == "__main__":
    for candidate in (
        "original_producer_drift",
        "original_asset_mismatch",
        "post_capture_preregistration",
    ):
        print(json.dumps(probe(candidate), sort_keys=True))
