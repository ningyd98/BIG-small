"""Join the two registered static jobs to their anonymous final sweep after both cold reads."""

import base64
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.graduation.perception_io import read, sha, write

HERE = Path(__file__).resolve().parent
RAW = Path("experiments/results/g1-cv-grasp-validation-20261125")
PACKAGE = HERE.parent / "round-g1-cv-sweep-route-binding-20261125/route-candidates.public.json"
CAPTURES = HERE.parent / "round-g1-cv-static-mass-verification-20261125/capture-v2.public.json"


def read_slots():
    initial = HERE / "prospective-registration.public.json"
    receipts = read(CAPTURES)["captures"]
    assert read(initial)["slots"] == read(RAW / "capture-v2/registration.json")["slots"]
    assert [s["id"] for s in read(initial)["slots"]] == [s["slot"] for s in receipts]
    matrix = read(PACKAGE)
    packed = base64.b64decode(matrix["data_base64"], validate=True)
    assert hashlib.sha256(packed).hexdigest() == matrix["full_gzip_sha256"]
    rows = gzip.decompress(packed)
    assert hashlib.sha256(rows).hexdigest() == matrix["full_uncompressed_sha256"]
    first = matrix["readback_first"]
    second = matrix["readback_second"]
    cases = {a["key"]: (r, a, b) for r, a, b in zip(json.loads(rows), first, second, strict=True)}
    assert len(cases) == len(first) == 14
    slots = []
    for receipt in receipts:
        token = receipt["token"]
        folder = RAW / "capture-v2/blind" / token
        row, cold_a, cold_b = cases[token]
        assert cold_a["key"] == cold_b["key"] and cold_a["sha256"] == cold_b["sha256"]
        assert cold_a["worker_pid"] != cold_b["worker_pid"]
        assert sha(folder / "frame.json") == cold_a["frame_sha256"] == receipt["frame_sha256"]
        assert sha(folder / "proprio.json") == cold_a["proprio_sha256"] == receipt["proprio_sha256"]
        assert row["frame_id"] == receipt["frame_id"] and row["checksum"] == receipt["checksum"]
        assert read(RAW / "capture-v2" / receipt["slot"] / "job-close.json") == receipt["job"]
        counts = Counter(r["full_physical_clearance"] for r in row["candidates"])
        assert dict(counts) == row["counts"] and counts["CLEAR"] == 0 and row["selected"] is None
        high = row["initial_routes"]["existing_tool_closure_axis"]
        assert high["status"] in {"BLOCKED", "UNKNOWN"} and row["status"] == "UNKNOWN"
        support = sum(
            r["geometric_status"] == "CLEAR" and r["load_support"]["status"] == "WITNESS"
            for r in row["candidates"]
        )
        assert receipt["commands"] == receipt["physics_steps"] == 0
        slots.append(
            dict(
                slot=receipt["slot"],
                anonymous_token=token,
                frame_id=row["frame_id"],
                archived_candidate_file_sha256=cold_a["sha256"],
                current_marker_ids=row["marker"]["usable_ids"],
                center_disagreement_mm=row["current_top_delta_mm"],
                candidate_count=len(row["candidates"]),
                counts=counts,
                nominal_candidates_with_static_witness=support,
                high_route=high["status"],
                dispatched_skills=receipt["commands"],
                physics_steps=receipt["physics_steps"],
                disposition="screened_out_before_motion",
            )
        )
    return dict(
        preregistration_sha256=sha(initial),
        capture_receipts_sha256=sha(CAPTURES),
        final_sweep_archive_sha256=sha(PACKAGE),
        slots=slots,
        registered_slots=len(slots),
        slots_dispatched=0,
        full_pick_place_completions=0,
        completion_rate_among_dispatched=None,
        formal_new_trials=0,
    )


if __name__ == "__main__":
    write(HERE / "development-dispatch.public.json", read_slots())
