from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from scripts.graduation import proposal_gate_binding as binding


def example_roles():
    base = datetime(2026, 11, 24, tzinfo=UTC)
    return [
        {
            "label": name,
            "acquired_for_this_role": index == 0,
            "captured_at": base.isoformat(),
            "checked_at": (base + timedelta(milliseconds=50 * (index + 1))).isoformat(),
            "frame_id": "f",
            "checksum_sha256": "h",
            "episode_id": "e",
            "physics_step": 120,
            "sim_time_s": 0.5,
        }
        for index, name in enumerate(binding.ROLE_NAMES)
    ]


def test_role_window_uses_last_same_source_pre_dispatch_check():
    roles = example_roles()
    last = dict(roles[-1], checked_at="2026-11-24T00:00:01+00:00")
    assert binding.clock_window(roles + [last])["dispatch_recheck"] == last["checked_at"]


@pytest.mark.parametrize("change", ["step", "episode", "hash", "order", "future", "fresh"])
def test_role_window_rejects_clock_or_source_substitution(change):
    roles = example_roles()
    field, value = {
        "step": ("physics_step", 121),
        "episode": ("episode_id", "wrong"),
        "hash": ("checksum_sha256", "wrong"),
        "order": ("label", binding.ROLE_NAMES[3]),
        "future": ("checked_at", "2026-11-23T23:59:00+00:00"),
        "fresh": ("acquired_for_this_role", True),
    }[change]
    roles[-1][field] = value
    with pytest.raises(ValueError):
        binding.clock_window(roles)


def test_tracker_accepts_only_one_freshness_region_in_the_whole_interval():
    cap = datetime(2026, 11, 24, tzinfo=UTC)
    binding.fresh_track_interval(cap, cap, cap + timedelta(seconds=5))
    with pytest.raises(ValueError):
        binding.fresh_track_interval(cap, cap, cap + timedelta(seconds=5, microseconds=1))


def test_reject_external_oracle_and_empty_preparation_sources():
    valid = {"source": binding.FACTS_SOURCE, "facts": {"target_visible": {"value": True}}}
    binding.validate_facts_envelope(valid)
    for substitute in (
        dict(valid, oracle_label="VALID"),
        dict(valid, facts={}),
        dict(valid, source="GROUNDING_PREPARATION"),
    ):
        with pytest.raises(ValueError):
            binding.validate_facts_envelope(substitute)


def test_pairing_uses_only_the_recorded_same_opportunity():
    events = [{"id": "a", "frame_id": "1"}, {"id": "b", "frame_id": "2"}]
    binding.require_event_identity(events[0], deepcopy(events[0]))
    with pytest.raises(ValueError):
        binding.require_event_identity(events[0], events[1])
    with pytest.raises(ValueError):
        binding.require_event_identity(events[0], dict(events[0], oracle_label="INVALID"))
