from pathlib import Path
import hashlib
import json

INDEX = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round134-p6-red-interface-connection-recovery-20261011/implementation/recovery3-freeze/source-index.json")
OUTPUT = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round152-p6-review-recovery-index-schema-20261012/review/batch-19-schema.json")
data = INDEX.read_bytes()
assert len(data) == 111415
assert hashlib.sha256(data).hexdigest() == "f74193993185e323d2b688638517f599d7871352093e90f8c69bbf07d61edc36"
index = json.loads(data)
assert type(index) is dict
assert set(index) == {"status", "files", "sources", "actual_case_regular_files", "actual_symlinks", "root_ledger_note"}
assert type(index["actual_case_regular_files"]) is int
assert index["actual_case_regular_files"] == 181
assert type(index["files"]) is list and len(index["files"]) == 197
assert type(index["sources"]) is list and len(index["sources"]) == 6
assert type(index["actual_symlinks"]) is list and len(index["actual_symlinks"]) == 2
files = index["files"]
snapshot_only = []
seen = set()
for record in files:
    assert type(record) is dict
    assert set(record) in ({"source", "snapshot", "bytes", "sha256"}, {"snapshot", "bytes", "sha256"})
    assert type(record["snapshot"]) is str and Path(record["snapshot"]).is_absolute()
    assert record["snapshot"] not in seen
    seen.add(record["snapshot"])
    assert type(record["bytes"]) is int and record["bytes"] >= 0
    assert type(record["sha256"]) is str and len(record["sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in record["sha256"])
    if "source" in record:
        assert type(record["source"]) is str and Path(record["source"]).is_absolute()
    else:
        snapshot_only.append(record)
assert snapshot_only == [{"snapshot": "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round134-p6-red-interface-connection-recovery-20261011/implementation/recovery3-freeze/step-report.json", "bytes": 21247, "sha256": "e1d99926ef9b4b217b04c6c84d2d5d10f6d85aeb8dfc4659b862f5a9b0cb7380"}]
assert all(record in files and "source" in record for record in index["sources"])
case_records = [record for record in files if record.get("source", "").startswith("/tmp/bigsmall-p6-r134-recovery3/")]
assert len(case_records) == index["actual_case_regular_files"]
for record in index["actual_symlinks"]:
    assert type(record) is dict and set(record) == {"source", "relative_path", "target", "kind"}
    assert all(type(record[k]) is str and record[k] for k in record)
    assert Path(record["source"]).is_absolute() and Path(record["target"]).is_absolute()
    assert not Path(record["relative_path"]).is_absolute()
    assert record["kind"] == "actual symlink metadata; regular target bytes preserved by complete case-tree"
result = {
    "status": "TYPED_SCHEMA_ONLY_NOT_FILE_HASH_OR_RECOVERY_ACCEPTANCE",
    "batch": 19, "cumulative_used": 19, "remaining": 5, "total": 24,
    "index": {"path": str(INDEX), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    "count_field": {"actual_case_regular_files": 181},
    "files": files, "sources": index["sources"], "case_records": case_records,
    "snapshot_only": snapshot_only, "symlink_metadata": index["actual_symlinks"],
    "source_drift_rule": "Historical R134 snapshot pins are not current production pins.",
    "snapshot_hashes_verified": False, "product_commands": 0, "acceptance": False,
}
encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with OUTPUT.open("xb") as stream:
    stream.write(encoded)
print(json.dumps({"status": result["status"], "path": str(OUTPUT), "bytes": len(encoded),
                  "sha256": hashlib.sha256(encoded).hexdigest(), "files": 197,
                  "case_regular": 181, "source_records": 6, "snapshot_only": 1,
                  "symlinks": 2, "remaining": 5}, ensure_ascii=False))

