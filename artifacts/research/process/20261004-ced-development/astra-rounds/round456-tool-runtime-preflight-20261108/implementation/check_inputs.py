"""One stdlib-only preflight; restore evidence from immutable pre-edit inputs."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
PRIOR = ROUND.parent / "round454-reset-conversion-completeness-20261108"


def load(path):
    return json.loads(path.read_text())


def fingerprint(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    pins = load(ROUND / "intake/input-pins.json")
    for row in pins:
        current = (ROOT / row["path"]).read_bytes()
        assert fingerprint(current) == {k: row[k] for k in ("bytes", "sha256")}, row["path"]
        assert (ROUND / row["copy"]).read_bytes() == current, row["path"]
    test = "tests/test_native_observer_failures.py"
    approved = next(row for row in pins if row["path"] == test)
    checks, originals = [], {}
    for row in load(PRIOR / "intake/input-pins.json"):
        original = (PRIOR / row["copy"]).read_bytes()
        expected = {k: row[k] for k in ("bytes", "sha256")}
        assert fingerprint(original) == expected, row["path"]
        current = fingerprint((ROOT / row["path"]).read_bytes())
        unchanged = current == expected
        if row["path"] == test:
            assert current == {k: approved[k] for k in ("bytes", "sha256")}
            assert not unchanged
        else:
            assert unchanged, row["path"]
        originals[row["path"]] = original
        checks.append(dict(path=row["path"], original=expected, current=current,
                           unchanged=unchanged, approved_delta=not unchanged))
    assert len(checks) == 24 and sum(row["unchanged"] for row in checks) == 23
    before = []
    for name in load(PRIOR / "plan.json")["allowed_product_paths"]:
        destination = PRIOR / "implementation/before" / name
        raw = originals[name]
        if destination.exists():
            assert destination.read_bytes() == raw, name
            action = "VERIFIED_EXISTING"
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(raw)
            action = "COPIED_FROZEN_ORIGINAL"
        before.append(dict(path=str(destination.relative_to(ROOT)), action=action,
                           source="R454 immutable pre-edit input copy", **fingerprint(raw)))
    report = dict(status="PASS", runtime=str(ROOT / ".venv/bin/python"),
                  round456_pins=len(pins), checks=checks, unchanged=23, approved_test_delta=1,
                  before=before, before_provenance="Evidence reconstructed after shell preflight failure from previously frozen pre-edit originals; working test never overwritten",
                  acquisition_success_disposition="COMPLETE", tests=0, actual_runs=0)
    save(ROUND / "implementation/preflight-result.json", report)
    save(PRIOR / "implementation/applicability-after-addendum.json", report)
    save(ROUND / "implementation/step-report.json", dict(
        status="COMPLETED", original_failure="intake/received-root-report.json (received report, not original stdout file)",
        recovery="implementation/preflight-result.json", product_edits=0, tests=0, actual_runs=0,
        next="Original R454 conversion-red may execute once under its unchanged plan"))
    print("PASS: 8 R456 pins, 23 unchanged R454 pins, 1 exact approved test delta; frozen before evidence restored")


if __name__ == "__main__":
    main()
