"""合并相同来源的真实分片回执；补充覆盖不能抹去失败或冒充原长项通过。"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def sha(path: Path) -> str:
    """对原始证据字节取摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outcomes(nodes: list[str], reports: list[dict]) -> dict[str, str]:
    """要求完整逐阶段通过；setup 留下的 XML 空条目不计通过。"""
    by_node = {node: {} for node in nodes}
    for report in reports:
        phases = by_node[report["nodeid"]]
        assert report["phase"] not in phases
        phases[report["phase"]] = report
    result = {}
    for node, phases in by_node.items():
        if any(r["outcome"] == "failed" for p, r in phases.items() if p != "call"):
            state = "error"
        elif phases.get("call", {}).get("outcome") == "failed":
            state = "failed"
        elif any(r["outcome"] == "skipped" for r in phases.values()):
            state = "skipped"
        elif all(
            phases.get(p, {}).get("outcome") == "passed" for p in ("setup", "call", "teardown")
        ):
            state = "passed"
        else:
            state = "unfinished"
        result[node] = state
    return result


def merge(master: Path, supplements: list[Path], collection: Path, plugin: Path) -> dict:
    """只合并同一准确来源版本；原始失败、跳过与未完成尝试全部保留。"""
    initial = json.loads((master / "manifest.json").read_text())
    assert sha(collection) == initial["collection_log_sha256"]
    assert sha(plugin) == initial["plugin_sha256"]
    original_nodes = [
        line
        for line in collection.read_text().splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    assert len(original_nodes) == len(set(original_nodes)) == initial["total"]
    source_rows = json.loads((master / "shard-0.spec.json").read_text())["sources"]
    assert len(source_rows) == initial["source_count"]
    all_attempts = {node: [] for node in original_nodes}
    parts, evidence, failures, skips = [], [], [], []
    original_partition = []
    for run in [master, *supplements]:
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["plugin_sha256"] == initial["plugin_sha256"]
        if run != master:
            assert manifest["root_source_manifest_sha256"] == sha(master / "manifest.json")
        evidence.append(manifest_path)
        for part in manifest["parts"]:
            index = part["shard"]
            spec_path = run / f"shard-{index}.spec.json"
            node_path = run / f"shard-{index}.nodes.txt"
            assert sha(spec_path) == part["spec_sha256"]
            assert sha(node_path) == part["nodes_sha256"]
            spec = json.loads(spec_path.read_text())
            nodes = node_path.read_text().splitlines()
            assert nodes == spec["nodes"] and len(nodes) == len(set(nodes)) == part["nodes"]
            assert set(nodes) <= set(original_nodes)
            assert spec["sources"] == source_rows
            if run == master:
                original_partition.extend(nodes)
            evidence.extend((spec_path, node_path))
            receipt_path = run / f"shard-{index}.receipt.json"
            assert receipt_path.is_file(), f"Missing final receipt: {receipt_path}"
            receipt = json.loads(receipt_path.read_text())
            assert receipt["spec_sha256"] == sha(spec_path)
            assert receipt["expected_nodes"] == receipt["collected_nodes"] == nodes
            assert receipt["source_postcheck_errors"] == []
            assert receipt["source_file_count"] == len(source_rows)
            journal_path = run / f"shard-{index}.receipt.events.jsonl"
            events = [json.loads(line) for line in journal_path.read_text().splitlines()]
            assert events[0] == {"event": "SESSION_STARTED", "shard": index}
            assert events[1:] == receipt["reports"]
            states = outcomes(nodes, receipt["reports"])
            counts = Counter(states.values())
            xml_path = run / f"shard-{index}.xml"
            xml_counts = Counter()
            for test in ET.parse(xml_path).getroot().iter("testcase"):
                state = next(
                    (key for key in ("error", "failure", "skipped") if test.find(key) is not None),
                    "passed",
                )
                xml_counts[{"failure": "failed"}.get(state, state)] += 1
            for state in ("failed", "error", "skipped"):
                assert xml_counts[state] == counts[state]
            extra = xml_counts["passed"] - counts["passed"]
            assert 0 <= extra <= counts["unfinished"]
            if not counts["unfinished"]:
                assert extra == 0
                assert receipt["exit_code"] == (1 if counts["failed"] or counts["error"] else 0)
            parts.append(
                {
                    "directory": str(run),
                    "shard": index,
                    "counts": dict(counts),
                    "exit_code": receipt["exit_code"],
                    "elapsed_s": receipt["elapsed_s"],
                    "junit_unfinished_entries_not_counted_as_passed": extra,
                    "source_postcheck_errors": [],
                }
            )
            for node, state in states.items():
                all_attempts[node].append({"shard": index, "state": state})
            for report in receipt["reports"]:
                if report["outcome"] == "failed":
                    failures.append({"shard": index, **report})
                elif report["outcome"] == "skipped":
                    skips.append({"shard": index, **report})
            evidence.extend((receipt_path, journal_path, xml_path))
    assert len(original_partition) == len(set(original_partition)) == len(original_nodes)
    assert set(original_partition) == set(original_nodes)
    counts = Counter()
    missing, duplicate_completed = [], []
    for node, attempts in all_attempts.items():
        states = [attempt["state"] for attempt in attempts]
        state = next(
            (state for state in ("error", "failed", "passed", "skipped") if state in states),
            "unfinished",
        )
        counts[state] += 1
        if state == "unfinished":
            missing.append(node)
        if sum(value != "unfinished" for value in states) > 1:
            duplicate_completed.append({"nodeid": node, "attempts": attempts})
    assert sum(counts.values()) == len(original_nodes)
    return {
        "scope": "SOFTWARE_SAME_SOURCE_NODE_COVERAGE_WITH_INDEPENDENT_SUPPLEMENTS",
        "total_nodes": len(original_nodes),
        "source_count": len(source_rows),
        "original_partition_exact_and_nonoverlapping": True,
        "same_sources_across_all_runs": True,
        "all_nodes_completed": not counts["unfinished"],
        "all_passed_or_skipped": not (counts["unfinished"] or counts["error"] or counts["failed"]),
        "single_process_full_suite": False,
        "totals": dict(counts),
        "parts": parts,
        "unfinished_nodes": missing,
        "failures": failures,
        "skips": skips,
        "duplicate_completed_attempts": duplicate_completed,
        "evidence_files": [
            {"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in [collection, plugin, *evidence]
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master", type=Path)
    parser.add_argument("collection", type=Path)
    parser.add_argument("plugin", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--supplement", action="append", type=Path, default=[])
    args = parser.parse_args()
    result = merge(args.master, args.supplement, args.collection, args.plugin)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("totals", "all_nodes_completed")}))
