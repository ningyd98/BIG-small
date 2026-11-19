from pathlib import Path

import pytest
from development_plan import make_assignments
from run_development import bill_totals, claim_presence, exclusive_owner, persist, registered_slots


def test_exclusive_owner_and_irrevocable_begin(tmp_path):
    fields = {
        name: tmp_path / name for name in ("begin", "end", "stdout", "stderr", "episode", "audit")
    }
    assert claim_presence(fields) == "NOT_EXECUTED"
    with exclusive_owner(tmp_path):
        with pytest.raises(BlockingIOError), exclusive_owner(tmp_path):
            pytest.fail("two actors acquired the batch owner")
        persist(fields["begin"], {"attempt": 1})
    with exclusive_owner(tmp_path):
        assert claim_presence(fields) == "STARTED_UNRESOLVED"
        with pytest.raises(FileExistsError):
            persist(fields["begin"], {"attempt": 2})
        persist(fields["end"], {"returncode": 2})
        assert claim_presence(fields) == "ENDED_UNVERIFIED"
        persist(fields["audit"], {"recognized_terminal": True})
        with pytest.raises(ValueError, match="audited slot is incomplete"):
            claim_presence(fields)


def test_requires_registered_poses_and_safe_directory_paths():
    independent, repeated = make_assignments()
    for slot in independent + repeated:
        slot["config"] = slot["assignment_id"] + ".json"
    allocation = {"development": independent, "repeats_1802": repeated}
    assert len(registered_slots(allocation)) == 22
    independent[0]["native_output"] = "../../../original-four-slot"
    with pytest.raises(ValueError, match="registered seed, pose, budget, order or output"):
        registered_slots(allocation)


def test_unknown_price_has_no_invented_currency_or_amount():
    expected = {
        "settled_reported_amount_by_currency": None,
        "cloud_entries_without_amount_and_currency_pair": 2,
    }
    assert (
        bill_totals(
            {
                "slot": {
                    "ledger": [
                        {"monetary_cost": None, "currency": None},
                        {"monetary_cost": "0.32", "currency": None},
                    ]
                },
            }
        )
        == expected
    )


def test_native_files_without_begin_are_not_a_new_slot(tmp_path: Path):
    episode = tmp_path / "episode"
    episode.mkdir()
    with pytest.raises(ValueError, match="native bytes without a BEGIN"):
        claim_presence({"begin": tmp_path / "begin", "episode": episode})
