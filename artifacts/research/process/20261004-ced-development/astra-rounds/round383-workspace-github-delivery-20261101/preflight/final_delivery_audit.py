"""R383 exact-path final checkpoint audit; administrative only, no product imports."""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import re
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[7]
ROUNDS = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
R383 = ROUNDS / "round383-workspace-github-delivery-20261101"
R385 = ROUNDS / "round385-delivery-generated-link-classification-20261101"
R386 = ROUNDS / "round386-delivery-unicode-path-preflight-20261101"
R387 = ROUNDS / "round387-git-empty-object-recovery-20261102"
PRIVATE = ROOT / ".git/r383-github-delivery-20261102"


def git(*args, payload=None):
    result = subprocess.run(["git", *args], cwd=ROOT, input=payload, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"native Git failed: {args}; exit {result.returncode}; {result.stderr[:1000]!r}")
    return result.stdout


def put_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert ROOT == Path.cwd().resolve(), (ROOT, Path.cwd())
    PRIVATE.mkdir(exist_ok=False)
    assert json.loads((ROOT / R387 / "recovery-summary.json").read_text())["accepted"] is True
    assert git("rev-parse", "HEAD").decode().strip() == "28ac315c2af8567b377e6e2cc3ee5acb9cda4677"
    assert git("branch", "--show-current").decode().strip() == "research/20261004-continuation"
    selection = ROOT / R383 / "preflight/delivery-selected-paths.txt"
    previous = set(selection.read_text().splitlines())
    assert len(previous) == 1091
    untracked = {p for p in git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0") if p}
    for path in untracked:
        assert path.startswith((str(R383) + "/", str(R387) + "/")), path
    extra_manifest = str(R383 / "preflight/final-path-classification.json")
    selected = previous | untracked | {extra_manifest}
    put_json(ROOT / extra_manifest, {
        "schema": "bigsmall.r383.final-path-classification.v1",
        "previous_selected_count": len(previous),
        "final_selected_count": len(selected),
        "additional_paths": sorted(selected - previous),
        "decision": "selected administrative plans, review, native bounded outputs and recovery evidence",
        "large_native_traversal_local_only": str(R387 / "integrity/reachability.stdout.log"),
        "private_git_backups_excluded": True,
        "fingerprint_scope": "Exact payload hashes are in the private final index manifest; no recursive self-hash.",
    })
    selection.write_text("".join(path + "\n" for path in sorted(selected)), encoding="utf-8")
    original = json.loads(gzip.decompress((ROOT / R385 / "preflight/intake-classification.json.gz").read_bytes()))
    original_selected = [v for v in original["records"] if v["decision"] == "selected"]
    assert len(original_selected) == 941
    for record in original_selected:
        data = (ROOT / record["path"]).read_bytes()
        assert sha(data) == record["sha256"] and len(data) == record["size"], record["path"]
    patterns = {
        "private-key": rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        "github-token": rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        "openai-token": rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b",
        "aws-access-key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        "google-api-key": rb"\bAIza[A-Za-z0-9_-]{35}\b",
        "slack-token": rb"\bxox[baprs]-[A-Za-z0-9-]{16,}\b",
    }
    compiled = {kind: re.compile(pattern) for kind, pattern in patterns.items()}
    records = []
    scan_bytes = 0
    hits = []
    for path in sorted(selected):
        relative = PurePosixPath(path)
        assert not relative.is_absolute() and ".." not in relative.parts and ".git" not in relative.parts, path
        file = ROOT / path
        info = file.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_size < 100_000_000, path
        assert file.suffix.lower() not in {".sqlite", ".sqlite3", ".db", ".wal", ".shm", ".pt", ".pth", ".safetensors", ".onnx", ".pem", ".key"}, path
        data = file.read_bytes()
        assert not data.startswith(b"SQLite format 3\0"), path
        scanned = gzip.decompress(data) if file.suffix == ".gz" else data
        scan_bytes += len(scanned)
        for kind, pattern in compiled.items():
            if pattern.search(scanned):
                hits.append({"path": path, "kind": kind})
        records.append({"path": path, "bytes": len(data), "sha256": sha(data),
                        "mode": "100755" if info.st_mode & 0o111 else "100644"})
    assert not hits, hits
    path_bytes = b"".join(path.encode() + b"\0" for path in sorted(selected))
    ignore = subprocess.run(["git", "check-ignore", "--no-index", "--stdin", "-z"], cwd=ROOT, input=path_bytes, capture_output=True)
    assert ignore.returncode == 1 and not ignore.stdout and not ignore.stderr, "selected path ignored"
    for file in [ROOT / R383 / "preflight/final_delivery_audit.py", ROOT / R387 / "recover_git_objects.py"]:
        compile(file.read_bytes(), str(file), "exec")
    for path in selected - previous:
        if path.endswith(".json"):
            json.loads((ROOT / path).read_text())
    nul_manifest = PRIVATE / "selected-paths.nul"
    nul_manifest.write_bytes(path_bytes)
    staged = subprocess.run(["git", "--literal-pathspecs", "add", "--pathspec-from-file=" + str(nul_manifest), "--pathspec-file-nul"], cwd=ROOT, capture_output=True)
    (PRIVATE / "git-add.stdout.log").write_bytes(staged.stdout)
    (PRIVATE / "git-add.stderr.log").write_bytes(staged.stderr)
    assert staged.returncode == 0, "native staging failed; inspect private outputs"
    changed = {p for p in git("diff", "--cached", "--name-only", "-z").decode().split("\0") if p}
    assert changed == selected, (sorted(changed - selected), sorted(selected - changed))
    indexed = {}
    for entry in git("ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        header, path_raw = entry.split(b"\t", 1)
        path = path_raw.decode()
        if path in selected:
            mode, oid, stage = header.decode().split()
            assert stage == "0" and mode in {"100644", "100755"}, path
            indexed[path] = (mode, oid)
    assert set(indexed) == selected
    oids = sorted({oid for mode, oid in indexed.values()})
    response = git("cat-file", "--batch", payload="".join(oid + "\n" for oid in oids).encode())
    stream = io.BytesIO(response)
    blobs = {}
    for oid in oids:
        header = stream.readline().decode().rstrip("\n").split()
        assert len(header) == 3 and header[0] == oid and header[1] == "blob", header
        length = int(header[2])
        data = stream.read(length)
        assert len(data) == length and stream.read(1) == b"\n", oid
        blobs[oid] = (length, sha(data))
    assert not stream.read()
    for record in records:
        mode, oid = indexed[record["path"]]
        assert mode == record["mode"] and blobs[oid] == (record["bytes"], record["sha256"]), record["path"]
        record["blob_oid"] = oid
    put_json(PRIVATE / "index-byte-manifest.json", records)
    strict_paths = ["src", "tests", "docs"] + sorted(path for path in selected - previous if Path(path).suffix in {".md", ".json", ".py", ".txt"})
    strict = subprocess.run(["git", "diff", "--cached", "--check", "--", *strict_paths], cwd=ROOT, capture_output=True)
    (PRIVATE / "strict-diff-check.stdout.log").write_bytes(strict.stdout)
    (PRIVATE / "strict-diff-check.stderr.log").write_bytes(strict.stderr)
    assert strict.returncode == 0, "new authored file whitespace failure"
    full = subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, capture_output=True)
    (PRIVATE / "full-diff-check.stdout.log").write_bytes(full.stdout)
    (PRIVATE / "full-diff-check.stderr.log").write_bytes(full.stderr)
    warning_records = json.loads((ROOT / R387 / "whitespace-audit.json").read_text())["warning_paths"]
    allowed = {record["path"] for record in warning_records}
    allowed.add(str(R387 / "full-diff-check.stdout.log"))
    for record in warning_records:
        assert sha((ROOT / record["path"]).read_bytes()) == record["sha256"], record["path"]
    warnings = set()
    for line in full.stdout.decode().splitlines():
        match = re.match(r"^(.+):[0-9]+: (?:trailing whitespace|new blank line at EOF|space before tab in indent)\.", line)
        if match:
            warnings.add(match.group(1))
    assert full.returncode in {0, 2} and not full.stderr and warnings == allowed, sorted(warnings - allowed)
    empty = [str(path.relative_to(ROOT)) for directory in (ROOT / ".git/objects").iterdir()
             if directory.is_dir() and re.fullmatch(r"[0-9a-f]{2}", directory.name)
             for path in directory.iterdir() if path.is_file() and path.stat().st_size == 0]
    assert not empty, empty
    result = {
        "accepted": True,
        "selected_paths": len(selected),
        "selected_bytes": sum(record["bytes"] for record in records),
        "original_intake_selected_hashes_verified": len(original_selected),
        "unique_staged_blobs": len(blobs),
        "all_selected_index_bytes_and_modes_match": True,
        "pattern_scanned_decompressed_bytes": scan_bytes,
        "credential_pattern_hits": hits,
        "strict_authored_diff_check_exit": strict.returncode,
        "full_frozen_evidence_diff_check_exit": full.returncode,
        "frozen_whitespace_warning_paths": sorted(warnings),
        "selected_path_set_sha256": sha(path_bytes),
        "index_byte_manifest_sha256": sha((PRIVATE / "index-byte-manifest.json").read_bytes()),
        "index_sha256": sha((ROOT / ".git/index").read_bytes()),
        "index_tree": git("write-tree").decode().strip(),
        "zero_loose_object_files": 0,
        "scope": "R383 checkpoint, 67 bounded CPU tests; no full research/hardware/cloud reproduction acceptance",
    }
    put_json(PRIVATE / "final-precommit-audit.json", result)
    print(json.dumps({key: result[key] for key in ["accepted", "selected_paths", "selected_bytes", "unique_staged_blobs", "index_tree", "zero_loose_object_files"]}))


if __name__ == "__main__":
    main()
