"""Offline R505 scoring; oracle files are never imported by model runners."""
import argparse
import hashlib
import json
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


def stats(values):
    return {"n": len(values), "p50_s": float(np.percentile(values, 50)) if values else None,
            "p90_s": float(np.percentile(values, 90)) if values else None}


def score(candidate):
    out = HERE / "candidates" / candidate
    run = json.loads((out / "run-01.json").read_text())
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
        lookup = {(r["id"], r["query"]): r["modes"].get(mode, {}) for r in native}
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
              "protocol_sha256": digest(out / "protocol.json"), "run_sha256": digest(out / "run-01.json"),
              "oracle_sha256": digest(HERE / "diagnostic/oracle-inputs.json"), "scorer_sha256": digest(Path(__file__)),
              "model_loads_started": run["model_loads_started"], "generation_calls_started": run["generation_calls_started"],
              "completed_calls": len(rows), "load_s": run.get("load_s"), "native": summary, "json": json_summary,
              "latency": {"native_cold_first_request_s": native[0]["end_to_end_s"] if native else None,
                          "native_warm_excluding_first": stats([r["end_to_end_s"] for r in native[1:]]),
                          "native_fixed_repetitions": stats([r["end_to_end_s"] for r in rows if r["repeat"]])},
              "gpu": {"torch_peak_allocated_bytes": max((r["torch_peak_allocated_bytes"] for r in run["completed"]), default=0),
                      "torch_peak_reserved_bytes": max((r["torch_peak_reserved_bytes"] for r in run["completed"]), default=0),
                      "device_peak_used_MiB_200ms": max(memory) if memory else None, "samples": len(memory)},
              "cap_reached_calls": sum(r["reached_cap"] for r in rows), "rows": rows,
              "acceptance": "DEVELOPMENT_SCREEN_ONLY_NOT_HELDOUT_OR_PHYSICAL_ACCEPTANCE", "hardware_dispatch": False}
    with (out / "score-01.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    score(parser.parse_args().candidate)
