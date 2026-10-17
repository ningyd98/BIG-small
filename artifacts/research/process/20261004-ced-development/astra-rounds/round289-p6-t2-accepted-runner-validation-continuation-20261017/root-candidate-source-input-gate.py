"""Original R289 ordinary source/input gate: candidate/native phase only; no imports of delivered code."""
from pathlib import Path
import base64
import hashlib
import json
import re
import stat

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017"
A = D.parent
FIXED = json.loads(r'''[["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/plan.json",48642,"4bc64ed58a737cb9f6bbe7386a9937a189b3e1522258e8a85c051bbd8f5fe5fb"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/input-observation.json",371055,"82c31139a709e11ca78fefaae3bc8df9cda1612a0584e2c391a527b9b1501cf3"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/prerequisite-supplement.json",6492,"fc267162c6ad812a056191eef27c727ae2009248c2034c58baeae53562fdfd19"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017/implementation/candidate-native-tool-returns.json",127203,"24524ee406b4fbbed5eb9af204f694c6c913f6d2a939f78a90173495a9d9287b"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round291-p6-t2-dual-lease-source-selector-binding-20261017/plan.json",11702,"3ecb53c9d2316db56f7431a30554a66fb3590b94ec2c21c5d639e2e58ec9b066"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round291-p6-t2-dual-lease-source-selector-binding-20261017/input-observation.json",5531,"305545be93c471f8c5e1259d4594d39ff5f914570c9aad33284c0178eebe8390"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round291-p6-t2-dual-lease-source-selector-binding-20261017/implementation/change-report.json",4470,"a86cd1bf7de4e511b897fcfaa0fc83dde85ba1f10e32c661c5fc44f3e181e3de"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round292-p6-t2-role-envelope-source-binding-20261017/plan.json",10850,"f193f955421f1f1be3afbf9b923c45d2ff71125c3d5fd00096ce98fbf9e4b36f"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round292-p6-t2-role-envelope-source-binding-20261017/input-observation.json",7810,"1a1bb76a69e3c206a0ad331a15b6e330fe8e17631ed8cb8110a21719a3b499d9"],["/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round292-p6-t2-role-envelope-source-binding-20261017/implementation/change-report.json",3758,"d860b49b410d8d4494898532238af7862e3f77f681deafa91cdfe6ddbe02094a"]]''')
checks = []
fixed_inputs = {}

def check(label, value):
    checks.append({"check": label, "passed": bool(value)})
    if not value:
        raise AssertionError(label)

def identity(row):
    return {key: row[key] for key in ("path", "bytes", "sha256")}

def pin(path, data=None):
    path = Path(path)
    if data is None:
        check("regular " + str(path), stat.S_ISREG(path.lstat().st_mode))
        data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def checked(row):
    item = identity(row)
    path = Path(item["path"])
    check("regular " + str(path), stat.S_ISREG(path.lstat().st_mode))
    data = path.read_bytes()
    check("identity " + str(path), pin(path, data) == item)
    previous = fixed_inputs.get(str(path))
    check("one exact current pin " + str(path), previous is None or previous == item)
    fixed_inputs[str(path)] = item
    return data

def document(row):
    return json.loads(checked(row))

def full(row):
    data = base64.b64decode(row["base64"], validate=True)
    check("whole before/archive/base64", checked(row["archive"]) == data
          and checked(row["original"]) == data)
    check("whole before modes", Path(row["original"]["path"]).lstat().st_mode
          == Path(row["archive"]["path"]).lstat().st_mode == row["mode"] == 33204)
    return data

def native_add(packet, target, data):
    check("native honest receipt", packet["tool"] == "tools.apply_patch"
          and packet["actual_tool_return"] == {}
          and all(packet[key] is None for key in ("numeric_exit", "independent_stdout",
                                                 "independent_stderr", "target_before")))
    argument = packet["arguments"]
    check("native LF text", type(argument) is str and "\r" not in argument)
    framed = argument[:-1] if argument.endswith("\n") else argument
    lines = framed.split("\n")
    check("single exact Add frame", lines[:2] == ["*** Begin Patch", "*** Add File: " + str(target)]
          and lines[-1] == "*** End Patch" and all(line.startswith("+") for line in lines[2:-1]))
    rebuilt = ("\n".join(line[1:] for line in lines[2:-1]) + "\n").encode("utf-8")
    check("native complete reconstruction " + str(target), rebuilt == data)
    return {"target": str(target), "argument_utf8_bytes": len(argument.encode("utf-8")),
            "argument_sha256": hashlib.sha256(argument.encode("utf-8")).hexdigest(),
            "argument_final_LF": argument.endswith("\n")}

for path, size, digest in FIXED:
    checked({"path": path, "bytes": size, "sha256": digest})
P = json.loads((D / "plan.json").read_bytes())
O = json.loads((D / "input-observation.json").read_bytes())
S = json.loads((D / "prerequisite-supplement.json").read_bytes())
check("actual frozen Astra32", P["round"] == "R289" and P["actual_model"] == "gpt-6-astra"
      and len(P["inputs"]) == 32 and O["inputs"] == P["inputs"])
check("actual finite eight supplement", S["round"] == "R289" and S["input_count"] == len(S["inputs"]) == 8)
for row in P["inputs"] + S["inputs"]:
    checked(row)
for row in document(P["before_manifest"])["records"]:
    full(row)
source_container = document(P["authority_contract"]["container"])
check("finite current authority", len(source_container["sources"]) == 27
      and len(source_container["authority_before"]["protected"]) == 211)
for row in source_container["sources"]:
    data = checked(row)
    check("current full physical/base64", data == checked(row["physical"])
          == base64.b64decode(row["base64"], validate=True)
          and Path(row["path"]).lstat().st_mode == row["mode"])
for row in source_container["authority_before"]["protected"]:
    checked(row)
lease_path = str(ROOT / "src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py")
lease_rows = [row for row in source_container["sources"] if row["path"] == lease_path]
check("unique checked current lease", len(lease_rows) == 1
      and lease_rows[0]["bytes"] == 40869
      and lease_rows[0]["sha256"] == "f71d9bcb9c38a7c93e989f7649360b4a0624b4cc2d869bc389b9c9f6b8a76580")
check("finite explicit role envelopes", set(O["R285_role_pins"]) == {"ROOT", "AUTHOR"})
for role in ("ROOT", "AUTHOR"):
    check("role envelope schema", set(O["R285_role_pins"][role]) == {"pin", "commands"})
    checked(O["R285_role_pins"][role]["pin"])

proofs = []
candidates = {}
for number, dirname in ((291, "round291-p6-t2-dual-lease-source-selector-binding-20261017"),
                        (292, "round292-p6-t2-role-envelope-source-binding-20261017")):
    directory = A / dirname
    plan = json.loads((directory / "plan.json").read_bytes())
    observation = json.loads((directory / "input-observation.json").read_bytes())
    report = json.loads((directory / "implementation/change-report.json").read_bytes())
    check("exact source supplement", plan["round"] == report["round"] == "R" + str(number)
          and plan["actual_model"] == "gpt-6-astra" and plan["inputs"] == observation["inputs"])
    for row in plan["inputs"]:
        checked(row)
    before = full(document(plan["full_before"]))
    candidate = checked(report["candidate"])
    check("complete after archive", checked(report["after"]) == candidate
          and Path(report["candidate"]["path"]).lstat().st_mode
          == Path(report["after"]["path"]).lstat().st_mode == report["mode"] == 33204)
    change = plan["scope"]["exact_change"]
    old, new = change["old"].encode(), change["new"].encode()
    check("unique one-line scope", before.count(old) == 1 and candidate == before.replace(old, new, 1))
    expected = change["expected_after"]
    check("entire expected candidate identity", len(candidate) == expected["bytes"]
          and len(candidate.splitlines()) == expected["lines"]
          and hashlib.sha256(candidate).hexdigest() == expected["sha256"])
    proof = document(report["scope_proof"])
    for row in proof["input_records"]:
        checked(row)
    start = before.index(old)
    prefix, suffix = before[:start], before[start + len(old):]
    check("original prefix/suffix unchanged", candidate[:start] == prefix
          and candidate[start + len(new):] == suffix and proof["start_byte"] == start)
    for name, data in (("prefix", prefix), ("suffix", suffix)):
        check("exact reported " + name, proof[name] == {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "exact_before_after": True})
    check("source-only report", report["source_contract_round"] == "R289"
          and report["candidate_executed"] is False and report["implementation_targets_added"] is False
          and report["new_runtime"] == report["new_static"] == 0)
    native = document(report["native"])
    native_proof = native_add(native, report["candidate"]["path"], candidate)
    checked(report["limited_diff"])
    check("real exact source proof flags", proof["complete_single_substitution"] is True
          and proof["native_reconstruction_exact"] is True and proof["runtime_executed"] is False)
    proofs.append({"round": plan["round"], "candidate": report["candidate"], "native": report["native"],
                   "native_proof": native_proof, "scope": report["scope_proof"]})
    candidates[number] = candidate

original_packet_pin = next(row for row in json.loads((A / "round292-p6-t2-role-envelope-source-binding-20261017/plan.json").read_bytes())["inputs"]
                           if row["path"] == str(D / "original-source-role-envelope-selector-mismatch.json"))
packet = document(original_packet_pin)
before = candidates[291]
coverage = [(1, 400), (401, 800), (801, 1200), (1201, 1586)]
check("four actual complete ROOT reads", len(packet["full_source_ROOT_reads"]) == 4)
for row, (low, high) in zip(packet["full_source_ROOT_reads"], coverage):
    actual = row["actual"]
    expected = b"".join(before.splitlines(keepends=True)[low - 1:high])
    check("uncapped exact ROOT source coverage", actual["exit_code"] == 0
          and actual["output"].encode("utf-8") == expected and len(expected) <= 40000
          and high - low + 1 <= 600)
plugin_pin = json.loads((A / "round292-p6-t2-role-envelope-source-binding-20261017/implementation/change-report.json").read_bytes())["plugin_unchanged"]
plugin = checked(plugin_pin)
plugin_template = checked(P["source_generation"]["plugin_template"])
expected_plugin = plugin_template.replace(
    b"round285-p6-t2-new-test-generation-validation-continuation-20261017", D.name.encode()
).replace(b"R285", b"R289").replace(b"r285", b"r289").replace(
    b"22983a42ecd12e188440b42a0491c059957e96998b546e769e3bd3ceaef0ffa0",
    pin(D / "plan.json")["sha256"].encode())
check("whole plugin only explicit identity bindings", plugin == expected_plugin
      and len(plugin.splitlines()) == 454)
candidate_native = document({"path": str(D / "implementation/candidate-native-tool-returns.json"),
                             "bytes": 127203, "sha256": "24524ee406b4fbbed5eb9af204f694c6c913f6d2a939f78a90173495a9d9287b"})
check("two original candidate native stages", len(candidate_native["stages"]) == 2)
original_candidate = D / "implementation/prepared-run-evidence-source.txt"
native_add(candidate_native["stages"][0], original_candidate, original_candidate.read_bytes())
native_add(candidate_native["stages"][1], plugin_pin["path"], plugin)

accepted_runner = document(P["source_generation"]["runner_acceptance"]["container"])
check("C486 actual source-only acceptance", accepted_runner["corrected_source_acceptance"]["status"] == "FULL_SOURCE_ONLY_NATIVE_SCOPE_ACCEPTED")
old = checked(P["source_generation"]["accepted_runner"])
new = candidates[292]
def function(data, name):
    start = data.index(b"def " + name + b"(")
    end = data.find(b"\ndef ", start + 4)
    return data[start:len(data) if end < 0 else end + 1]
for name in (b"_t2_pin", b"_t2_cleanup", b"diagnostic_resources", b"_t2_index",
             b"completion_marker_fact", b"behavior_resources_complete"):
    check("byte-identical accepted helper " + name.decode(), function(old, name) == function(new, name))
check("protected main only R289 identity", function(new, b"main") == function(old, b"main").replace(b"R285", b"R289").replace(b"r285", b"r289"))
lease_old = b'"lease": next(x for x in context["plan"]["inputs"]'
lease_new = b'"lease": next(x for x in context["before_check"]["sources"]'
check("session consumer only identity and R291 binding", function(new, b"session_observations")
      == function(old, b"session_observations").replace(b"R285", b"R289").replace(b"r285", b"r289").replace(lease_old, lease_new, 1))
check("authority established before consumer", b'context["before_check"] = authority(context)' in function(new, b"preconditions")
      and function(new, b"main").index(b"context = preconditions()") < function(new, b"main").index(b"session_observations("))
roles = {role: P["runner_contract"]["roles"][role] for role in ("ROOT", "AUTHOR")}
for path in list(roles.values()) + P["scope"]["new_sources"]:
    check("still absent before source Add " + path, not Path(path).exists() and not Path(path).is_symlink())
record = {"round": "R289", "status": "CANDIDATE_FULL_SOURCE_NATIVE_INPUT_REVIEW_ACCEPTED_NO_RUNTIME",
          "checks_passed": len(checks), "checks": checks, "fixed_inputs": list(fixed_inputs.values()),
          "proofs": proofs, "runner_candidate": proofs[-1]["candidate"], "plugin_candidate": plugin_pin,
          "ROOT_full_source_review_reuse": True, "runtime": 0, "roles_created": False, "T2_complete": False}
path = D / "root-candidate-source-native-acceptance.json"
with path.open("x", encoding="utf-8") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"round": "R289", "status": record["status"], "checks_passed": len(checks),
                  "receipt": pin(path)}, ensure_ascii=False))
