"""Inventory immutable intake bytes and classify Git delivery without deleting data."""

from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
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


def main() -> None:
    original = json.loads((BASE / "initial-inventory.json").read_text())
    records = []
    for number, row in enumerate(original):
        path = ROOT / row["path"]
        assert not Path(row["path"]).is_absolute()
        assert ".." not in Path(row["path"]).parts
        assert "\n" not in row["path"] and "\r" not in row["path"]
        current = path.lstat()
        assert not stat.S_ISLNK(current.st_mode), row["path"]
        decision, reason = classify(row)
        credential = reason.startswith("credential material")
        if path.is_file():
            assert current.st_size == row["size"] and current.st_mtime_ns == row["mtime_ns"], row["path"]
        sha = digest(path) if path.is_file() and not credential else None
        records.append({**row, "decision": decision, "reason": reason, "sha256": sha,
                        "mode": "100755" if current.st_mode & stat.S_IXUSR else "100644"})
        if number and number % 5000 == 0:
            print(f"hashed {number} original intake entries", flush=True)
    counts = Counter(row["decision"] for row in records)
    sizes = Counter()
    for row in records:
        if row["sha256"] is not None:
            sizes[row["decision"]] += row["size"]
    raw = (json.dumps({"schema": "bigsmall.r383.intake-classification.v1", "records": records,
                       "scope": "original intake only; newly generated delivery receipts are audited separately",
                       "not_a_complete_raw_or_cloud_reproduction_package": True}, ensure_ascii=False, indent=2) + "\n").encode()
    target = BASE / "preflight/intake-classification.json.gz"
    target.write_bytes(gzip.compress(raw, mtime=0))
    assert gzip.decompress(target.read_bytes()) == raw
    for name in ("initial-inventory.json", "initial-status.porcelain-z"):
        source = BASE / name
        compressed = BASE / (name + ".gz")
        compressed.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
        assert gzip.decompress(compressed.read_bytes()) == source.read_bytes()
    selected = sorted(row["path"] for row in records if row["decision"] == "selected")
    (BASE / "preflight/selected-intake-paths.txt").write_text("\n".join(selected) + "\n")
    summary = {
        "schema": "bigsmall.r383.intake-classification-summary.v1",
        "original_intake_count": len(records), "counts": dict(counts), "bytes": dict(sizes),
        "all_intake_entries_accounted_for": len(records) == sum(counts.values()),
        "uncompressed_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_manifest_sha256": digest(target),
        "original_inventory_sha256": digest(BASE / "initial-inventory.json"),
        "original_status_sha256": digest(BASE / "initial-status.porcelain-z"),
        "original_files_deleted_or_rewritten": 0,
        "already_gitignored_data_not_recursively_inventoried": True,
        "nested_gitlink_contents_not_recursively_inventoried": True,
    }
    (BASE / "preflight/classification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with (BASE / "progress.md").open("a") as stream:
        stream.write("\n- Task 1 classification: complete; every initial intake path classified and fingerprinted where safe. All initial file sizes/mtimes stable; original inventory/status retained plus verified lossless gzip copies. No deletion or historical byte edits.\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
