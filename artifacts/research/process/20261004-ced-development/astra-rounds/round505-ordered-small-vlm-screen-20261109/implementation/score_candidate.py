"""Offline R505 scoring; oracle files are never imported by model runners."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from score_native import point_pixel, pixel_assessment, mask_pixel, box_iou, strict_json

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
sys.path.insert(0, str(ROOT / "src"))
from cloud_edge_robot_arm.vision.planner import VisualDecision


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_scalar(value):
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def stats(values):
    return {"n": len(values), "p50_s": float(np.percentile(values, 50)) if values else None,
            "p90_s": float(np.percentile(values, 90)) if values else None}


def native_latency(rows):
    native = [r for r in rows if r["stage"].startswith("NATIVE") and not r["repeat"]]
    modes = sorted({m for r in native for m in r["modes"]})
    result = {}
    for mode in modes:
        mode_rows = [r for r in native if mode in r["modes"]]
        first = mode_rows[0] if mode_rows else None
        cold = bool(first is not None and native and first is native[0])
        result[mode] = {"first_request_s": first["end_to_end_s"] if first else None,
                        "first_is_process_cold": cold,
                        "cold_first_request_s": first["end_to_end_s"] if cold else None,
                        "warm_excluding_first": stats([r["end_to_end_s"] for r in mode_rows[1:]]),
                        "fixed_repetitions": stats([r["end_to_end_s"] for r in rows if r["stage"].startswith("NATIVE") and r["repeat"] and mode in r["modes"]])}
    return {"native_by_mode": result}


def resolve_score_inputs(candidate, run_json, protocol_json, output_name):
    out=(HERE/"candidates"/candidate).resolve()
    if (run_json is None)!=(protocol_json is None):
        raise ValueError("run-json and protocol-json must be selected together")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json",output_name) or ".." in output_name:
        raise ValueError("output-name must be a safe JSON basename")
    paths=[]
    for supplied,default in [(run_json,"run-01.json"),(protocol_json,"protocol.json")]:
        path=Path(supplied).resolve() if supplied is not None else out/default
        if path.parent!=out or path.is_symlink() or not path.is_file() or path.suffix!=".json" or "progress" in path.name or path.name.endswith(".local.json"):
            raise ValueError("input must be a sealed JSON in this candidate directory")
        paths.append(path)
    run_path,protocol_path=paths
    if json.loads(run_path.read_text()).get("protocol_sha256")!=digest(protocol_path):
        raise ValueError("selected run/protocol hash mismatch")
    output=out/output_name
    if output.exists():raise FileExistsError(output)
    return run_path,protocol_path,output


def score(candidate, *, run_json=None, protocol_json=None, output_name="score-03.json"):
    out = HERE / "candidates" / candidate
    run_path,protocol_path,output_path=resolve_score_inputs(candidate,run_json,protocol_json,output_name)
    run = json.loads(run_path.read_text())
    protocol=json.loads(protocol_path.read_text())
    cpu_path=None
    if "cpu_contract_sha256" in protocol:
        matches=[p for p in out.glob("cpu-contract*.json") if digest(p)==protocol["cpu_contract_sha256"]]
        if len(matches)!=1:raise ValueError("selected protocol CPU contract is missing or ambiguous")
        cpu_path=matches[0]
    reliability=None
    if "prior_run_sha256" in protocol:
        cpu=json.loads(cpu_path.read_text())
        if run_path.name!="run-02.json" or run["status"]!="ALL_REQUESTS_COMPLETED" or run["model_loads_started"]!=1 or run["generation_calls_started"]!=100 or len(run["completed"])!=100 or cpu["status"]!="PASS" or len(cpu["requests"])!=100:
            raise ValueError("R514 scoring requires sealed complete 100-request run-02 and CPU contract")
        prior_path=out/"run-01.json"
        if digest(prior_path)!=protocol["prior_run_sha256"]:raise ValueError("prior failure hash mismatch")
        prior=json.loads(prior_path.read_text())
        if (prior["model_loads_started"],prior["generation_calls_started"],len(prior["completed"]))!=(1,1,0):raise ValueError("prior reliability ledger mismatch")
        if (run["cumulative_model_loads_started"],run["cumulative_generation_calls_started"])!=(2,101):raise ValueError("cumulative ledger mismatch")
        for observed,expected in zip(run["completed"],cpu["requests"]):
            if any(observed[k]!=expected[k] for k in ("id","query","mode","stage","repeat")):raise ValueError("run/CPU request order mismatch")
            folder=Path(observed["raw_directory"])
            if folder.parent!=Path(run["raw_directory"]) or folder.parent.name!="run-02":raise ValueError("raw run directory mismatch")
            if json.loads((folder/"processor.json").read_text())!=expected["features"] or digest(folder/"prompt.txt")!=expected["rendered_sha256"]:raise ValueError("processor/prompt contract mismatch")
        reliability={"prior_loads":prior["model_loads_started"],"prior_generation":prior["generation_calls_started"],"prior_completed":len(prior["completed"]),"current_loads":run["model_loads_started"],"current_generation":run["generation_calls_started"],"current_completed":len(run["completed"]),"cumulative_loads":run["cumulative_model_loads_started"],"cumulative_generation":run["cumulative_generation_calls_started"],"cumulative_completed":len(prior["completed"])+len(run["completed"])}
    oracle = json.loads((HERE / "diagnostic/oracle-inputs.json").read_text())
    frozen_schema = HERE.parent / "round491-taichu-constrained-json-20261108/diagnostic/visual-decision-schema.json"
    assert VisualDecision.model_json_schema() == json.loads(frozen_schema.read_text())
    cases = {c["id"]: c for c in oracle["cases"]}
    ground = {}
    for key, case in cases.items():
        arrays = {}
        for name, dtype in [("instance_geom_ids.i32", "<i4"), ("depth.f32", "<f4"), ("valid_mask.u8", "u1")]:
            source = case["files"][name]
            path = ROOT / source["path"]
            assert path.stat().st_size == source["bytes"] and digest(path) == source["sha256"]
            arrays[name] = np.fromfile(path, dtype=dtype)
        ground[key] = arrays
    rows = []
    for request in run["completed"]:
        folder = Path(request["raw_directory"])
        assert digest(folder / "raw-response.txt") == request["raw_response_sha256"]
        assert len(json.loads((folder / "output-token-ids.json").read_text())) == request["output_tokens"]
        case = cases[request["id"]]
        g = ground[request["id"]]
        width, height = case["width"], case["height"]
        labels = {v: int(k) for k, v in case["instance_labels"].items()}

        def assess(point, kind):
            geom_id = labels.get("object_geom" if kind == "target" else "target_region_geom", -999)
            return pixel_assessment(point, g["instance_geom_ids.i32"].tolist(),
                                    g["valid_mask.u8"], g["depth.f32"], width, height, geom_id)

        item = {k: request[k] for k in ["index", "id", "query", "stage", "repeat", "end_to_end_s", "output_tokens", "reached_cap"]}
        item["case_kind"] = case["kind"]
        if request["stage"].startswith("NATIVE"):
            item["modes"] = {}
            for mode, prediction in request["native"].items():
                if not isinstance(prediction, dict) or "status" not in prediction:
                    continue
                pred = dict(prediction)
                point = pred.get("point")
                pred.update(assess(point, request["query"]))
                pred["explicit_no_detection"] = pred["status"] == "REFUSAL" and not pred.get("predictions")
                expected_id = labels.get("object_geom" if request["query"] == "target" else "target_region_geom", -999)
                gt = (g["instance_geom_ids.i32"].reshape(height, width) == expected_id)
                if mode == "box" and pred.get("predictions") and gt.any():
                    ys, xs = np.where(gt)
                    pred["iou"] = box_iou(pred["predictions"][0]["box"], (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
                if mode == "mask" and (folder / "raw-mask-logits.npy").exists() and pred.get("predictions"):
                    logits = np.load(folder / "raw-mask-logits.npy")
                    selected = int(request["native"].get("thought_masks", 0))
                    bitmap, derived = mask_pixel(logits[0, selected], width, height, kind="logit", threshold=0.0)
                    assert derived == (tuple(point) if point is not None else None)
                    bitmap = np.asarray(bitmap, dtype=bool)
                    intersection = int((bitmap & gt).sum())
                    union = int((bitmap | gt).sum())
                    total = int(bitmap.sum() + gt.sum())
                    pred["iou"] = intersection / union if union else 0.0
                    pred["dice"] = 2 * intersection / total if total else 0.0
                item["modes"][mode] = pred
        else:
            text = (folder / "raw-response.txt").read_text()
            try:
                strict_json(text)
                decision = VisualDecision.model_validate_json(text, strict=True)
                item["schema_valid"] = True
                item["decision"] = decision.model_dump(mode="json")
                item["strict_absence"] = decision.target_pixel is None and decision.destination_pixel is None and decision.skills == []
                item["absence_with_confidence_zero"] = item["strict_absence"] and decision.reported_confidence == 0
                item["action_suggestion"] = bool(decision.skills)
                for kind in ("target", "destination"):
                    value = getattr(decision, kind + "_pixel")
                    try:
                        point = point_pixel(value, width, height, "normalized_1000") if value is not None else None
                        item[kind] = {"point": point, "coordinate_valid": True, **assess(point, kind)}
                    except ValueError as error:
                        item[kind] = {"point": None, "coordinate_valid": False, "hit": False, "valid_depth": False, "error": str(error)}
            except (ValueError, TypeError) as error:
                item.update(schema_valid=False, strict_absence=False, action_suggestion=None, error=str(error))
        rows.append(item)
    positive = [c["id"] for c in cases.values() if c["kind"] == "positive"]
    absent = [c["id"] for c in cases.values() if c["kind"] != "positive"]
    assert len(positive) == 12 and len(absent) == 4
    native = [r for r in rows if r["stage"].startswith("NATIVE") and not r["repeat"]]
    modes = sorted({m for r in native for m in r["modes"]})
    summary = {}
    for mode in modes:
        lookup = {(r["id"], r["query"]): r["modes"][mode] for r in native if mode in r["modes"]}
        hit = lambda key, kind: lookup.get((key, kind), {}).get("hit", False)
        summary[mode] = {"positive_n": 12, "target_hits": sum(hit(k, "target") for k in positive),
                         "destination_hits": sum(hit(k, "destination") for k in positive),
                         "joint_hits": sum(hit(k, "target") and hit(k, "destination") for k in positive),
                         "absent_n": 4, "clear_target_absence": sum(lookup.get((k, "target"), {}).get("explicit_no_detection", False) for k in absent),
                         "coverage": len(lookup), "expected_coverage": 32,
                         "invalid_outputs": sum(p.get("status") in ("INVALID", "EMPTY") for p in lookup.values())}
        for metric in ("iou", "dice"):
            for kind in ("target", "destination"):
                values = [lookup.get((k, kind), {}).get(metric, 0.0) for k in positive]
                if any(metric in lookup.get((k, kind), {}) for k in positive):
                    summary[mode][kind + "_mean_" + metric + "_denominator12"] = float(np.mean(values))
        summary[mode]["screening_signal"] = (summary[mode]["joint_hits"] >= 10 and summary[mode]["clear_target_absence"] == 4 and len(lookup) == 32)
    json_summary = {}
    for stage in sorted({r["stage"] for r in rows if r["stage"].startswith("JSON")}):
        group = [r for r in rows if r["stage"] == stage and not r["repeat"]]
        by_id = {r["id"]: r for r in group}
        hit = lambda key, kind: by_id.get(key, {}).get(kind, {}).get("hit", False)
        json_summary[stage] = {"schema_valid": sum(r["schema_valid"] for r in group), "expected_n": 16,
                               "positive_n": 12, "target_hits": sum(hit(k, "target") for k in positive),
                               "destination_hits": sum(hit(k, "destination") for k in positive),
                               "joint_hits": sum(hit(k, "target") and hit(k, "destination") for k in positive),
                               "absent_n": 4, "strict_absence": sum(by_id.get(k, {}).get("strict_absence", False) for k in absent),
                               "absent_action_suggestions": sum(by_id.get(k, {}).get("action_suggestion") is True for k in absent),
                               "latency": stats([r["end_to_end_s"] for r in group])}
    raw = Path(run["raw_directory"])
    memory = []
    memory_path = raw / "gpu-memory-200ms.csv"
    if memory_path.exists():
        for line in memory_path.read_text().splitlines():
            try:
                memory.append(float(line.split(",")[1].strip()))
            except (ValueError, IndexError):
                pass
    result = {"candidate": candidate, "status": "SCORED_DEV16", "run_status": run["status"],
              "protocol_sha256": digest(protocol_path), "run_sha256": digest(run_path),
              "oracle_sha256": digest(HERE / "diagnostic/oracle-inputs.json"), "scorer_sha256": digest(Path(__file__)),
              "model_loads_started": run["model_loads_started"], "generation_calls_started": run["generation_calls_started"],
              "completed_calls": len(rows), "load_s": run.get("load_s"), "native": summary, "json": json_summary,
              "latency": native_latency(rows),
              "gpu": {"torch_peak_allocated_bytes": max((r["torch_peak_allocated_bytes"] for r in run["completed"]), default=0),
                      "torch_peak_reserved_bytes": max((r["torch_peak_reserved_bytes"] for r in run["completed"]), default=0),
                      "device_peak_used_MiB_200ms": max(memory) if memory else None, "samples": len(memory)},
              "cap_reached_calls": sum(r["reached_cap"] for r in rows), "rows": rows,
              "acceptance": "DEVELOPMENT_SCREEN_ONLY_NOT_HELDOUT_OR_PHYSICAL_ACCEPTANCE", "hardware_dispatch": False}
    result["provenance"]={"run_path":str(run_path),"protocol_path":str(protocol_path),"output_name":output_name,"run_bytes":run_path.stat().st_size,"protocol_bytes":protocol_path.stat().st_size,"cpu_contract_path":str(cpu_path) if cpu_path else None,"cpu_contract_sha256":digest(cpu_path) if cpu_path else None,"oracle_path":str(HERE/"diagnostic/oracle-inputs.json"),"helper_sha256":digest(HERE/"implementation/score_native.py")}
    if reliability is not None:result["reliability"]=reliability
    assert digest(run_path)==result["run_sha256"] and digest(protocol_path)==result["protocol_sha256"]
    with output_path.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False, default=_json_scalar)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2, allow_nan=False, default=_json_scalar))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--run-json")
    parser.add_argument("--protocol-json")
    parser.add_argument("--output-name",default="score-03.json")
    args=parser.parse_args()
    score(args.candidate,run_json=args.run_json,protocol_json=args.protocol_json,output_name=args.output_name)
