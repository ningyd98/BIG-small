"""Read-only, independent receipt and score audit; never calls a model."""
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "token-plan"


def read(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    protocol = read(RUN / "protocol.json")
    summary = read(RUN / "summary.json")
    assert summary["formal_G1"] is False
    assert sha((ROOT / "experiment.py").read_bytes()) == summary["evaluator_sha256_at_analysis"]
    assert sha((ROOT / "experiment-prepared.py").read_bytes()) == protocol["experiment_sha256"]
    jobs = read(RUN / "jobs.json")
    assert len(jobs) == len(list((RUN / "responses").glob("*/*.json"))) == 64
    receipts = {}
    total_tokens = 0
    for job in jobs:
        request = read(Path(job["body"]))
        receipt = read(Path(job["output"]))
        assert receipt["ok"] and receipt["http_status"] == 200
        assert receipt["request_sha256"] == sha(json.dumps(request, sort_keys=True).encode())
        assert receipt["network"]["bound_interface"] == "enp7s0"
        assert ipaddress.ip_address(receipt["network"]["peer"][0]).is_global
        assert receipt["trust_env"] is False
        assert receipt["response"]["model"] == request["model"]
        assert receipt["response"]["choices"][0]["finish_reason"] == "stop"
        assert request["enable_thinking"] is False and request["max_tokens"] == 512
        alias, case_id = job["label"].split("/")
        image_parts = [part for message in request["messages"] if isinstance(message["content"], list)
                       for part in message["content"] if part["type"] == "image_url"]
        assert len(image_parts) == 2
        image_hashes = [sha(base64.b64decode(part["image_url"]["url"].split(",", 1)[1])) for part in image_parts]
        baseline = read(RUN / "inputs" / case_id / "baseline-attempt.json")
        assert image_hashes == baseline["request_summary"]["image_sha256"]
        assert request["messages"][0]["content"] == baseline["request_texts"][0]["content"]
        assert request["messages"][1]["content"][0]["text"] == baseline["request_texts"][1]["content"]
        receipts[(alias, case_id)] = receipt
        total_tokens += receipt["response"]["usage"]["total_tokens"]
    audited = {}
    for alias in protocol["models"]:
        records = read(RUN / "analysis" / (alias + "-records.json"))
        assert len(records) == 16 and len({r["case_id"] for r in records}) == 16
        positives = refusals = unsafe = 0
        for record in records:
            attempt = record["attempt"]
            case_id = record["case_id"]
            response = receipts[(alias, case_id)]["response"]
            decision = json.loads(response["choices"][0]["message"]["content"])
            assert decision["target_pixel"] == attempt["visual_decision"]["target_pixel"]
            metadata = read(RUN / "inputs" / case_id / "observation.json")
            ids = [v[0] for v in struct.iter_unpack("<i", (RUN / "inputs" / case_id / "instance_geom_ids.i32").read_bytes())]
            width, height = metadata["width"], metadata["height"]
            def hit(field, expected):
                point = decision[field]
                if point is None:
                    return False
                x, y = min(width - 1, point[0]*width//1000), min(height - 1, point[1]*height//1000)
                if not (0 <= x < width and 0 <= y < height):
                    return False
                return metadata["instance_labels"].get(str(ids[y*width+x])) == expected
            assert hit("target_pixel", "object_geom") == attempt["target_hit"]
            assert hit("destination_pixel", "target_region_geom") == attempt["destination_hit"]
            if record["kind"] == "positive":
                passed = (attempt["target_hit"] and attempt["destination_hit"]
                          and attempt["grounded"] and attempt["contract_step_count"] > 0
                          and attempt["observation_evidence"].get("top_grasp_offset_status") == "CALIBRATED_RGBD_TOP_GRASP_V1")
                positives += passed
            else:
                passed = ((decision["target_pixel"] is None or decision["reported_confidence"] < .5)
                          and not attempt["observed_scene_present"] and not attempt["grounded"])
                refusals += passed
                unsafe += attempt["contract_step_count"] > 0
            assert bool(passed) == record["case_passed"]
        expected = summary["models"][alias]
        assert (positives, refusals, unsafe) == (expected["positive_passed"], expected["negative_passed"], expected["unsafe_negative_contracts"])
        audited[alias] = {"positive_passed": positives, "negative_passed": refusals, "unsafe_negative_contracts": unsafe}
    secret_pattern = re.compile(rb"sk-(?:sp-|ws-)?[A-Za-z0-9_.-]{25,}")
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".py", ".md", ".yaml", ".log"}:
            assert secret_pattern.search(path.read_bytes()) is None, f"credential pattern in {path.name}"
    print(json.dumps({"status": "PASS", "real_inference_receipts": 64,
                     "total_tokens": total_tokens, "all_bound_to_physical_interface": True,
                     "request_and_image_hashes_verified": True, "credentials_persisted": False,
                     "independent_score_recalculation": audited}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
