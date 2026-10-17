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
    target = D / "before/root-parent-green7-reservation" / label
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


# Filled only after actual soleSol source/native evidence and full ROOT reading.

def reconstruct_one_recorded_update(before_raw, argument, exact_target):
    lines = argument.splitlines()
    if (not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch"
            or len(lines) < 4 or lines[1] != "*** Update File: " + exact_target):
        raise ValueError("exact single-target native Update envelope required")
    body = lines[2:-1]
    if any(x.startswith("*** ") and x != "*** End of File" for x in body):
        raise ValueError("additional native file operation is outside this finite source change")
    original = before_raw.decode("utf-8").splitlines()
    if not before_raw.endswith(b"\n") or b"\r" in before_raw:
        raise ValueError("known LF source contract required")
    chunks, current = [], None
    eof = False
    for line in body:
        if line.startswith("@@"):
            if current is not None:
                chunks.append(current)
            current = {"old":[], "new":[]}
        elif line == "*** End of File":
            eof = True
        else:
            if current is None or not line or line[0] not in " +-":
                raise ValueError("unsupported recorded native update line")
            if line[0] in " -":
                current["old"].append(line[1:])
            if line[0] in " +":
                current["new"].append(line[1:])
    if current is not None:
        chunks.append(current)
    if not chunks:
        raise ValueError("empty native source update")
    cursor, rebuilt, applications = 0, [], []
    for ordinal, chunk in enumerate(chunks):
        old, new = chunk["old"], chunk["new"]
        if not old:
            raise ValueError("anchored original source context required")
        possible = [i for i in range(cursor, len(original)-len(old)+1)
                    if original[i:i+len(old)] == old]
        if not possible:
            raise ValueError("recorded update original byte context absent")
        position = possible[0]
        rebuilt.extend(original[cursor:position])
        rebuilt.extend(new)
        cursor = position + len(old)
        applications.append({"ordinal":ordinal, "old_start_line":position+1,
                             "old_lines":len(old), "new_lines":len(new)})
    if eof and cursor != len(original):
        raise ValueError("recorded end-of-file boundary differs")
    rebuilt.extend(original[cursor:])
    return ("\n".join(rebuilt)+"\n").encode("utf-8"), applications


D264 = D.parent / "round264-p6-t2-parent-bridge-lifecycle-case-binding-20261017"
def fixed(path, size, digest):
    return {"path":str(path), "bytes":size, "sha256":digest}
PARENT_PLAN_PIN = P["authority"]["parent_plan"]
G0_PIN = fixed(D/"input-check.json",888422,"61f245b551e38a0d819f5de8731d51b0b705f08e939d3092a840b0513b4f8e65")
REVIEW_PIN = fixed(D264/"root-full-source-and-contract-review.json",90737,"19976bdbb39379a6b6f8f588d644ccbdf8750df95e25d70afda63cf96b10a724")
REPORT_PIN = fixed(D264/"implementation/change-report.json",164156,"2170e201ae82be60966a9e182dea6791c6b8833300d1b0a140a0e35b385b1603")
NATIVE_PIN = fixed(D264/"implementation/actual-runner-native-tool-return.json",185002,"d76a0d000b93622ca6eada940909e0ed354ce1c4d5a55bfddbfb5ec54348a907")
RUNNER_PIN = fixed(D/"implementation/run-parent-t2-green.py",71517,"c157178f61ae3609356fa9441f9f953b116a4ebccbd8f324b172b6d2c0980cba")
P264_PIN = fixed(D264/"plan.json",18817,"76deed087d52b0806c5f70bd01975941d0b70817747a8241067ce699cac91666")
P264 = parsed_pin(P264_PIN,"R264_plan")
EXTRA_FIXED_INPUTS = [P264_PIN,REPORT_PIN,NATIVE_PIN,REVIEW_PIN,G0_PIN,
 fixed(D264/"plan.md",4256,"2278157c211cafcd5e443f071901e677d8042ca3a7f720d5f633c4b3ddbec9f3"),
 fixed(D264/"input-observation.json",10328,"dba8815f302852239921aae670c3cbc16b6e015cd457edf0f7fb7b27f853eb5a"),
 fixed(D264/"root-source-correction-release.json",44234,"5a44a7b5d121c22f04dae752eaeee020c37c8d1303beef400c0a776c880f895c"),
 fixed(D264/"implementation/source-preparation-actual-tool-returns.json",45566,"1fd562cd08c76d2de5ae8e5689ad92b0ffe8bd825e8409ac727d32efa0f4876a"),
 fixed(D/"root-source-preparation-actual.json",51205,"dad867b478caee03beb71a8b9d924293c1d15a62188f10265c53713db00e0211"),
 fixed(D/"root-source-preparation-gate.py",13168,"370e46cb9ccfa2798abfe5ec6e29c317757b35861c2afa181222c4ccdc06219d")]
report = parsed_pin(REPORT_PIN,"R264_report")
for name in ("runner_before","before_manifest","candidate","native_receipt","limited_diff"):
    direct(report[name],"R264_report_pin:"+name)
    EXTRA_FIXED_INPUTS.append(report[name])
current = direct(RUNNER_PIN,"corrected_runner")
candidate = direct(report["candidate"],"complete_candidate")
before = direct(report["runner_before"],"complete_v1_before")
manifest = parsed_pin(report["before_manifest"],"v1_fullbefore_manifest")
check("candidate_live_full_bytes",candidate == current == base64.b64decode(report["after_full_base64"],validate=True))
check("physical_fullbefore_equality", before == base64.b64decode(manifest["base64"],validate=True)
      and raw_pin(before,manifest["original"]["path"]) == manifest["original"])
check("source_modes", [read_regular(x["path"])[1] for x in (report["runner_before"],report["candidate"],RUNNER_PIN)] == [33204]*3)
check("source_shape",len(current.splitlines()) == report["source_lines"] == 1243 and current.endswith(b"\n") and b"\r" not in current)
for i,pin in enumerate(P264["inputs"]):
    if identity(pin) == identity(manifest["original"]):
        check("R264_exact_historical_v1:"+str(i),raw_pin(before,pin["path"]) == pin)
        RESOLUTIONS.append({"original":pin,"archive":report["runner_before"]})
    else:
        direct(pin,"R264_input:"+str(i))
        EXTRA_FIXED_INPUTS.append(pin)
review = parsed_pin(REVIEW_PIN,"ROOT_full_corrected_review")
check("ROOT_full1243_review",len(review["actual_reads"]) == 7
      and all(x["actual"]["exit_code"] == 0 and "session_id" not in x["actual"] for x in review["actual_reads"])
      and review["blocking_findings"] == [] and review["runtime_released"] is False)
g0 = parsed_pin(G0_PIN,"original_G0")
check("original_G0_all1410",len(g0["checks"]) == 1410 and all(x["ok"] is True for x in g0["checks"]))
helper = before[before.index(b"def _t2_pin("):before.index(b"def _t2_pin(")+17622]
check("original17622_helper_exact_once",len(helper)==17622
      and hashlib.sha256(helper).hexdigest()=="0a2601487ad75ccb1ae32872d40f340ab74ba799aa394f76855fea898687ffe4"
      and before.count(helper)==current.count(helper)==1)
old_bounds = [(0,before.index(b"def cas_author(")),
              (before.index(b"def strict_index("),before.index(b"def capture_cases(")),
              (before.index(b"def retained_new_databases("),before.index(b"def main():")),
              (before.index(b'if __name__ == "__main__":'),len(before))]
new_bounds = [(0,current.index(b"def author_bytes(")),
              (current.index(b"def strict_index("),current.index(b"def capture_cases(")),
              (current.index(b"def retained_new_databases("),current.index(b"def main():")),
              (current.index(b'if __name__ == "__main__":'),len(current))]
for i,((lo,hi),(a,b)) in enumerate(zip(old_bounds,new_bounds,strict=True)):
    check("exact_unchanged_outside_region:"+str(i),before[lo:hi] == current[a:b])
import difflib
expected_diff = "".join(difflib.unified_diff(before.decode().splitlines(keepends=True),
              current.decode().splitlines(keepends=True),fromfile=report["runner_before"]["path"],
              tofile=RUNNER_PIN["path"])).encode()
check("full_limited_diff_exact",direct(report["limited_diff"],"complete_limited_diff") == expected_diff)
def recorded_add(argument, path):
    rows = argument.splitlines()
    if (rows[:2] != ["*** Begin Patch","*** Add File: "+path]
            or rows[-1] != "*** End Patch" or not all(x.startswith("+") for x in rows[2:-1])):
        raise ValueError("one exact recorded AddFile required")
    return ("\n".join(x[1:] for x in rows[2:-1])+"\n").encode()
native = parsed_pin(NATIVE_PIN,"new_actual_native_receipt")
check("native_two_finite_stages",len(native["stages"])==2 and
      [x["id"] for x in native["stages"]] == ["before_candidate","implementation"] and native["runtime_execution"] is False)
for row in native["stages"]:
    check("honest_native:"+row["id"],row["tool"]=="tools.apply_patch"
          and row["actual_tool_return"]=={} and all(row[k] is None for k in
              ("numeric_exit","independent_stdout","independent_stderr")))
check("candidate_native_full_reconstruction",
      recorded_add(native["stages"][0]["arguments"],report["candidate"]["path"]) == candidate)
old_native_pin = next(x for x in P264["inputs"] if x["path"]==str(D/"implementation/actual-runner-native-tool-return.json"))
old_native = parsed_pin(old_native_pin,"old_actual_AddFile")
check("old_AddFile_full_reconstruction",recorded_add(old_native["implementation"]["arguments"],RUNNER_PIN["path"]) == before
      and old_native["implementation"]["actual_tool_return"]=={}
      and old_native["implementation"]["numeric_exit"] is None)
rebuilt, applications = reconstruct_one_recorded_update(before,native["stages"][1]["arguments"],RUNNER_PIN["path"])
check("recorded_Update_complete_reconstruction",rebuilt == candidate == current and len(applications)==3)
check("native_actual_preparation_reads",all(native[k]["actual"]["exit_code"]==0
      for k in ("before_archive","candidate_readback_and_immediate_before_CAS")))
check("expected_case_contract", report["case_binding_source_disposition"]["expected"] == P264["case_binding_contract"]["expected"]
      and report["case_binding_source_disposition"]["success_counts"] == {"nodes":7,"directories":15,"scenario_files":19})
unique = {}
for pin in EXTRA_FIXED_INPUTS:
    unique[identity(pin)]={k:pin[k] for k in ("path","bytes","sha256")}
EXTRA_FIXED_INPUTS=list(unique.values())
for i,pin in enumerate(EXTRA_FIXED_INPUTS):
    direct(pin,"new_immutable_fixed:"+str(i))

for name,row in P["inputs"]["parent_role_timepoint"].items():
    role = parsed_pin(row["pin"], "parent_pre_reservation:" + name)
    check("original_parent_green_held:" + name, all(role["commands"]["t2_green"][k] == row["t2_green"][k] for k in ("state","used","remaining")))
    archive_before(row["pin"], name)
for name,pin in P["inputs"]["mutable_current_context"].items():
    archive_before(pin, name)
for path in P["command"]["output_paths"].values():
    absent(path,"unused_runtime_output")
for path in ("source-gate.json","script-gate.json","root-parent-green7-reservation.json"):
    absent(D/path,"exclusive_new_ROOT_gate")
parent_plan = parsed_pin(PARENT_PLAN_PIN,"parent_original_plan")
original_command = parent_plan["commands"]["t2_green"]
check("parent_original_green_exact_overlay_authority", original_command == P["command"]["original_record"])

command = P["command"]
parent_nodes = [v for v in original_command["argv"] if "::" in v]
check("exact_original7_order", command["exact_nodes"] == parent_nodes and len(parent_nodes) == len(set(parent_nodes)) == 7)
expected_argv = [str(R/".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "-p", "r235_startup_prerequisite", *parent_nodes,
                 "--basetemp=" + command["output_paths"]["basetemp"],
                 "--junitxml=" + command["output_paths"]["JUnit"]]
check("exact_finite_effective_argv", command["effective_argv"] == expected_argv)
check("exact_launcher_argv", command["launcher_argv"] == [str(R/".venv/bin/python"), RUNNER_PIN["path"],"t2_green"])
plugin_dir = str(Path(P["prerequisite"]["plugin"]["path"]).parent)
check("exact_child_environment", command["finite_child_environment"] == {
    "PATH":str(R/".venv/bin")+":/usr/bin:/bin","LANG":"C.UTF-8","PYTHONDONTWRITEBYTECODE":"1",
    "PYTHONPATH":"src:.:"+plugin_dir,"BIGSMALL_R158_COMMAND":"t2_green",
    "BIGSMALL_R158_T2_RESOURCE_DIR":str(D/"implementation/green/resources"),
    "BIGSMALL_R235_PREREQUISITE_RECORD":command["output_paths"]["prerequisite"]})
check("exact_launcher_environment", command["finite_launcher_environment"] == {
    "PATH":str(R/".venv/bin")+":/usr/bin:/bin","LANG":"C.UTF-8","PYTHONDONTWRITEBYTECODE":"1"})
check("exact_timing_and_cwd", command["cwd"] == str(R) and
      [command[k] for k in ("child_timeout_seconds","cleanup_total_seconds","TERM_grace_within_cleanup_seconds",
       "outer_transport_timeout_seconds","outer_transport_kill_after_seconds")] == [600,15,5,900,20])
import shlex
q = shlex.quote
literal = ("set -o noclobber\n/usr/bin/env -i " + q("PATH="+str(R/".venv/bin")+":/usr/bin:/bin")+
           " LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 /usr/bin/timeout --signal=TERM --kill-after=20s 900s "+
           q(str(R/".venv/bin/python"))+" "+q(RUNNER_PIN["path"])+" t2_green > "+
           q(command["output_paths"]["outer_stdout"])+" 2> "+q(command["output_paths"]["outer_stderr"]))
check("exact_tool_literal", command["exact_tool_arguments"] == {
    "cmd":literal,"workdir":str(R),"yield_time_ms":1000,"max_output_tokens":2000})

if not all(x["ok"] for x in CHECKS):
    failure = save_new(D/"root-runtime-gate-failure.json",{"checks":CHECKS,"all_checks_true":False})
    print(json.dumps({"status":"STOP","report":failure},ensure_ascii=False))
    raise SystemExit(1)

source_gate = {"round":"R258","status":"VERIFIED_SOURCE_ONLY","plan":PLAN_PIN,
               "observation":OBS_PIN,"input_check":G0_PIN,"runner":RUNNER_PIN,"native":NATIVE_PIN,
               "checks":CHECKS,"all_checks_true":True,"ROOT_review":REVIEW_PIN,"fixed_inputs":EXTRA_FIXED_INPUTS,
               "runtime_reserved":False,"T2_complete":False}
SOURCE_GATE_PIN = save_new(D/"source-gate.json",source_gate)
script_gate = {"round":"R258","status":"VERIFIED_BY_ROOT","command_id":"t2_green","plan":PLAN_PIN,
               "observation":OBS_PIN,"runner":RUNNER_PIN,"source_gate":SOURCE_GATE_PIN,
               "original_command":original_command,"command":P["command"],
               "root_reservation_path":str(D/"root-parent-green7-reservation.json")}
SCRIPT_GATE_PIN = save_new(D/"script-gate.json",script_gate)
import copy
import uuid
reservation_id = "R258-original-R158-t2_green-" + str(uuid.uuid4())
continuation = {"reservation_id":reservation_id,"plan":PLAN_PIN,"runner":RUNNER_PIN,
                "source_gate":SOURCE_GATE_PIN,"script_gate":SCRIPT_GATE_PIN,"command":P["command"]}
root_before = next(x for x in ARCHIVES if x["original"]["path"] == P["budget"]["ROOT_ledger"])
author_before = next(x for x in ARCHIVES if x["original"]["path"] == P["budget"]["author_ledger"])
raw_before = base64.b64decode(root_before["base64"],validate=True)
root_original = json.loads(raw_before)
root_expected = copy.deepcopy(root_original)
entry = root_expected["commands"]["t2_green"]
entry.update({"used":1,"remaining":0,"state":"RESERVED_BY_ROOT","reservation_id":reservation_id})
entry.setdefault("continuation",{})["R258"] = continuation
root_expected["active_task"] = "T2"
expected_raw = (json.dumps(root_expected,ensure_ascii=False,indent=2)+"\n").encode()
if (json.dumps(root_original,ensure_ascii=False,indent=2)+"\n").encode() != raw_before:
    raise ValueError("canonical ROOT input serialization changed before reservation")
current_raw, current_mode = read_regular(root_before["original"]["path"])
if current_raw != raw_before:
    raise ValueError("ROOT original ledger changed at immediate full-byte CAS")
target = Path(root_before["original"]["path"])
temp = D / "before/root-parent-green7-reservation/root-reserved-ledger.new"
with temp.open("xb") as stream:
    os.fchmod(stream.fileno(), stat.S_IMODE(current_mode))
    stream.write(expected_raw)
    stream.flush()
    os.fsync(stream.fileno())
# Sole ROOT is the authorized writer; repeat full bytes immediately before atomic replace.
current_raw,_ = read_regular(target)
if current_raw != raw_before:
    raise ValueError("ROOT original ledger changed immediately before replace")
os.replace(temp,target)
actual_after, after_mode = read_regular(target)
if actual_after != expected_raw or after_mode != current_mode:
    raise ValueError("ROOT reserved ledger readback mismatch")
ROOT_AFTER_PIN = raw_pin(actual_after,target)
reservation = {"schema_version":"bigsmall.r258.root-original-green-reservation.v1","round":"R258","command_id":"t2_green",
               "reservation_id":reservation_id,"status":"RESERVED_BY_ROOT","plan":PLAN_PIN,"runner":RUNNER_PIN,
               "source_gate":SOURCE_GATE_PIN,"script_gate":SCRIPT_GATE_PIN,"exact_tool_arguments":P["command"]["exact_tool_arguments"],
               "role_before":[{"original":x["original"],"archive":x["physical"],"base64":x["base64"]} for x in (root_before,author_before)],
               "context_history":[],"context_before":[{"original":x["original"],"archive":x["physical"],"base64":x["base64"]} for x in ARCHIVES if x not in (root_before,author_before)],
               "root_role_after":ROOT_AFTER_PIN,"author_role_before":author_before["original"],
               "effective_command":P["command"],"original_command":original_command,
               "ROOT_continuation":continuation,"source_gate_checks":len(CHECKS),"all_checks_true":True,
               "budget_origin":"R158","original_authorized":1,"original_used":1,"original_remaining":0,
               "no_retry":True,"T2_complete":False}
RESERVATION_PIN = save_new(D/"root-parent-green7-reservation.json",reservation)
print(json.dumps({"status":"RESERVED_BY_ROOT","reservation":RESERVATION_PIN,"root_role_after":ROOT_AFTER_PIN,
                  "source_gate":SOURCE_GATE_PIN,"script_gate":SCRIPT_GATE_PIN,"checks":len(CHECKS),"all_checks_true":True,
                  "original_t2_green":{"used":1,"remaining":0},"child_executed_by_ROOT":False},ensure_ascii=False))

