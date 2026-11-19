import hashlib

import pytest
import resume_v2 as v2


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"id": True}, {"id": 1}),
        ({"z": 1}, {"z": 2}),
        ({"rows": [1, 2]}, {"rows": [2, 1]}),
        ({"rows": []}, {}),
    ],
)
def test_actual_checkpoint_refuses_other_fields_numbers_types_or_order(tmp_path, before, after):
    path = tmp_path / "receipt.json"
    path.write_bytes(v2.canonical(before))
    with pytest.raises(ValueError, match="checkpoint bytes differ"):
        v2.compare_checkpoint(path, after)


def test_exact_bytes_accept_arrays_and_reject_serialized_format_changes(tmp_path):
    path = tmp_path / "receipt.json"
    expected = v2.canonical({"physical": {"safety": []}})
    path.write_bytes(expected)
    assert v2.compare_checkpoint(path, {"physical": {"safety": ()}}) == (
        hashlib.sha256(expected).hexdigest()
    )
    path.write_bytes(expected.rstrip() + b" \n")
    with pytest.raises(ValueError, match="checkpoint bytes differ"):
        v2.compare_checkpoint(path, {"physical": {"safety": ()}})
    path.write_bytes(b'{"physical":0,"physical":1}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        v2.compare_checkpoint(path, {"physical": 1})


def test_supplement_checkpoint_is_append_only_and_keeps_v1_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(v2.original, "OWNER", tmp_path)
    (tmp_path / "verification").mkdir()
    fresh = {"supplemental_reader_sha256": v2.V1_SHA, "physical": {"events": ()}}
    first = v2.supplemental_checkpoint("development-18", fresh, save=True)
    assert v2.supplemental_checkpoint("development-18", fresh) == first
    with pytest.raises(ValueError, match="v1 reader SHA"):
        v2.supplemental_checkpoint(
            "development-18",
            fresh | {"supplemental_reader_sha256": "1" * 64},
            save=True,
        )
    with pytest.raises(ValueError, match="checkpoint bytes differ"):
        v2.supplemental_checkpoint("development-18", fresh | {"physical": None}, save=True)


def test_existing_begin_without_end_and_second_owner_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(v2.original, "OWNER", tmp_path)
    (tmp_path / "receipts").mkdir()
    slot = {"assignment_id": "development-18", "native_output": "native/development-18"}
    root = v2.original.slot_paths(tmp_path, slot)
    v2.original.persist(root["begin"], {"attempt": 1})
    with v2.original.exclusive_owner(tmp_path):
        with pytest.raises(BlockingIOError), v2.original.exclusive_owner(tmp_path):
            pytest.fail("second owner acquired lock")
        with pytest.raises(ValueError, match="lacks complete END"):
            v2.fresh_assessment({}, slot)
