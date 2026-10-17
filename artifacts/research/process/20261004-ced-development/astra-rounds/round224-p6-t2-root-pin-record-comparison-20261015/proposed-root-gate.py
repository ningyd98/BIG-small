from pathlib import Path
import hashlib
import json
import sys

BASE = Path(__file__).resolve().parent
REPORT = BASE / "recovery-input-check.json"
records = []
proofs = {}
cache = {}
errors = []

def identity(value):
    return {key: value[key] for key in ("path", "bytes", "sha256")}

def check(expected, role):
    observed = None
    error = None
    try:
        path = Path(expected["path"])
        data = path.read_bytes()
        observed = {"path": str(path), "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()}
        matches = identity(observed) == identity(expected)
        if matches:
            cache[str(path)] = data
    except Exception as exc:
        matches = False
        error = {"type": type(exc).__name__, "message": str(exc)}
    records.append({"role": role, "expected": expected, "observed": observed,
                    "matches": matches, "error": error})
    return matches

def document(path):
    return json.loads(cache[path])

# The ROOT source gate must pin this source and plan.json before the single run.
# No product is imported, executed, parsed as Python, or written.
try:
    plan = json.loads((BASE / "plan.json").read_bytes())
    for entry in plan["gate_inputs"]:
        check(entry["expected"], entry["role"])
    proofs["all_input_identities"] = all(row["matches"] for row in records)
    proofs["protected211_count"] = sum(row["role"] == "protected211" for row in records) == 211
    protected = [row["expected"]["path"] for row in records if row["role"] == "protected211"]
    proofs["protected211_unique"] = len(set(protected)) == 211
    if proofs["all_input_identities"]:
        authority = document(plan["authorities"]["R222"])
        manifest = document(plan["authorities"]["manifest222"])
        old_manifest = document(plan["authorities"]["manifest158"])
        pairs = authority["current_and_archive_pins"]
        proofs["25_pairs"] = len(pairs) == 25 and pairs == manifest["archives"]
        proofs["protected_authority_exact"] = [row["expected"] for row in records if row["role"] == "protected211"] == old_manifest["protected"]
        proofs["all25_physical_pairs_equal"] = all(cache[x["source"]["path"]] == cache[x["archive"]["path"]] for x in pairs)
        prior = authority["pre_failure_target_archives"]
        proofs["three_prior_archives"] = len(prior) == 3
        proofs["three_targets_equal_prior"] = all(cache[x["source_path"]] == cache[x["physical_before"]["path"]] for x in prior)
        evidence = document(plan["authorities"]["patches220"])
        patches = evidence["patches"]
        targets = {x["source_path"] for x in prior}
        patch_proofs = []
        for item in patches:
            target_lines = [line for line in item["exact_patch"].splitlines() if line.startswith(("*** Update File: ", "*** Add File: ", "*** Delete File: ", "*** Move to: "))]
            paths = [line.split(": ", 1)[1] for line in target_lines]
            patch_proofs.append({"store_key": item["store_key"], "target_lines": target_lines,
                                 "actual_tool_return": item["actual_tool_return"],
                                 "no_target_overlap": not targets.intersection(paths)})
        proofs["nine_patch_count"] = len(patches) == 9
        proofs["nine_do_not_touch_three"] = all(x["no_target_overlap"] for x in patch_proofs)
        proofs["nine_returns_match_frozen_authority"] = all(x["actual_tool_return"] == {} for x in patch_proofs)
        role_proofs = []
        for item in plan["role_expectations"]:
            ledger = document(item["path"])
            observed = {key: {k: ledger["commands"][key][k] for k in ("authorized", "used", "remaining", "state")} for key in ("t2_red", "t2_green")}
            ok = observed == item["expected"]
            role_proofs.append({"path": item["path"], "expected": item["expected"], "observed": observed, "matches": ok})
        proofs["two_role_views_RED_spent_GREEN_held"] = len(role_proofs) == 2 and all(x["matches"] for x in role_proofs)
    else:
        patch_proofs = []
        role_proofs = []
except Exception as exc:
    errors.append({"type": type(exc).__name__, "message": str(exc)})
    patch_proofs = locals().get("patch_proofs", [])
    role_proofs = locals().get("role_proofs", [])
    proofs["metadata_completed_without_exception"] = False

ok = bool(records) and not errors and all(proofs.values())
report = {"schema_version": "astra.r224.identity-recovery-result.v1",
          "status": "PASS_PREPARATION_TEXT_ONLY" if ok else "STOP",
          "records": records, "proofs": proofs, "patch_proofs": patch_proofs,
          "role_proofs": role_proofs, "errors": errors,
          "scope": "Metadata only; no R222 apply/readback or GREEN released",
          "product_execution": False, "product_mutation": False}
raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
# Exclusive write preserves all original and failed outcomes; no retry/overwrite.
try:
    with REPORT.open("xb") as stream:
        stream.write(raw)
except Exception:
    print('{"status":"STOP_REPORT_WRITE_FAILED","retry":false}')
    raise SystemExit(1)
summary = {"status": report["status"], "report": {"path": str(REPORT), "bytes": len(raw),
           "sha256": hashlib.sha256(raw).hexdigest()}, "records": len(records),
           "pin_failures": sum(not x["matches"] for x in records),
           "proof_failures": sum(not x for x in proofs.values()), "errors": len(errors)}
output = json.dumps(summary, ensure_ascii=False)
if len(output.encode("utf-8")) > 6000:
    print('{"status":"STOP_SUMMARY_BOUND","retry":false}')
    raise SystemExit(1)
print(output)
raise SystemExit(0 if ok else 1)
