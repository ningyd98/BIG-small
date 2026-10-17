"""Local R83-authorized preparer; not a published executable or commit tool."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess

MAIN = Path.cwd()
W = Path("/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall")
B = Path("artifacts/research/process/20261004-ced-development")
R = B / "astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round76-lifecycle-evidence"
O = B / "t12-sol-handoff-20261007/delivery-rw1"
BASE = "4d40a65059ab75292fa1842bacf62653829808e6"
USER_COMMIT = "34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e"
BRANCH = "codex/research-20261007-p1-delivery"
OWNED = ["src/cloud_edge_robot_arm/research/protocol_generation.py", "tests/test_protocol_generation_sources.py"]


def pin(p):
    raw = Path(p).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def save(name, value):
    with (O / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def git(argv):
    result = subprocess.run(["git", *argv], cwd=W, capture_output=True)
    return result


checks = []
for dirname in [
    "round77-git-delivery-boundary-20261007",
    "round81-git-verbatim-evidence-20261007",
    "round83-git-policy-prerequisite-20261007",
]:
    plan = json.loads((B / "astra-rounds" / dirname / "plan.json").read_text())
    entries = plan["input_pins"]
    if isinstance(entries, dict):
        entries = [{"path": p, **v} for p, v in entries.items()]
    for entry in entries:
        assert pin(entry["path"]) == {k: entry[k] for k in ("sha256", "bytes")}
    checks.append({"plan": dirname, "verified_pins": len(entries)})
assert git(["rev-parse", "HEAD"]).stdout.decode().strip() == BASE
assert git(["status", "--porcelain=v1", "-z", "--untracked-files=all"]).stdout == b""
assert git(["symbolic-ref", "-q", "HEAD"]).returncode == 1
assert git(["show-ref", "--verify", "--quiet", "refs/heads/" + BRANCH]).returncode == 1
remote = git(["ls-remote", "--heads", "origin", "refs/heads/" + BRANCH, "refs/heads/research/20261004-continuation"])
assert remote.returncode == 0
assert remote.stdout.decode().splitlines() == [BASE + "\trefs/heads/research/20261004-continuation"]
save("resume-preconditions-r83.json", {
    "checks": checks, "head": BASE, "detached_clean": True,
    "remote_query": {"argv": remote.args, "exit": remote.returncode, "stdout": remote.stdout.decode(), "stderr": remote.stderr.decode()},
    "original_failure_retained": pin(O / "preparation-failure-1.json"),
})
policy = {"sha256": "8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649", "bytes": 1774}
assert not (W / "AGENTS.md").exists()
assert pin("AGENTS.md") == policy
user_policy = git(["show", USER_COMMIT + ":AGENTS.md"])
assert user_policy.returncode == 0 and user_policy.stdout == Path("AGENTS.md").read_bytes()

pool = (R / "delivery-paths.txt").read_text().splitlines()
assert len(pool) == 63 and sum(Path(p).stat().st_size for p in pool) == 1285123
selected = {}
excluded = []
for path in pool:
    if path == str(R / "command-runner.py"):
        excluded.append({
            "path": path, **pin(path), "semantic_role": "CURRENT_EXECUTABLE_IF_REUSED",
            "reason": "Historical executable not needed for imported source/tests; no bound current quality proof. Not reused, executed or published as a tool; original pin/reference remains.",
        })
        continue
    if path in OWNED:
        role, reason = "CURRENT_EXECUTABLE", "Complete final RW1 file, scoped independent PASS and bound39/27/static verification."
    elif "/source-before/" in path or "/source-after/" in path:
        role, reason = "VERBATIM_EVIDENCE", "Frozen source audit specimen; never imported or executed as current implementation."
    elif Path(path).name in ["step-report.md", "step-report.json", "progress.md", "delivery-paths.txt", "local-evidence-paths.txt"]:
        role, reason = "NEW_PROSE_OR_METADATA", "Scoped narrative/delivery/local-only metadata; strict subset."
    else:
        role, reason = "VERBATIM_EVIDENCE", "Immutable R76 raw command/result/stdout/JUnit/diff or frozen audit receipt/manifest with source pin; no edits or execution."
    selected[path] = (role, reason, "R76 explicit63 pool")

for row in json.loads((R / "input-check.json").read_text()):
    path = row["path"]
    if path.startswith("/tmp/"):
        excluded.append({"path": path, **pin(path), "semantic_role": "LOCAL_ONLY_ORIGINAL", "reason": "Historical raw remains local; no full raw publication."})
        continue
    if path in ["AGENTS.md", "pyproject.toml"] or path in selected:
        continue
    if "/source-after/" in path:
        role, reason = "VERBATIM_EVIDENCE", "Prior R71 frozen source establishes before provenance; not current executable."
    elif Path(path).name in ["plan.md", "plan.json", "step-report.md", "step-report.json", "final-review.md", "final-review.json"]:
        role, reason = "NEW_PROSE_OR_METADATA", "Necessary historical RW1 plan/review narrative and original REQUEST_CHANGES."
    else:
        role, reason = "VERBATIM_EVIDENCE", "Finite pinned historical result, original platform/interface or AST/source receipt."
    selected[path] = (role, reason, "R76 finite35 pinned input")

extra = [
    ("round76-rw1-lifecycle-evidence-20261007", ["plan.md", "plan.json", "root-authorization.json"]),
    ("round78-rw1-preflight-schema-20261007", ["plan.md", "plan.json", "failure-receipt.json", "step-report.md", "recovery.command-result.json", "recovery.stdout.txt", "recovery.stderr.txt", "implementation/input-check.json"]),
    ("round77-git-delivery-boundary-20261007", ["plan.md", "plan.json", "root-authorization.json", "input-pins.json", "readonly-evidence.json"]),
    ("round81-git-verbatim-evidence-20261007", ["plan.md", "plan.json", "root-authorization.json", "input-pins.json", "original-observation.json"]),
    ("round83-git-policy-prerequisite-20261007", ["plan.md", "plan.json", "root-authorization.json", "input-pins.json", "readonly-observation.json"]),
]
for dirname, names in extra:
    for name in names:
        path = str(B / "astra-rounds" / dirname / name)
        assert Path(path).is_file()
        role = "NEW_PROSE_OR_METADATA" if Path(name).name in ["plan.md", "plan.json", "root-authorization.json", "step-report.md"] else "VERBATIM_EVIDENCE"
        selected[path] = (role, "Required exact authorization/repair/delivery/whitespace provenance. R78 effective approval is R76 root-authorization, not an invented separate receipt.", "Explicit necessary addition")
for name in ["rw1-independent-review/round76-final-review.md", "rw1-independent-review/round76-final-review.json", "rw1-root-check-round76.json", "rw1-root-acceptance-round76.json"]:
    path = str(B / "t12-sol-handoff-20261007" / name)
    selected[path] = ("NEW_PROSE_OR_METADATA", "Final independent scoped PASS and ROOT source/JUnit/acceptance snapshot; no active phase totals.", "ROOT frozen signing evidence")
selected["AGENTS.md"] = ("NEW_PROSE_OR_METADATA", "User research policy and R77/R81 execution basis; exact sole R83 policy addition.", "user commit " + USER_COMMIT + " / AGENTS.md")

queue = list(OWNED)
seen = set()
external = set()
missing = []
while queue:
    path = queue.pop(0)
    if path in seen:
        continue
    seen.add(path)
    tree = ast.parse(Path(path).read_text())
    if path.startswith("src/"):
        for parent in Path(path).parents:
            if str(parent) == "src":
                break
            init = parent / "__init__.py"
            if init.is_file():
                queue.append(str(init))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.level == 0 else []
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            continue
        for module in modules:
            if not module:
                continue
            if not module.startswith("cloud_edge_robot_arm"):
                external.add(module.split(".")[0])
                continue
            path_module = Path("src") / Path(*module.split("."))
            found = next((str(p) for p in [path_module.with_suffix(".py"), path_module / "__init__.py"] if p.is_file()), None)
            if found:
                queue.append(found)
            else:
                missing.append({"module": module, "from": path})
producer = ast.parse(Path(OWNED[0]).read_text())
declaration = next(node for node in producer.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SOURCE_PATHS" for t in node.targets))
seen.update(ast.literal_eval(declaration.value))
seen.update(["configs/research/recovery_faults.yaml", "AGENTS.md", "pyproject.toml"])
closure = []
for path in sorted(seen):
    assert Path(path).is_file()
    current = pin(path)
    base_pin = pin(W / path) if (W / path).is_file() else None
    equal = current == base_pin
    if path == "AGENTS.md":
        assert base_pin is None and current == policy and user_policy.stdout == Path(path).read_bytes()
        action = "EXACT_R83_ADDED_POLICY_NOT_RUNTIME_DEPENDENCY"
    else:
        assert equal or path in OWNED
        action = "DEPENDENCY_ALREADY_IN_BASE" if equal else "IMPORT_COMPLETE_FINAL_FILE"
    closure.append({"path": path, "source_pin": current, "base_pin": base_pin, "base_bytes_equal": equal, "action": action})
assert not missing
save("closure.json", {
    "status": "STATIC_CLOSURE_CONFIRMED_R83_POLICY_EXCEPTION_ONLY",
    "dependencies": closure, "external_modules": sorted(external), "changed_source_files": OWNED,
    "other_dependency_preconditions_relaxed": False,
    "platform_evidence": {"path": str(R.parent / "platform-evidence/report.json"), **pin(R.parent / "platform-evidence/report.json"), "added_hardcoded_small_source": True, "claim": "Original immutable local capability only; current environment/assets/lease/RW2 wiring/actual gates are separately unverified."},
    "selected66_test_dependency": "Synthetic CPU fixture with native/network/real-clock sentinels; no big raw/historical runtimeDB.",
    "not_real_runtime_readiness": True,
})

patterns = {
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github_token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b",
    "openai_key": rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b",
    "aws_access_key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "credential_url": rb"https?://[^\s/:]+:[^\s/@]+@",
}
entries, reviews = [], []
for path, (role, reason, source_version) in sorted(selected.items()):
    source = Path(path)
    assert not source.is_absolute() and ".." not in source.parts and source.is_file()
    assert not any(p.is_symlink() for p in [source, *source.parents])
    assert not any(part in path for part in ["local-cpu-originals/", "physics/workspace", "runtime.db", ".venv/"])
    raw = source.read_bytes()
    hits = [kind for kind, regex in patterns.items() if re.search(regex, raw)]
    if hits:
        save("sensitive-content-stop.json", {"path": path, "categories": hits, "secret_values_printed": False})
        raise SystemExit(3)
    text = raw.decode("utf-8")
    if source.suffix == ".json":
        json.loads(text)
    if role == "CURRENT_EXECUTABLE":
        ast.parse(text)
    info = pin(source)
    mode = "100755" if source.stat().st_mode & 0o111 else "100644"
    base_raw = (W / path).read_bytes() if (W / path).is_file() else None
    entries.append({"path": path, "source": str((MAIN / path).resolve()), "frozenSha256": info["sha256"], "bytes": info["bytes"], "mode": mode, "reason": reason, "semantic_role": role, "source_version": source_version, "relative_to_base_changed": base_raw != raw, "change": "M" if base_raw is not None else "A"})
    reviews.append({"path": path, "semantic_role": role, "utf8_checked": True, "json_parsed": source.suffix == ".json", "credential_pattern_hits": [], "publication": "REVIEWED_SAME_PUBLIC_PROJECT_SCOPE", "context": "Existing workspace paths/CPU machine labels/public project or source code identifiers; no credential material/changed audience identified. Finite content review, not a repository-wide claim."})
manifest = {
    "status": "FROZEN_CANDIDATE_PAYLOAD", "base": BASE, "branch": BRANCH, "source_user_commit": USER_COMMIT,
    "pool_count": 63, "pool_bytes": 1285123, "entries": entries, "excluded": excluded,
    "path_count": len(entries), "bytes": sum(e["bytes"] for e in entries),
    "metadata_policy": "Payload excludes its own manifest and new delivery metadata. Published metadata is separate; final local receipt pins metadata and final staged tree without self-reference.",
    "unpublished_references": "Original receipts retain honest references to omitted /tmp/full raw/local-only copies/older broader receipts/historical orchestration. References do not assert remote availability.",
}
save("candidate-paths.json", manifest)
(O / "candidate-paths.nul").open("xb").write(b"\0".join(e["path"].encode() for e in entries) + b"\0")
save("content-review.json", {"status": "PASS_SCOPED_CANDIDATE_CONTENT", "files": reviews, "limitations": "Candidate-only credential/endpoint/personal-context review; no original edits and no all-repository secret-free claim."})
result = git(["switch", "-c", BRANCH])
save("branch-create.json", {"argv": result.args, "cwd": str(W), "exit_code": result.returncode, "stdout": result.stdout.decode(), "stderr": result.stderr.decode()})
assert result.returncode == 0
for entry in entries:
    target = W / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = Path(entry["source"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["frozenSha256"]
    target.write_bytes(raw)
    target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
    assert pin(target) == {"sha256": entry["frozenSha256"], "bytes": entry["bytes"]}
save("payload-import.json", {"status": "IMPORTED_EXACT_BYTES_AND_MODES", "paths": len(entries), "bytes": manifest["bytes"], "branch_created": True, "staged": False, "commit_push": 0, "main_source_writes": 0})
print(json.dumps({"payload_paths": len(entries), "bytes": manifest["bytes"], "excluded": len(excluded), "dependencies": len(closure), "branch_created": True, "stage_commit_push": 0}))
