from pathlib import Path
import base64
import copy
import hashlib
import json
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round276-p6-t2-first-session-invalidation-capture-20261017")
p = D / "root-context-update.json"
raw = p.read_bytes()
assert len(raw) == 321314 and hashlib.sha256(raw).hexdigest() == "d423936ab5fc4d506f25db3c8b1beb5c2b54de93643c9fee9de812a9b4c27eb0"
m = json.loads(raw)
originals, current = [], []
for change in m["changes"]:
    before, after = change["before"], change["after"]
    old = Path(before["archive"]["path"]).read_bytes()
    assert old == base64.b64decode(before["base64"], validate=True)
    assert len(old) == before["original"]["bytes"] == before["archive"]["bytes"]
    assert hashlib.sha256(old).hexdigest() == before["original"]["sha256"] == before["archive"]["sha256"]
    b = Path(after["path"]).read_bytes()
    assert b == Path(change["after_archive"]["path"]).read_bytes()
    assert len(b) == after["bytes"] == change["after_archive"]["bytes"]
    assert hashlib.sha256(b).hexdigest() == after["sha256"] == change["after_archive"]["sha256"]
    assert Path(after["path"]).lstat().st_mode == Path(before["archive"]["path"]).lstat().st_mode == Path(change["after_archive"]["path"]).lstat().st_mode == change["mode"] == 33204
    originals.append(old)
    current.append(b)
old, new = [json.loads(x) for x in (originals[0], current[0])]
for key in ["R" + str(i) for i in range(268, 277)]:
    old["planning"].pop(key, None)
    new["planning"].pop(key, None)
assert old == new
assert current[1].startswith(originals[1])
s = json.loads(current[0])
assert all(s["planning"]["R268"]["commands"][k]["used"] == 1 and s["planning"]["R268"]["commands"][k]["remaining"] == 0 for k in ("wait_memory_failure", "dual_progress"))
assert s["planning"]["R274"]["status"] == "SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED"
assert all(x["used"] == 0 and x["remaining"] == 1 for x in s["planning"]["R276"]["commands"].values())
report = {"round": "R276", "status": "INDEPENDENT_CONTEXT_READBACK_PASSED", "complete_before_archive_base64_mode": True, "actual_after_matches_archives": True, "all_other_STATE_values_preserved": True, "PHASE_prefix_preserved": True, "R268_spent_R274_source_only_R276_unspent": True, "T2_complete": False}
out = D / "root-context-independent-readback.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
b = out.read_bytes()
print(json.dumps({"status": report["status"], "report": {"path": str(out), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}}, ensure_ascii=False))
