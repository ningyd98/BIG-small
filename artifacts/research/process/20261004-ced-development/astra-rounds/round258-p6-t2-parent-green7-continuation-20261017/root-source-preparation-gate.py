"""ROOT-only R258 preparation gate. Bytes/JSON only; no product execution."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import time

R = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = R / "artifacts/research/process/20261004-ced-development/astra-rounds/round258-p6-t2-parent-green7-continuation-20261017"
START = time.monotonic()
CHECKS = []
CACHE = {}
RESOLUTIONS = []
ARCHIVES = []

def check(name, ok, detail=None):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    if time.monotonic() - START > 115:
        raise TimeoutError("ROOT metadata gate exceeded internal115s")

def identity(p):
    return (p["path"], p["bytes"], p["sha256"])

def read_regular(path):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("not own regular file: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read()
        after = os.fstat(fd)
    finally:
        os.close(fd)
    end = path.lstat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not all(signature(s) == signature(before) for s in (opened, after, end)):
        raise ValueError("unstable file: " + str(path))
    return raw, end.st_mode

def raw_pin(raw, path):
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def direct(p, name):
    raw, mode = read_regular(p["path"])
    check(name, raw_pin(raw, p["path"]) == {k: p[k] for k in ("path", "bytes", "sha256")}, p)
    if "mode" in p:
        check(name + ":mode", mode == p["mode"])
    CACHE[str(p["path"])] = raw
    return raw

def parsed_pin(p, name):
    return json.loads(direct(p, name))

def absent(path, name):
    p = Path(path)
    check(name, not p.exists() and not p.is_symlink(), str(p))

def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return raw_pin(raw, path)

def archive_before(p, label):
    raw = direct(p, label + ":current")
    target = D / "before/root-source-preparation" / label
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    record = {"original": {k:p[k] for k in ("path","bytes","sha256")},
              "physical": raw_pin(raw, target), "base64": base64.b64encode(raw).decode()}
    ARCHIVES.append(record)

PLAN_PIN = {"path": str(D/"plan.json"), "bytes":152521, "sha256":"50970ee4e58d28f7732686ff11befd01f1d56a3657a200d97dba9b45ffa764e7"}
MD_PIN = {"path": str(D/"plan.md"), "bytes":5979, "sha256":"7f465c8fda7e01be9b69791ce53f6d5084a8a4f42491fc302f8496fa6ec2824f"}
OBS_PIN = {"path": str(D/"input-observation.json"), "bytes":996699, "sha256":"8213421ccb98f9bdc8370d909cda26a7366cc44c9f4fe12a9d463c5f5e2899d9"}
P = parsed_pin(PLAN_PIN, "frozen_plan")
direct(MD_PIN, "frozen_md")
O = parsed_pin(OBS_PIN, "frozen_observation")
check("manifest_count", len(O["inputs"]) == 388)
check("planning_all692", O["check_count"] == 692 and len(O["checks"]) == 692 and all(x["ok"] is True for x in O["checks"]))
MAPS = {}
for i, row in enumerate(O["existing_exact_maps47"]):
    original, archive = row["original"], row["archive"]
    raw = direct(archive, "exact_map47:" + str(i))
    check("archive_original_identity:" + str(i), (len(raw), hashlib.sha256(raw).hexdigest()) == (original["bytes"], original["sha256"]))
    MAPS[identity(original)] = {"physical":archive, "raw":raw}
check("maps_count", len(O["existing_exact_maps47"]) == 47)
for i, row in enumerate(O["R251_exact_invocation_generations"]):
    container = parsed_pin(row["container"], "generation_container:" + str(i))
    selected = container
    for token in row["pointer"].lstrip("/").split("/"):
        selected = selected[int(token)] if isinstance(selected, list) else selected[token]
    raw = base64.b64decode(selected, validate=True)
    original = row["original"]
    check("generation22_full_bytes:" + str(i), (len(raw), hashlib.sha256(raw).hexdigest()) == (original["bytes"], original["sha256"]))
    MAPS[identity(original)] = {"container":row["container"], "pointer":row["pointer"], "raw":raw}
check("generation_count", len(O["R251_exact_invocation_generations"]) == 22)
for i, pin in enumerate(O["inputs"]):
    key = identity(pin)
    if key in MAPS:
        row = MAPS[key]
        check("manifest_exact_generation:" + str(i), (len(row["raw"]),hashlib.sha256(row["raw"]).hexdigest()) == (pin["bytes"],pin["sha256"]))
        RESOLUTIONS.append({"original":pin, "via":{k:v for k,v in row.items() if k != "raw"}})
    else:
        direct(pin, "manifest_current:" + str(i))
source_index = parsed_pin(O["accepted_history_authority"]["source_index"], "accepted_source_index")
check("accepted_history_finite", len(source_index["history_observations"]) == 1689 and len(source_index["explicit_maps"]) == 47 and len(source_index["input_records"]) == 48)
check("sources27", len(O["current_sources27"]) == len(source_index["sources"]) == 27)
for i, (current, frozen) in enumerate(zip(O["current_sources27"], source_index["sources"], strict=True)):
    raw = direct(current, "current_source:" + str(i))
    archived = direct(current["physical"], "source_physical:" + str(i))
    encoded = base64.b64decode(frozen["base64"], validate=True)
    check("source_full_equality:" + str(i), raw == archived == encoded and all(current[k] == frozen[k] for k in ("path","bytes","sha256","mode")))
check("protected211", len(O["protected211"]) == 211 and O["protected211"] == source_index["protected"])
for i, pin in enumerate(O["protected211"]):
    direct(pin, "protected:" + str(i))
for i, row in enumerate(O["R251_final_controls"]):
    direct(row["after"], "fixed_R251_control:" + str(i))
check("R251_controls7", len(O["R251_final_controls"]) == 7 and all(x["full_exact_transition"] is True for x in O["R251_final_controls"]))
def resolve_missing_authority(row, container):
    # container bytes have already matched row["authority"]["pin"].
    authority = row["authority"]
    if type(authority) is not dict or set(authority) != {"pin", "selector", "ordinal"}:
        raise ValueError("exact missing-authority record required")
    selector = authority["selector"]
    ordinal = authority["ordinal"]
    if type(container) is not dict or type(ordinal) is not int:
        raise ValueError("dictionary container and integer ordinal required")
    if selector == "input_records":
        records = container["input_records"]
    elif selector == "new_retained_databases.pin":
        records = container["new_retained_databases"]
    else:
        raise ValueError("unapproved missing-authority selector")
    if type(records) is not list or not 0 <= ordinal < len(records):
        raise ValueError("bounded exact authority ordinal required")
    selected = records[ordinal]
    if type(selected) is not dict:
        raise ValueError("authority row must be a dictionary")
    if selector == "new_retained_databases.pin":
        selected = selected["pin"]
    if type(selected) is not dict:
        raise ValueError("selected pin must be a dictionary")
    required = ("path", "bytes", "sha256")
    actual = {key: selected[key] for key in required}
    expected = {key: row["original"][key] for key in required}
    if (type(actual["path"]) is not str or type(actual["bytes"]) is not int
            or actual["bytes"] < 0 or type(actual["sha256"]) is not str
            or len(actual["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in actual["sha256"])
            or actual != expected):
        raise ValueError("exact original missing identity differs")
    return actual

D260 = D.parent / "round260-p6-t2-root-missing-selector-schema-20261017"
R260_PIN = {"path":str(D260/"plan.json"),"bytes":11318,"sha256":"06eb02068cdc1360e46be6a52cee24b725e5edde9bf29345aaa47093abd21042"}
P260 = parsed_pin(R260_PIN, "R260_plan")
direct({"path":str(D260/"plan.md"),"bytes":2196,"sha256":"bd0ffbf8998b7bd8ad4d5e9b83a5cbaf7b6e2d48b6e58374b1b1f9557cdb2d55"}, "R260_md")
direct(P260["observation"], "R260_observation")
for i, pin in enumerate(P260["inputs"]):
    direct(pin, "R260_input:" + str(i))
MISSING_PROOFS = []
CONTAINERS = {}
for row in P260["actual_schema"]["container_pins"]:
    container = parsed_pin(row["pin"], "missing_container")
    check("authority_schema", type(container) is dict and type(container[row["selected_key"]]) is list and len(container[row["selected_key"]]) == row["selected_list_count"])
    CONTAINERS[identity(row["pin"])] = container
selector_counts = {"input_records":0,"new_retained_databases.pin":0}
check("missing_count35", len(O["missing_registry35"]) == 35)
for i,row in enumerate(O["missing_registry35"]):
    original = resolve_missing_authority(row, CONTAINERS[identity(row["authority"]["pin"])])
    absent(original["path"], "missing_original:" + str(i))
    check("missing_null_boundary:" + str(i), row["disposition"] == "HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245" and row["current_exists"] is False and row["current_is_symlink"] is False and all(row[k] is None for k in ("current_bytes","current_sha256","hash_match")))
    selector_counts[row["authority"]["selector"]] += 1
    MISSING_PROOFS.append({"original":original,"authority":row["authority"],"identity_matches":True,"current_exists":False,"current_bytes":None,"current_sha256":None,"hash_match":None})
check("exact_selector_counts29_6", selector_counts == {"input_records":29,"new_retained_databases.pin":6})

for i, row in enumerate(O["old_absent_sidecars90"]):
    absent(row["path"], "old_sidecar:" + str(i))
    check("old_sidecar_record:" + str(i), row["exists"] is False and row["is_symlink"] is False)
check("old_sidecar_count90", len(O["old_absent_sidecars90"]) == 90)
for group, count in (("R242_R248",12),("R251",18)):
    rows = O["retained_workspace_databases"][group]
    check("retained_count:" + group, len(rows) == count)
    for i,row in enumerate(rows):
        direct(row["pin"], "retained_DB:" + group + ":" + str(i))
        check("DB_sidecars3:" + group + ":" + str(i), len(row["sidecars"]) == 3)
        for sidecar in row["sidecars"]:
            absent(sidecar["path"], "retained_sidecar:" + group + ":" + str(i))
            check("retained_sidecar_record", sidecar["exists"] is False and sidecar["is_symlink"] is False and sidecar["pin"] is None)
check("inventory72", len(O["writer_inventory"]["entries"]) == 72)
direct(O["writer_inventory"]["pin"], "writer_inventory_pin")
for name,row in P["inputs"]["parent_role_timepoint"].items():
    role = parsed_pin(row["pin"], "parent_role:" + name)
    check("original_red:" + name, all(role["commands"]["t2_red"][k] == row["t2_red"][k] for k in ("state","used","remaining")))
    check("original_green_unused:" + name, all(role["commands"]["t2_green"][k] == row["t2_green"][k] for k in ("state","used","remaining")))
    check("no_continuation_yet:" + name, "R258" not in role["commands"]["t2_green"].get("continuation",{}))
    archive_before(row["pin"], name)
for name,pin in P["inputs"]["mutable_current_context"].items():
    archive_before(pin, name)
for path in P["scope"]["new_author_files"]:
    absent(path, "new_author_file_absent")
for path in P["command"]["output_paths"].values():
    absent(path, "runtime_output_absent")
check("all_checks_before_release", all(x["ok"] for x in CHECKS))
report = {"schema_version":"bigsmall.r258.root-input-check.v1", "status":"SOURCE_PREPARATION_ONLY" if all(x["ok"] for x in CHECKS) else "STOP",
          "plan":PLAN_PIN, "observation":OBS_PIN, "checks":CHECKS, "check_count":len(CHECKS),
          "all_checks_true":all(x["ok"] for x in CHECKS), "exact_resolutions":RESOLUTIONS,
          "full_before":ARCHIVES, "R260_disposition":R260_PIN, "missing35":MISSING_PROOFS, "runtime_released":False, "runtime_executed":False, "original_t2_green_remaining":1,
          "history_limit":"accepted1689 finite source authority; exact47 archives and22 invocation generations checked; no recursive audit or unavailable bytes recovery"}
receipt = save_new(D/"input-check.json", report)
if not report["all_checks_true"]:
    summary = json.dumps({"status":"STOP","report":receipt,"failed":[x for x in CHECKS if not x["ok"]]},ensure_ascii=False)
    print(summary.encode()[:5500].decode("utf-8", errors="ignore"))
    raise SystemExit(1)
activation = {"round":"R258","status":"SOURCE_PREPARATION_ONLY","plan":PLAN_PIN,"input_check":receipt,
              "author":"/root/p6_stage_b_sol","runtime_released":False,"runtime_reserved":False,
              "note":"Prepare sole green-only bridge and native source evidence only. Original ROOT/author t2_green remain0/1."}
activation_pin = save_new(D/"root-activation.json",activation)
print(json.dumps({"status":"SOURCE_PREPARATION_ONLY","checks":len(CHECKS),"all_checks_true":True,"input_check":receipt,"activation":activation_pin},ensure_ascii=False))
