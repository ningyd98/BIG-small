import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def test_frozen_first_generation_refusals_and_full_source_packages():
    assert importlib.util.find_spec("qualify_native"), "missing guarded qualification entry"
    import qualify_native as q

    result = q.frozen_inputs(Path(__file__).resolve().parent.parents[5])
    assert result["old_raw_frames"] == 42
    assert result["pre_clock_refusals"] == [8, 8]
    assert result["cold_read_failures"] == 2


def test_archived_evaluation_requires_authenticated_role_frame_time_and_deadline():
    assert importlib.util.find_spec("qualify_archive"), "missing original-time reader"
    from qualify_archive import checked_time

    now = datetime.now(UTC)
    packet = {"frame_id": "capture1", "checksum_sha256": "a" * 64, "captured_at": now.isoformat()}
    event = {
        **packet,
        "role": "color.initial",
        "lease_id": "lease1",
        "evaluated_at": (now + timedelta(milliseconds=20)).isoformat(),
        "call_start_utc": (now + timedelta(milliseconds=10)).isoformat(),
        "call_end_utc": (now + timedelta(milliseconds=26)).isoformat(),
    }
    limit = now + timedelta(seconds=1)
    assert (
        checked_time(packet, event, "color.initial", "lease1", limit).isoformat()
        == event["evaluated_at"]
    )
    for fault in (
        {"frame_id": "other"},
        {"checksum_sha256": "b" * 64},
        {"lease_id": "bad"},
        {"role": "other"},
        {"evaluated_at": None},
        {"evaluated_at": now.isoformat()},
        {"evaluated_at": now.replace(tzinfo=None).isoformat()},
        {"evaluated_at": (now + timedelta(seconds=5)).isoformat()},
    ):
        with pytest.raises(ValueError):
            checked_time(packet, {**event, **fault}, "color.initial", "lease1", limit)
