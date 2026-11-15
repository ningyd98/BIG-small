"""核对分片、实际逐节点回执和源码绑定，保留失败与未完成节点。"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def digest(path: Path) -> str:
    """计算原始文件摘要，不改写输入。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run: Path, collection: Path, plugin: Path) -> dict:
    """独立检查完整分区及实际运行结果；失败不是通过，缺回执不是完成。"""
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert digest(collection) == manifest["collection_log_sha256"]
    assert digest(plugin) == manifest["plugin_sha256"]
    collected = [
        line for line in collection.read_text().splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    assert len(collected) == len(set(collected)) == manifest["total"]
    sources = None
    all_nodes = []
    parts = []
    failures = []
    skips = []
    files = [manifest_path, collection, plugin]
    for part in manifest["parts"]:
        index = part["shard"]
        spec_path = run / f"shard-{index}.spec.json"
        nodes_path = run / f"shard-{index}.nodes.txt"
        assert digest(spec_path) == part["spec_sha256"]
        assert digest(nodes_path) == part["nodes_sha256"]
        spec = json.loads(spec_path.read_text())
        nodes = nodes_path.read_text().splitlines()
        assert nodes == spec["nodes"] and len(nodes) == part["nodes"]
        assert len(spec["sources"]) == manifest["source_count"]
        if sources is None:
            sources = spec["sources"]
        assert sources == spec["sources"]
        all_nodes.extend(nodes)
        files.extend((spec_path, nodes_path))
        receipt_path = run / f"shard-{index}.receipt.json"
        journal_path = run / f"shard-{index}.receipt.events.jsonl"
        if not receipt_path.is_file():
            parts.append({"shard": index, "receipt_missing": True,
                          "counts": {"unfinished": len(nodes)}})
            continue
        receipt = json.loads(receipt_path.read_text())
        assert receipt["spec_sha256"] == digest(spec_path)
        assert receipt["expected_nodes"] == receipt["collected_nodes"] == nodes
        assert receipt["source_file_count"] == len(sources)
        assert receipt["source_postcheck_errors"] == []
        events = [json.loads(line) for line in journal_path.read_text().splitlines()]
        assert events[0] == {"event": "SESSION_STARTED", "shard": index}
        assert events[1:] == receipt["reports"]
        by_node = {node: {} for node in nodes}
        for report in receipt["reports"]:
            phase = report["phase"]
            phases = by_node[report["nodeid"]]
            assert phase not in phases
            phases[phase] = report
            if report["outcome"] == "failed":
                failures.append({"shard": index, **report})
            if report["outcome"] == "skipped":
                skips.append({"shard": index, **report})
        counts = Counter()
        for phases in by_node.values():
            if any(r["outcome"] == "failed" for p, r in phases.items() if p != "call"):
                counts["error"] += 1
            elif phases.get("call", {}).get("outcome") == "failed":
                counts["failed"] += 1
            elif any(r["outcome"] == "skipped" for r in phases.values()):
                counts["skipped"] += 1
            elif all(phases.get(p, {}).get("outcome") == "passed"
                     for p in ("setup", "call", "teardown")):
                counts["passed"] += 1
            else:
                counts["unfinished"] += 1
        assert sum(counts.values()) == len(nodes)
        if not counts["unfinished"]:
            assert receipt["exit_code"] == (1 if counts["failed"] or counts["error"] else 0)
        xml_path = run / f"shard-{index}.xml"
        tests = list(ET.parse(xml_path).getroot().iter("testcase"))
        xml_counts = Counter()
        for test in tests:
            outcome = next((key for key in ("error", "failure", "skipped")
                            if test.find(key) is not None), "passed")
            xml_counts[{"failure": "failed"}.get(outcome, outcome)] += 1
        if not counts["unfinished"]:
            assert dict(xml_counts) == dict(counts)
            xml_unfinished_entries = 0
        else:
            # pytest 中断时会为仅完成 setup 的节点输出无 failure 的 testcase；
            # 这些 XML 条目不能越过逐阶段日志而计作 passed。
            for outcome in ("error", "failed", "skipped"):
                assert xml_counts[outcome] == counts[outcome]
            xml_unfinished_entries = xml_counts["passed"] - counts["passed"]
            started_incomplete = sum(
                bool(phases) and not all(phases.get(p, {}).get("outcome") == "passed"
                                         for p in ("setup", "call", "teardown"))
                and not any(r["outcome"] in {"failed", "skipped"} for r in phases.values())
                for phases in by_node.values()
            )
            assert 0 <= xml_unfinished_entries <= started_incomplete
        files.extend((receipt_path, journal_path, xml_path))
        parts.append({"shard": index, "exit_code": receipt["exit_code"],
                      "counts": dict(counts), "elapsed_s": receipt["elapsed_s"],
                      "junit_unfinished_entries_not_counted_as_passed": xml_unfinished_entries,
                      "source_postcheck_errors": receipt["source_postcheck_errors"]})
    assert len(all_nodes) == len(set(all_nodes)) == len(collected)
    assert set(all_nodes) == set(collected)
    totals = Counter()
    for part in parts:
        totals.update(part["counts"])
    assert sum(totals.values()) == manifest["total"]
    complete = not totals["unfinished"] and all(not p.get("receipt_missing") for p in parts)
    passed = complete and not totals["failed"] and not totals["error"]
    return {
        "scope": "SOFTWARE_EXACT_COMPLETE_NODE_PARTITION_VERIFICATION",
        "source_commit_before_uncommitted_changes": "7c326c1d141f81723042bfcb9e1471bc31d4c7a8",
        "manifest_sha256": digest(manifest_path), "source_count": len(sources),
        "exact_nonoverlapping_partition": True, "all_nodes_completed": complete,
        "all_tests_passed_or_skipped": passed, "single_process_full_suite": False,
        "totals": dict(totals), "parts": parts, "failures": failures, "skips": skips,
        "evidence_files": [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p)}
                           for p in files],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("collection", type=Path)
    parser.add_argument("plugin", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.run, args.collection, args.plugin)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("all_nodes_completed", "all_tests_passed_or_skipped", "totals")}))
