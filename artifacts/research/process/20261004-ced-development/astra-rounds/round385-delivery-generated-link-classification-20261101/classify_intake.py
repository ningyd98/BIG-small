"""Inventory immutable intake bytes and classify Git delivery without deleting data."""

from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path
import stat


BASE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
GENERATED_PARTS = {
    "persistent-basetemp", "retained-cases", "retained-tree", "dist", "node_modules",
    "data", "fixture", "fixtures", "test-results", "playwright-report", "runtime",
    "pycache", "ruff-cache", "mypy-cache", "render", "candidate-render", "draft-render",
    "reference-original-render", "report-render", "source-render", "source-original-render",
    "report-conversion",
}
TEXT_SUFFIXES = {
    ".md", ".json", ".jsonl", ".txt", ".log", ".xml", ".py", ".diff", ".patch",
    ".csv", ".yaml", ".yml", ".sh", ".html", ".ndjson",
}
RAW_NAMES = {"records.jsonl", "observations.jsonl", "commands.jsonl", "trajectory.jsonl", "frames.jsonl"}
CREDENTIAL_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "credentials.toml"}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def classify(row: dict) -> tuple[str, str]:
    relative = Path(row["path"])
    parts = set(relative.parts)
    if relative.name in CREDENTIAL_NAMES or relative.suffix in {".pem", ".key", ".p12"}:
        return "local-only", "credential material; contents and values not inspected or published"
    if row["status"] != "??":
        if row["path"].startswith(("src/", "tests/")):
            return "selected", "existing source/test overlay; checkpoint verification required"
        return "local-only", "historical nested gitlink; parent pointer and internal dirty state preserved"
    if row["path"].startswith("tests/"):
        return "selected", "new scoped regression contract belonging to existing research plans"
    if parts & GENERATED_PARTS:
        return "local-only", "generated runtime/raw/fixture/source-copy/build output; original bytes retained"
    if relative.name in RAW_NAMES:
        return "local-only", "bulk runtime records; manifest does not replace original payload"
    if relative.suffix not in TEXT_SUFFIXES:
        return "local-only", "generated binary, cache, lock, or unpublished presentation build candidate"
    if row["size"] > 2_000_000:
        return "local-only", "non-required generated report exceeds existing 2 MB evidence boundary"
    if "/presentations/" in row["path"] and "evidence" not in parts:
        return "local-only", "regenerable presentation intermediate; authored final deck already tracked"
    return "selected", "bounded research plan/report/script/original failure log or provenance receipt"


ORIGINAL = BASE.with_name("round383-workspace-github-delivery-20261101")


def main() -> None:
    plan = json.loads((BASE / "plan.json").read_text())
    for pin in plan["inputs"]:
        assert digest(ROOT / pin["path"]) == pin["sha256"], pin["path"]
    audit = json.loads((BASE / "input-audit.json").read_text())
    allowed_links = {row["path"]: row for row in audit["symlinks"]}
    original = json.loads((ORIGINAL / "initial-inventory.json").read_text())
    assert len(original) == 21480 and len(allowed_links) == 600
    gitlink_paths = [row["path"] for row in original if stat.S_ISDIR((ROOT / row["path"]).lstat().st_mode)]
    index = subprocess.check_output(["git", "ls-files", "--stage", "-z", "--", *gitlink_paths])
    gitlinks = {}
    for item in index.split(b"\0"):
        if item:
            meta, name = item.decode().split("\t", 1)
            mode, oid, stage = meta.split()
            assert mode == "160000" and stage == "0"
            gitlinks[name] = oid
    assert len(gitlinks) == 2
    output = BASE / "preflight"
    output.mkdir()
    records = []
    checked_parents = set()
    kinds = Counter()
    byte_totals = Counter()
    for number, row in enumerate(original):
        relative = Path(row["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert "\n" not in row["path"] and "\r" not in row["path"]
        path = ROOT / relative
        for parent in path.parents:
            if parent in checked_parents:
                break
            assert not stat.S_ISLNK(parent.lstat().st_mode), str(parent)
            checked_parents.add(parent)
        current = path.lstat()
        decision, reason = classify(row)
        record = {**row, "decision": decision, "reason": reason, "sha256": None}
        if stat.S_ISLNK(current.st_mode):
            assert row["path"] in allowed_links and decision == "local-only" and row["status"] == "??"
            expected = allowed_links[row["path"]]
            target = os.readlink(path)
            assert target == expected["target"]
            assert current.st_size == row["size"] and current.st_mtime_ns == row["mtime_ns"]
            lexical_target = Path(os.path.normpath(os.path.join(str(path.parent), target)))
            assert lexical_target.is_relative_to(ROOT)
            raw_target = os.fsencode(target)
            assert path.lstat().st_mtime_ns == current.st_mtime_ns and os.readlink(path) == target
            record.update(node_type="symlink", mode="120000", link_target=target,
                          link_target_sha256=hashlib.sha256(raw_target).hexdigest(),
                          link_target_bytes=len(raw_target), payload_sha256=None,
                          target_node_present=os.path.lexists(lexical_target), target_payload_read=False)
            kinds["symlink"] += 1
            byte_totals["link_target_bytes"] += len(raw_target)
        elif stat.S_ISDIR(current.st_mode):
            assert row["path"] in gitlinks and decision == "local-only"
            record.update(node_type="gitlink", mode="160000", git_oid=gitlinks[row["path"]], payload_sha256=None)
            kinds["gitlink"] += 1
        else:
            assert stat.S_ISREG(current.st_mode)
            assert current.st_size == row["size"] and current.st_mtime_ns == row["mtime_ns"], row["path"]
            credential = reason.startswith("credential material")
            fingerprint = None if credential else digest(path)
            after = path.lstat()
            assert after.st_size == current.st_size and after.st_mtime_ns == current.st_mtime_ns
            record.update(node_type="regular", mode="100755" if current.st_mode & stat.S_IXUSR else "100644",
                          sha256=fingerprint, payload_sha256=fingerprint)
            kinds["regular"] += 1
            byte_totals[decision + "_regular_bytes"] += current.st_size
        records.append(record)
        if number and number % 5000 == 0:
            print(f"classified and fingerprinted {number} intake nodes", flush=True)
    assert dict(kinds) == {"gitlink": 2, "regular": 20878, "symlink": 600}
    assert len({row["path"] for row in records}) == len(original)
    assert {row["path"] for row in records} == {row["path"] for row in original}
    assert {row["path"] for row in records if row["node_type"] == "symlink"} == set(allowed_links)
    assert all(row["decision"] == "local-only" for row in records if row["node_type"] != "regular")
    counts = Counter(row["decision"] for row in records)
    assert counts.get("blocked", 0) == 0
    raw = (json.dumps({"schema": "bigsmall.r385.intake-classification.v1", "records": records,
                       "scope": "original R383 intake only; generated delivery receipts audited separately",
                       "not_a_complete_raw_or_cloud_reproduction_package": True}, ensure_ascii=False, indent=2) + "\n").encode()
    target = output / "intake-classification.json.gz"
    with target.open("xb") as stream:
        stream.write(gzip.compress(raw, mtime=0))
    assert gzip.decompress(target.read_bytes()) == raw
    copies = []
    for name in ("initial-inventory.json", "initial-status.porcelain-z"):
        source = ORIGINAL / name
        compressed = output / (name + ".gz")
        with compressed.open("xb") as stream:
            stream.write(gzip.compress(source.read_bytes(), mtime=0))
        assert gzip.decompress(compressed.read_bytes()) == source.read_bytes()
        copies.append({"original": str(source.relative_to(ROOT)), "original_sha256": digest(source),
                       "compressed": str(compressed.relative_to(ROOT)), "compressed_sha256": digest(compressed)})
    selected = sorted(row["path"] for row in records if row["decision"] == "selected")
    local = sorted(row["path"] for row in records if row["decision"] == "local-only")
    (output / "selected-intake-paths.txt").write_text("\n".join(selected) + "\n")
    local_raw = ("\n".join(local) + "\n").encode()
    (output / "local-only-intake-paths.txt.gz").write_bytes(gzip.compress(local_raw, mtime=0))
    assert gzip.decompress((output / "local-only-intake-paths.txt.gz").read_bytes()) == local_raw
    for pin in plan["inputs"]:
        assert digest(ROOT / pin["path"]) == pin["sha256"], pin["path"]
    source_audit = json.loads((ORIGINAL / "input-audit.json").read_text())
    for pin in source_audit["inputs"]:
        if pin["path"].startswith(("src/", "tests/")):
            assert digest(ROOT / pin["path"]) == pin["sha256"]
    summary = {"schema": "bigsmall.r385.intake-classification-summary.v1", "accepted": True,
        "original_intake_count": len(records), "node_types": dict(kinds), "counts": dict(counts),
        "bytes": dict(byte_totals), "blocked": 0, "selected_symlinks": 0,
        "all_initial_paths_accounted_for": True, "source_overlay_unchanged": True,
        "uncompressed_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_manifest_sha256": digest(target), "lossless_original_copies": copies,
        "original_files_deleted_or_rewritten": 0, "symlink_target_payloads_read": 0,
        "already_gitignored_data_not_recursively_inventoried": True,
        "nested_gitlink_contents_not_recursively_inventoried": True}
    (output / "classification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (BASE / "progress.md").write_text("# R385 ledger — plan: " + str(BASE / "plan.md") + "\n\n- Original classifier preserved; exact 600 generated symlinks fingerprinted without dereferencing or modifying them.\n- Task complete: 21480 nodes conserved; 20878 regular, 600 local-only symlink, 2 local-only gitlink; blocked=0 and selected symlink=0; original pins and source overlay stable.\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
