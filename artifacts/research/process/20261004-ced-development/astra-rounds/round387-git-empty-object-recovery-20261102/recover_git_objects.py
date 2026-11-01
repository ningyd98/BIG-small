"""Apply the exact R387 recovery plan; preserve every original empty node privately."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import zlib


ROOT = Path.cwd().resolve()
BASE = Path(__file__).resolve().parent
GIT = Path(subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], text=True).strip())


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def reference_bytes() -> dict[str, bytes]:
    result = {}
    paths = [GIT / "HEAD", GIT / "packed-refs"]
    for directory in (GIT / "refs", GIT / "logs"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*") if path.is_file())
    for path in paths:
        if path.exists():
            assert not path.is_symlink(), path
            result[str(path.relative_to(GIT))] = path.read_bytes()
    return result


def loose_files() -> dict[str, os.stat_result]:
    result = {}
    for folder in (GIT / "objects").iterdir():
        if folder.is_dir() and len(folder.name) == 2:
            assert not folder.is_symlink(), folder
            for path in folder.iterdir():
                assert not path.is_symlink(), path
                if path.is_file():
                    result[str(path.relative_to(GIT))] = path.lstat()
    return result


def blob_oid(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def native(name: str, argv: list[str]) -> dict:
    directory = BASE / "integrity"
    directory.mkdir(exist_ok=True)
    started = time.monotonic()
    print("starting " + name, flush=True)
    with (directory / (name + ".stdout.log")).open("xb") as out, (directory / (name + ".stderr.log")).open("xb") as err:
        result = subprocess.run(argv, stdout=out, stderr=err, check=False)
    receipt = {"argv": argv, "returncode": result.returncode,
               "elapsed_s": time.monotonic() - started,
               "ended_utc": datetime.now(timezone.utc).isoformat()}
    save(directory / (name + ".result.json"), receipt)
    print(name + " exit " + str(result.returncode), flush=True)
    assert result.returncode == 0, "R387 integrity failure; retain native output and request the next Astra plan"
    return receipt


def main() -> None:
    plan = json.loads((BASE / "plan.json").read_text())
    audit = json.loads((BASE / "input-audit.json").read_text())
    for row in plan["inputs"]:
        path = Path(row["path"])
        path = path if path.is_absolute() else ROOT / path
        assert sha(path.read_bytes()) == row["sha256"], row["path"]
    assert not (GIT / "index.lock").exists()
    index_before = (GIT / "index").read_bytes()
    assert sha(index_before) == plan["index_before"]["sha256"]
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == plan["head"]
    assert subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() == plan["branch"]
    refs_before = reference_bytes()
    all_before = loose_files()
    expected = {str(Path(row["path"]).relative_to(GIT)): row for row in audit["empty_loose_objects"]}
    assert {name for name, info in all_before.items() if info.st_size == 0} == set(expected)
    valid_before = {name: (info.st_ino, info.st_size, info.st_mtime_ns) for name, info in all_before.items() if info.st_size}
    for name, row in expected.items():
        info = all_before[name]
        assert stat.S_ISREG(info.st_mode) and info.st_size == 0
        assert info.st_ino == row["inode"] and info.st_mtime_ns == row["mtime_ns"]
    payloads = {}
    for row in plan["recovery_payloads"]:
        path = ROOT / row["path"]
        assert path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
        assert blob_oid(raw) == row["git_blob_oid"]
        payloads[row["git_blob_oid"]] = raw
    assert len(payloads) == 59
    selected_file = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/preflight/delivery-selected-paths.txt"
    staged_paths = {name.decode() for name in subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"]).split(b"\0") if name}
    assert staged_paths == set(selected_file.read_text().splitlines()) and len(staged_paths) == 1091
    worktree_before = {name: sha((ROOT / name).read_bytes()) for name in staged_paths}
    private = GIT / "r387-empty-object-recovery-20261102"
    private.mkdir(mode=0o700)
    (private / "backup").mkdir()
    (private / "backup/index").write_bytes(index_before)
    assert (private / "backup/index").read_bytes() == index_before
    for name, raw in refs_before.items():
        target = private / "backup/references" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for name, raw in payloads.items():
        target = private / "payloads" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        assert sha(target.read_bytes()) == sha(raw)
    node_receipts = []
    for name, row in expected.items():
        source = GIT / name
        target = private / "backup" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        assert target.read_bytes() == b""
        info = source.lstat()
        node_receipts.append({"relative_git_path": name, "source_stat": {
            "dev": info.st_dev, "inode": info.st_ino, "mode": info.st_mode,
            "uid": info.st_uid, "gid": info.st_gid, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}, "empty_sha256": sha(b"")})
    save(private / "backup-manifest.json", {"nodes": node_receipts, "index_sha256": sha(index_before)})
    assert len(node_receipts) == 110 and (GIT / "index").read_bytes() == index_before
    journal = private / "actions.jsonl"
    with journal.open("x") as stream:
        for name, row in expected.items():
            source = GIT / name
            info = source.lstat()
            assert stat.S_ISREG(info.st_mode) and not source.is_symlink() and info.st_size == 0
            assert info.st_ino == row["inode"] and info.st_mtime_ns == row["mtime_ns"]
            assert (private / "backup" / name).read_bytes() == b""
            target = private / "quarantine" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            assert not target.exists()
            source.rename(target)
            assert target.lstat().st_ino == info.st_ino and target.read_bytes() == b""
            stream.write(json.dumps({"action": "quarantine", "path": name, "inode_preserved": True}) + "\n")
            stream.flush()
        for oid, raw in payloads.items():
            location = GIT / "objects" / oid[:2] / oid[2:]
            assert not location.exists()
            result = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=raw, capture_output=True, check=False)
            stream.write(json.dumps({"action": "reconstruct", "oid": oid, "exit": result.returncode,
                                    "stdout": result.stdout.decode(errors="replace"),
                                    "stderr": result.stderr.decode(errors="replace")}) + "\n")
            stream.flush()
            assert result.returncode == 0 and result.stdout.decode().strip() == oid
            assert subprocess.check_output(["git", "cat-file", "-t", oid], text=True).strip() == "blob"
            restored = subprocess.check_output(["git", "cat-file", "blob", oid])
            assert restored == raw and blob_oid(restored) == oid
            assert zlib.decompress(location.read_bytes()) == b"blob " + str(len(raw)).encode() + b"\0" + raw
    save(BASE / "restoration-receipt.json", {"quarantined_nodes": 110, "reconstructed_blobs": 59,
         "unreachable_named_objects_preserved_only": 50, "temporary_empty_node_preserved_only": 1,
         "private_backup": str(private), "index_unchanged_after_restoration": (GIT / "index").read_bytes() == index_before})
    results = [native("reachability", ["git", "rev-list", "--objects", "--all", "--reflog", "--missing=print"]),
               native("connectivity", ["git", "fsck", "--connectivity-only", "--no-progress"]),
               native("full-fsck", ["git", "fsck", "--full", "--no-progress"])]
    assert not any(info.st_size == 0 for info in loose_files().values())
    assert (GIT / "index").read_bytes() == index_before and reference_bytes() == refs_before
    after = loose_files()
    assert all(name in after and (after[name].st_ino, after[name].st_size, after[name].st_mtime_ns) == old for name, old in valid_before.items())
    assert all(sha((ROOT / name).read_bytes()) == fingerprint for name, fingerprint in worktree_before.items())
    entries = []
    for item in subprocess.check_output(["git", "ls-files", "--stage", "-z"]).split(b"\0"):
        if item:
            meta, name = item.decode().split("\t", 1)
            mode, oid, stage = meta.split()
            assert stage == "0"
            if mode != "160000":
                entries.append((oid, name, mode))
    checked = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        input="\n".join(item[0] for item in entries) + "\n", text=True, capture_output=True, check=True)
    rows = checked.stdout.splitlines()
    assert len(rows) == len(entries) and all(len(row.split()) == 3 and row.split()[1] == "blob" for row in rows)
    oid_by_path = {name: oid for oid, name, mode in entries}
    for name in staged_paths:
        assert subprocess.check_output(["git", "cat-file", "blob", oid_by_path[name]]) == (ROOT / name).read_bytes(), name
    r386 = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round386-delivery-unicode-path-preflight-20261101"
    for row in json.loads((r386 / "verification/temporal_cpu/source-before.json").read_text()):
        assert sha(Path(row["path"]).read_bytes()) == row["sha256"], row["path"]
    assert all((private / "backup" / name).read_bytes() == b"" and (private / "quarantine" / name).read_bytes() == b"" for name in expected)
    save(BASE / "recovery-summary.json", {"schema": "bigsmall.r387.recovery-summary.v1", "accepted": True,
        "quarantined_nodes": 110, "restored_blobs": 59, "restored_index_paths": 65,
        "preserved_unreachable_empty_oids": 50, "preserved_empty_temp_files": 1,
        "zero_loose_files_remaining": 0, "all_index_blob_entries_readable": len(entries),
        "staged_paths_checked_byte_for_byte": len(staged_paths), "index_sha256_unchanged": sha(index_before),
        "head_refs_reflogs_unchanged": True, "existing_valid_loose_object_metadata_unchanged": True,
        "source_and_67_pass_evidence_unchanged": True, "integrity_commands": results,
        "empty_object_creation_cause": "UNKNOWN", "backup_metadata_private_not_for_git_delivery": str(private)})
    print("R387 recovery and full integrity accepted", flush=True)


if __name__ == "__main__":
    main()
