"""R345 POST_RUN_ARTIFACT_RETENTION: inert bytes/metadata only; no DB engine."""

from pathlib import Path
import hashlib
import json
import os
import stat
import time


BASE = Path(__file__).absolute().parent
PLAN_SHA = "2c515f891efaff394c93f1d73c94ce4e96783dfb482eb3db2362602998e71b08"
ACTIVATION_SHA = "0092e8350b124f15307c28c41a4b31c29445f2e32ce62879ab31348460d76bab"
KIND = "POST_RUN_ARTIFACT_RETENTION"
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).absolute()), "bytes": len(data), "sha256": digest(data)}


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def open_root(path):
    """Open every absolute ancestor without following a symbolic link."""
    assert path.is_absolute() and ".." not in path.parts, "exact absolute root"
    descriptors = [os.open("/", DIR_FLAGS)]
    relations = []
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=descriptors[-1])
            relations.append((descriptors[-1], part, child))
            descriptors.append(child)
        return descriptors, relations
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def verify_relations(relations):
    for parent, name, child in relations:
        actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
        assert identity(actual) == identity(os.fstat(child)), "source ancestor identity changed"
        assert stat.S_ISDIR(actual.st_mode), "source ancestor no longer directory"


def parent_descriptor(root_fd, relative, *, create=False):
    assert not relative.is_absolute() and relative.parts and ".." not in relative.parts, "safe relative path"
    descriptors = []
    relations = []
    current = root_fd
    try:
        for part in relative.parts[:-1]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
            child = os.open(part, DIR_FLAGS, dir_fd=current)
            descriptors.append(child)
            relations.append((current, part, child))
            current = child
        return current, descriptors, relations
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def stable_file(root_fd, relative, expected, *, destination_fd=None):
    parent, directories, relations = parent_descriptor(root_fd, relative)
    source_fd = None
    output_fd = None
    output_directories = []
    try:
        initial = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
        assert stat.S_ISREG(initial.st_mode), "source must remain a regular file"
        assert initial.st_size == expected["bytes"], "inventoried source size changed"
        source_fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        opened = os.fstat(source_fd)
        assert identity(initial) == identity(opened), "source identity changed before read"
        if destination_fd is not None:
            output_parent, output_directories, _ = parent_descriptor(destination_fd, relative, create=True)
            output_fd = os.open(relative.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=output_parent)
        value = hashlib.sha256()
        size = 0
        while chunk := os.read(source_fd, 1024 * 1024):
            value.update(chunk)
            size += len(chunk)
            if output_fd is not None:
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(output_fd, remaining)
                    assert written > 0, "destination write made no progress"
                    remaining = remaining[written:]
        if output_fd is not None:
            os.fsync(output_fd)
        assert size == expected["bytes"] and value.hexdigest() == expected["sha256"], "inventoried bytes changed"
        assert identity(opened) == identity(os.fstat(source_fd)), "source changed while reading"
        assert identity(opened) == identity(os.stat(relative.name, dir_fd=parent, follow_symlinks=False)), "source path changed"
        verify_relations(relations)
        return {"bytes": size, "sha256": value.hexdigest(), "identity": list(identity(opened))}
    finally:
        if output_fd is not None:
            os.close(output_fd)
        if source_fd is not None:
            os.close(source_fd)
        for descriptor in reversed(output_directories):
            os.close(descriptor)
        for descriptor in reversed(directories):
            os.close(descriptor)


def census(root_fd, prefix=Path()):
    result = {}
    with os.scandir(root_fd) as entries:
        for entry in entries:
            relative = prefix / entry.name
            value = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(value.st_mode):
                child = os.open(entry.name, DIR_FLAGS, dir_fd=root_fd)
                try:
                    result.update(census(child, relative))
                finally:
                    os.close(child)
            elif stat.S_ISREG(value.st_mode):
                result[relative.as_posix()] = {"type": "regular", "bytes": value.st_size}
            elif stat.S_ISLNK(value.st_mode):
                result[relative.as_posix()] = {"type": "symlink", "target": os.readlink(entry.name, dir_fd=root_fd)}
            else:
                result[relative.as_posix()] = {"type": "other", "mode": value.st_mode}
    return result


def write_json(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, allow_nan=False, indent=2)
        output.write("\n")


plan_data = (BASE / "plan.json").read_bytes()
assert digest(plan_data) == PLAN_SHA, "actual R345 plan pin"
assert pin(BASE / "root-activation.json")["sha256"] == ACTIVATION_SHA, "ROOT artifact-only activation pin"
plan = json.loads(plan_data)
for row in plan["inputs"]:
    assert pin(row["path"])["bytes"] == row["bytes"], "input size: " + row["path"]
    assert pin(row["path"])["sha256"] == row["sha256"], "input hash: " + row["path"]
run = Path(plan["scope"]["original_run_root"])
inventory = json.loads(Path(plan["original_evidence"]["inventory"]["path"]).read_bytes())
regular = [row for row in inventory["files"] if row["type"] == "regular"]
links = [row for row in inventory["files"] if row["type"] == "symlink"]
assert len(regular) == 220 and sum(row["bytes"] for row in regular) == 59542786, "fixed regular inventory"
assert len(links) == 3, "fixed link inventory"
available = os.statvfs(BASE)
free_bytes = available.f_bavail * available.f_frsize
assert free_bytes >= 59542786 + 8 * 1024 * 1024, "retained bytes plus metadata storage"
recovery = BASE / "recovery"
recovery.mkdir(mode=0o700, exist_ok=False)
retained = recovery / "retained-tree"
retained.mkdir(mode=0o700)
source_descriptors, source_relations = open_root(run)
destination_descriptors, destination_relations = open_root(retained.absolute())
source_fd, destination_fd = source_descriptors[-1], destination_descriptors[-1]
copied, errors, originals_after, database_observations = [], [], [], []
manifest = {"kind": KIND, "original_capture_complete": False, "consistent_database_backup": False,
            "script": pin(__file__), "plan_sha256": PLAN_SHA, "ROOT_activation_sha256": ACTIVATION_SHA,
            "source_root": str(run), "destination_root": str(retained), "free_bytes_before": free_bytes,
            "copied_files": copied, "errors": errors, "symlinks_not_followed_or_recreated": links}
try:
    expected_set = {str(Path(row["path"]).relative_to(run)): {"type": row["type"],
                    **({"bytes": row["bytes"]} if row["type"] == "regular" else {"target": row["target"]})}
                    for row in inventory["files"]}
    before_set = census(source_fd)
    assert before_set == expected_set, "original file/link set differs from inventory"
    for row in regular:
        source = Path(row["path"])
        relative = source.relative_to(run)
        assert run / relative == source, "source outside exact original root"
        before = stable_file(source_fd, relative, row)
        copied_source = stable_file(source_fd, relative, row, destination_fd=destination_fd)
        destination = stable_file(destination_fd, relative, row)
        assert before["identity"] == copied_source["identity"], "source identity changed across stable reads"
        copied.append({"source": str(source), "destination": str(retained / relative),
                       "relative_path": str(relative), "bytes": destination["bytes"],
                       "sha256": destination["sha256"], "source_identity": copied_source["identity"],
                       "destination_readback_verified": True})
    for row in regular:
        relative = Path(row["path"]).relative_to(run)
        actual = stable_file(source_fd, relative, row)
        original = next(item for item in copied if item["relative_path"] == str(relative))
        assert actual["identity"] == original["source_identity"], "original identity changed after all copying"
        originals_after.append({"path": row["path"], "bytes": actual["bytes"], "sha256": actual["sha256"], "unchanged": True})
    after_set = census(source_fd)
    assert after_set == before_set, "original file/link set changed after copying"
    verify_relations(source_relations)
    verify_relations(destination_relations)
    assert all(not (retained / Path(row["path"]).relative_to(run)).exists() for row in links), "symlinks must not be recreated"
    for row in regular:
        if not row["path"].endswith(".db"):
            continue
        item = {"database_path": row["path"], "kind": KIND, "no_database_engine_open": True, "sidecars": {}}
        for suffix in ("-wal", "-shm", "-journal"):
            relative = Path(row["path"] + suffix).relative_to(run)
            parent, descriptors, _ = parent_descriptor(source_fd, relative)
            try:
                try:
                    observed = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    observation = {"present_now": False}
                else:
                    observation = {"present_now": True, "regular_now": stat.S_ISREG(observed.st_mode), "bytes_now": observed.st_size}
                item["sidecars"][suffix] = observation
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)
        database_observations.append(item)
    assert len(database_observations) == 10, "ten inventoried database paths"
except BaseException as error:
    errors.append({"type": type(error).__name__, "message": str(error), "partial_outputs_preserved": True})
finally:
    for descriptor in reversed(destination_descriptors):
        os.close(descriptor)
    for descriptor in reversed(source_descriptors):
        os.close(descriptor)

sidecars = []
for source in plan["original_evidence"]["completed_sidecars"]:
    retained_path = retained / Path(source["pin"]["path"]).relative_to(run)
    if retained_path.is_file():
        payload = json.loads(retained_path.read_bytes())
        observations = payload["observations"]
        sidecars.append({"nodeid": payload["nodeid"], "source": source["pin"],
                         "retained": pin(retained_path), "entered_behavior": payload["entered_behavior"],
                         "assertions_completed": observations["assertions_completed"],
                         "exit_exception": observations["exit_exception"], "cleanup_errors": payload["cleanup_errors"]})
expected_nodes = json.loads(next(Path(row["path"]).read_bytes() for row in plan["inputs"] if row["path"].endswith("round331-p6-t3-continuation-20261024/plan.json")))["commands"]["t3_green"]["nodes"]
completed_nodes = {row["nodeid"] for row in sidecars}
missingness = {"kind": KIND, "expected_nodes": expected_nodes, "expected_count": 9,
               "completed_resource_sidecars": sidecars, "completed_sidecar_count": len(sidecars),
               "nodes_without_completed_sidecar": [node for node in expected_nodes if node not in completed_nodes],
               "fifth_case_directory": {"path": str(run / "persistent-basetemp/test_b_terminal_publication_co0"), "present_at_later_observation": (run / "persistent-basetemp/test_b_terminal_publication_co0").is_dir(), "completion": "UNKNOWN"},
               "JUnit_present_now": (run / "junit.xml").exists(), "runner_source_after_present_now": (run / "source-after.json").exists(),
               "original_capture_complete": False, "missing_case_results_reconstructed": False,
               "limit": "Directory presence or later source-pin observations cannot establish completion. No nine-node completion, consistent DB backup or runtime pass."}
manifest.update({"status": "ALL_220_EXISTING_REGULAR_FILES_RETAINED" if len(copied) == 220 and not errors else "PARTIAL_RETENTION_ERRORS_PRESERVED",
                 "copied_count": len(copied), "copied_bytes": sum(row["bytes"] for row in copied),
                 "originals_after": originals_after, "originals_unchanged": len(originals_after) == 220 and not errors,
                 "observed_at_ns": time.time_ns(), "database_sidecar_observations": database_observations,
                 "absence_limit": "Sidecar absence now does not prove absence during execution; no SQLite engine was opened."})
resources = {"kind": KIND, "completed_resource_sidecar_count": len(sidecars), "expected_count": 9,
             "completed_sidecars": sidecars, "database_sidecar_observations": database_observations,
             "original_cleanup_evidence": json.loads((retained / "result.json").read_bytes()).get("cleanup"),
             "limit": "Later byte/JSON observations only, not complete original resource aggregation or a runtime qualification."}
write_json(recovery / "recovery-manifest.json", manifest)
write_json(recovery / "missingness.json", missingness)
write_json(recovery / "resource-observation.json", resources)
for row in plan["inputs"]:
    actual = pin(row["path"])
    assert actual["bytes"] == row["bytes"] and actual["sha256"] == row["sha256"], "original plan input changed after retention"
print(json.dumps({"kind": KIND, "status": manifest["status"], "copied_count": len(copied),
                  "copied_bytes": manifest["copied_bytes"], "errors": errors,
                  "completed_sidecars": len(sidecars), "expected_nodes": 9,
                  "manifests": [pin(recovery / name) for name in ("recovery-manifest.json", "missingness.json", "resource-observation.json")]}, indent=2))
if errors:
    raise SystemExit(1)
