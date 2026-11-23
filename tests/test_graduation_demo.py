import json
import shutil
from pathlib import Path

import pytest
from scripts.graduation.demo import ROOT, SOURCES, matrix


def test_matrix_keeps_heldout_frames_and_official_groups_separate() -> None:
    counts = matrix(ROOT)["counts"]
    assert counts["held_out_groups"] == 3
    assert counts["held_out_observed"] == 159
    assert counts["held_out_frames"] == 162
    assert counts["held_out_conditional_p90_mm"] == pytest.approx(6.8686, abs=0.0001)
    assert counts["formal_registered"] == 9
    assert counts["formal_attempted"] == 1
    assert counts["formal_not_run"] == 8


def test_matrix_rejects_an_extra_formal_invocation(tmp_path: Path) -> None:
    for relative in SOURCES.values():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    teacher = tmp_path / SOURCES["teacher"]
    record = json.loads(teacher.read_text())
    record["formal_process"]["invocations"] += 1
    teacher.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="formal group identity"):
        matrix(tmp_path)
