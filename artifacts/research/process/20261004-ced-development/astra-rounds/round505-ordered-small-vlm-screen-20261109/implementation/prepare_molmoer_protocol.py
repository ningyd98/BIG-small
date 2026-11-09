import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
OUT = HERE / "candidates/04-molmoer"
def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
cpu = json.loads((OUT / "cpu-contract-r507.json").read_text())
assert cpu["status"] == "PASS"
assets = json.loads((OUT / "download-result.json").read_text())
assert assets["status"] == "PASS"
for row in assets["files"]:
    path = Path(row["path"])
    assert path.stat().st_size == row["size"] and sha(path) == row["sha256"]
sources = [HERE / "implementation" / p for p in ["score_native.py", "molmoer_adapter.py", "cpu_molmoer.py", "prepare_molmoer_protocol.py", "run_candidate_molmoer.py"]]
from molmoer_adapter import native_prompt
protocol = {"candidate": "04-molmoer", "official_model_repo": "allenai/Molmo2-ER", "precision": "BF16 full model",
            "model_directory": str(CACHE / "models/Molmo2-ER"), "runtime": str(CACHE / "runtimes/molmoer-r505/bin/python"),
            "versions": cpu["versions"], "attention": "sdpa", "thinking": "no configurable thinking branch exposed",
            "native_modes": ["point"], "primary_mode": "point", "native_prompt_example": native_prompt("{phrase}"),
            "native_output": "official UnifiedPointFormatter coordinates: image_id=1 then object_id x y triples; normalized_1000",
            "selection": "first original predicted point; no oracle selection",
            "JSON_RGB": "UNSUPPORTED_SYSTEM_ROLE", "JSON_DUAL": "UNSUPPORTED_SYSTEM_ROLE",
            "dual_CPU": cpu["dual_image_processor"], "depth_causal_use": "NOT_ASSESSED",
            "authorized_model_loads": 1, "authorized_generation_calls": 34, "candidate_cumulative_cap": 134,
            "generation": {"max_new_tokens": 512, "do_sample": False, "num_beams": 1, "use_cache": True, "seed": 0},
            "public_inputs_sha256": sha(HERE / "diagnostic/model-inputs.json"), "cpu_contract_sha256": sha(OUT / "cpu-contract-r507.json"),
            "asset_verification": "ALL_26_FILES_HASHED_IMMEDIATELY_BEFORE_PROTOCOL_FREEZE", "asset_manifest_sha256": sha(OUT / "asset-manifest.json"),
            "official_format_evidence_sha256": sha(OUT / "published-point-contract-r507.json"), "plan_r507_sha256": sha(HERE.parent / "round507-molmoer-transformers-compat-20261109/plan.json"),
            "research_sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sources],
            "formal_acceptance": "NOT_PERFORMED", "hardware_dispatch": False}
for name in ["protocol-r507.json", "protocol.json"]:
    with (OUT / name).open("x") as stream:
        json.dump(protocol, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
print("MOLMOER_PROTOCOL_FROZEN", sha(OUT / "protocol-r507.json"), flush=True)
