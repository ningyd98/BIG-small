"""Read-only static verification authorized by Astra R483."""

import ast
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
R482 = HERE.parent / "round482-taichu-offline-scoring-snapshot-20261108"


def main():
    checks = []
    for directory in (HERE, R482):
        plan = json.loads((directory / "plan.json").read_text())
        seen = set()
        for row in plan["input_sha256"]:
            path = ROOT / row["path"]
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            key = str(path.resolve())
            checks.append({"plan": directory.name, "path": row["path"],
                           "bytes": len(data), "sha256": digest,
                           "duplicate_path": key in seen,
                           "match": digest == row["sha256"] and len(data) == row["bytes"]})
            seen.add(key)
    assert all(row["match"] for row in checks)
    script = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/implementation/evaluate_pair_v2.py"
    source = script.read_text()
    assert script.read_bytes() == (HERE / "diagnostic/evaluate_pair_v2.before.py").read_bytes()
    compile(source, str(script), "exec")
    tree = ast.parse(source)
    calls = sorted({node.func.attr for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)})
    blocked = {"plan", "_request_visual", "_post", "_get", "generate", "from_pretrained"}
    assert not blocked.intersection(calls)
    result = {"status": "PASS", "argv": sys.argv, "input_checks": checks,
              "v2_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
              "syntax_compile_without_execution": True, "v2_bytes_unchanged": True,
              "attribute_calls": calls, "blocked_attribute_calls_absent": True,
              "source_review": "Reads fixed local capture/run/response files; constructs offline identity snapshot; invokes original strict parser and _ground_response/_pixel_hit. No service, model load, generation or hardware entry point.",
              "static_check_limit": "Attribute scanning is bounded supporting evidence, not a complete safety proof.",
              "formal_acceptance": "NOT_PERFORMED"}
    with (HERE / "verification.json").open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "input_checks": len(checks),
                      "v2_sha256": result["v2_sha256"]}))


if __name__ == "__main__":
    main()
