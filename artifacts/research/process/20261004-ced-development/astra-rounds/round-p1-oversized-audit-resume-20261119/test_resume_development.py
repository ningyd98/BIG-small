import hashlib
from pathlib import Path

import pytest
import resume_development as resume
from resume_development import original


@pytest.mark.parametrize(
    ("row", "error"),
    [
        ({"name": "result.json", "size": 21}, "result size outside"),
        ({"name": "result.json", "size": 1000}, "manifested file length"),
        ({"name": "result.json", "sha": "a" * 64}, "large result bytes differ"),
        ({"name": "../escape.json"}, "unsafe evidence path"),
    ],
)
def test_bounded_index_refuses_bad_size_sha_and_path(tmp_path, monkeypatch, row, error):
    monkeypatch.setattr(resume, "REGISTERED_LIMIT", 32)
    actual = b" " * 200
    (tmp_path / "result.json").write_bytes(actual)
    entry = {
        "path": row["name"],
        "bytes": row.get("size", len(actual)),
        "sha256": row.get("sha", hashlib.sha256(actual).hexdigest()),
    }
    if row.get("size") == 21:
        (tmp_path / "result.json").write_bytes(b" " * 21)
    original.persist(
        tmp_path / "evidence-manifest.json",
        {
            "schema_version": "local.files.v1",
            "files": [entry],
        },
    )
    with pytest.raises(ValueError, match=error):
        resume.bounded_index(tmp_path, None)


def test_known_receipts_are_not_interchangeable_or_generic(monkeypatch, tmp_path):
    freeze = original.freeze_at(resume.FREEZE_SHA)
    slot = original.registered_slots(freeze["allocation"])[10]
    original_paths = original.slot_paths(original.OWNER, slot)
    original_wrapper = original.read(original_paths["stdout"])
    config = resume.load_config(original.OWNER / "configs" / slot["config"])
    source = resume.verify_checkout(Path(freeze["source"]), config)
    (tmp_path / "receipts").mkdir()
    paths = original.slot_paths(tmp_path, slot)

    def copy_receipts(*, claimed, source_revision, code):
        output = original_wrapper | {"output": str(paths["episode"]), "episode_exit_code": code}
        output["source"] = output["source"] | {"git_revision": source_revision}
        original.persist(paths["stdout"], output)
        paths["stderr"].write_bytes(b"")
        binding = original.bound_slot(claimed, resume.FREEZE_SHA)
        original.persist(paths["begin"], binding)
        original.persist(
            paths["end"],
            binding
            | {
                "returncode": 2,
                "begin_sha256": original.sha(paths["begin"]),
                "stdout_sha256": original.sha(paths["stdout"]),
                "stderr_sha256": original.sha(paths["stderr"]),
            },
        )
        original.persist(
            paths["audit"].with_suffix(".unresolved.json"),
            {
                "status": "STARTED_UNRESOLVED",
                "error_type": "ValueError",
                "message": resume.LIMIT_ERROR,
                "original_end_sha256": original.sha(paths["end"]),
            },
        )

    cases = (
        (slot | {"runtime_seed": 3}, freeze["commit"], 0, "assigned identity differs"),
        (slot, "a" * 40, 0, "configuration differs"),
        (slot, freeze["commit"], 2, "exact known 2/2/0 signature"),
    )
    for claimed, revision, code, error in cases:
        copy_receipts(claimed=claimed, source_revision=revision, code=code)
        with pytest.raises(ValueError, match=error):
            resume.owned_wrapper(freeze, slot, paths, source, config)
        for flag in ("begin", "end", "stdout", "stderr"):
            paths[flag].unlink()
        paths["audit"].with_suffix(".unresolved.json").unlink()

    copy_receipts(claimed=slot, source_revision=freeze["commit"], code=0)
    assert resume.owned_wrapper(freeze, slot, paths, source, config)["native_exit"] == 0


def test_retained_begin_with_no_end_cannot_be_dispatched(tmp_path, monkeypatch):
    freeze = original.freeze_at(resume.FREEZE_SHA)
    slot = original.registered_slots(freeze["allocation"])[10]
    monkeypatch.setattr(original, "OWNER", tmp_path)
    (tmp_path / "receipts").mkdir()
    paths = original.slot_paths(tmp_path, slot)
    original.persist(paths["begin"], original.bound_slot(slot, resume.FREEZE_SHA))
    with original.exclusive_owner(tmp_path):
        with pytest.raises(BlockingIOError), original.exclusive_owner(tmp_path):
            pytest.fail("second caller received same owner")
        with pytest.raises(ValueError, match="BEGIN without independent terminal evidence"):
            resume.prior_assessment(freeze, slot)


def test_resume_requires_old_prefix_and_cannot_skip_an_unresolved_slot():
    expected = ["AUDITED"] * 10 + ["ENDED_UNVERIFIED"] + ["NOT_EXECUTED"] * 11
    resume.expected_started_prefix(expected)
    expected[2] = "NOT_EXECUTED"
    with pytest.raises(ValueError, match="required prior receipts"):
        resume.expected_started_prefix(expected)
    expected[2] = "AUDITED"
    expected[19] = "AUDITED"
    with pytest.raises(ValueError, match="do not form a prefix"):
        resume.expected_started_prefix(expected)
