"""根据重放一致性和带单位的关节证据分析A/B/C，不强行归类。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def classify(diagnostics, verification):
    """只有复现原实验且有对应证据时才支持假设。"""
    unknown = {key: "UNDETERMINED" for key in "ABC"}
    try:
        digest = hashlib.sha256(
            json.dumps(diagnostics, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        rows = diagnostics["violations"]
        steps = [row["physics_step"] for row in rows]
        coverage = verification.get("online_guard_coverage")
        joint_records_valid = all(
            isinstance(row.get("violated_joints"), list)
            and row["violated_joints"]
            and all(
                isinstance(joint, dict)
                and type(joint.get("index")) is int
                and 0 <= joint["index"] < 9
                and joint.get("type") == ("arm" if joint["index"] < 7 else "finger")
                and joint.get("unit") == ("rad" if joint["index"] < 7 else "m")
                and isinstance(joint.get("violation_magnitude"), (int, float))
                and joint["violation_magnitude"] > 1e-4
                for joint in row["violated_joints"]
            )
            for row in rows
        )
        valid = (
            verification.get("replay_matches_original") is True
            and verification.get("original_evidence_unchanged") is True
            and verification.get("diagnostic_file_hash_matches") is True
            and verification.get("diagnostic_errors") == []
            and isinstance(coverage, list)
            and bool(coverage)
            and all(kind in ("arm", "finger") for kind in coverage)
            and joint_records_valid
            and digest == verification.get("diagnostic_content_sha256")
            and diagnostics.get("schema") == "joint-limit-diagnostics.v1"
            and diagnostics.get("source_case") == verification["case"]
            and diagnostics.get("episode_id") == verification["replay_episode_id"]
            and diagnostics.get("original_episode_id") == verification["original_episode_id"]
            and bool(steps)
            and all(type(step) is int and step >= 0 for step in steps)
            and steps == sorted(set(steps))
            and steps == verification["original_flagged_steps"]
            and steps == verification["replayed_flagged_steps"]
            and all(row.get("online_guard_result") == "PASS" for row in rows)
        )
    except (ValueError, TypeError, KeyError):
        return unknown
    if not valid:
        return unknown
    joints = [joint for row in diagnostics["violations"] for joint in row["violated_joints"]]
    fingers = any(joint["type"] == "finger" for joint in joints)
    arms = any(joint["type"] == "arm" for joint in joints)
    a = (
        "SUPPORTED"
        if fingers and "finger" not in verification["online_guard_coverage"]
        else "NOT_OBSERVED"
    )
    # Joint excursion alone, even above 1e-3, cannot prove an unreachable target.
    return {"A": a, "B": "UNDETERMINED" if arms else "NOT_OBSERVED", "C": "UNDETERMINED"}


def main():
    """读取三样本诊断并在同一新输出根目录生成报告。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic_root", type=Path)
    args = parser.parse_args()
    root = args.diagnostic_root
    rows = []
    details = []
    lines = [
        "# 三样本硬限位诊断报告",
        "",
        "范围：仅离线重放诊断，不修改控制器、评价判据或数据类，不构成修复验收。",
        "",
        "| 样本 | 违规物理步 | 机械臂关节事件 | 手指关节事件 | 最大手指越界 m | A | B | C |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for case in ("development-043003", "held-out-044009", "held-out-044011"):
        diagnostic_path = root / case / "component/joint-limit-diagnostics.json"
        verification = json.loads((root / case / "replay-verification.json").read_text())
        input_error = None
        try:
            raw = diagnostic_path.read_bytes()
            diagnostics = json.loads(raw)
            if not isinstance(diagnostics, dict) or not isinstance(
                diagnostics.get("violations"), list
            ):
                raise ValueError("invalid diagnostic structure")
            verification["diagnostic_file_hash_matches"] = hashlib.sha256(
                raw
            ).hexdigest() == verification.get("diagnostic_file_sha256")
        except (ValueError, OSError) as error:
            input_error = str(error)
            diagnostics = {"violations": []}
            verification["diagnostic_file_hash_matches"] = False
        hypothesis = classify(diagnostics, verification)
        if all(value == "UNDETERMINED" for value in hypothesis.values()):
            input_error = input_error or "diagnostic identity, content or coverage not verified"
            diagnostics = {"violations": []}
        counts = Counter()
        by_joint = {}
        magnitudes = {"arm": [], "finger": []}
        positions = {}
        for row in diagnostics["violations"]:
            for joint in row["violated_joints"]:
                counts[joint["type"]] += 1
                magnitudes[joint["type"]].append(joint["violation_magnitude"])
                positions.setdefault(str(joint["index"]), []).append(joint["position"])
                entry = by_joint.setdefault(
                    joint["index"],
                    {
                        "name": verification["joint_mapping"][joint["index"]]["name"],
                        "unit": joint["unit"],
                        "lower_bound": joint["lower_bound"],
                        "upper_bound": joint["upper_bound"],
                        "events": 0,
                        "max_excursion": 0.0,
                    },
                )
                entry["events"] += 1
                entry["max_excursion"] = max(entry["max_excursion"], joint["violation_magnitude"])
        result = {
            "diagnostic_input_error": input_error,
            "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "case": case,
            "violation_steps": len(diagnostics["violations"]),
            "joint_event_counts": dict(counts),
            "hypotheses": hypothesis,
            "max_arm_excursion_rad": max(magnitudes["arm"], default=None),
            "max_finger_excursion_m": max(magnitudes["finger"], default=None),
            "joint_position_ranges": {
                name: [min(values), max(values)] for name, values in positions.items()
            },
            "replay_matches_original": verification["replay_matches_original"],
            "violated_joint_details": by_joint,
            "finger_control_targets_m": sorted(
                {tuple(row["control_targets"][7:9]) for row in diagnostics["violations"]}
            ),
            "online_guard_results_at_violations": dict(
                Counter(
                    row.get("online_guard_result", "UNRECORDED")
                    for row in diagnostics["violations"]
                )
            ),
        }
        rows.append(result)
        maximum = result["max_finger_excursion_m"]
        lines.append(
            f"| {case} | {result['violation_steps']} | {counts['arm']} | {counts['finger']} | "
            f"{maximum if maximum is not None else 'UNKNOWN'} | "
            f"{hypothesis['A']} | {hypothesis['B']} | {hypothesis['C']} |"
        )
        details += [
            "",
            f"### {case}",
            "",
            f"物理步数{result['violation_steps']}，关节事件数{sum(counts.values())}；"
            "同一步两只手指可同时越界，两者不可混作样本数。",
            "",
        ]
        for joint in by_joint.values():
            details.append(
                f"- {joint['name']}：{joint['events']}个关节事件，"
                f"上下界[{joint['lower_bound']}, {joint['upper_bound']}] {joint['unit']}，"
                f"最大超过物理边界{joint['max_excursion']:.12g} {joint['unit']}。"
            )
        details.append("")
        details.append(f"违规步在线检查结果：{result['online_guard_results_at_violations']}。")
        details.append(f"违规步手指控制目标m：{result['finger_control_targets_m']}。")
    lines += [
        "",
        "## 本轮结论",
        "",
        "三项逐步复现后，若均仅有手指违规且原在线检查均通过，则支持假设A："
        "手指超行程没有进入在线硬状态检查。具体关节、原始位置和速度见逐样本诊断文件。",
        "这是对漏检机制的定位，不等同于已解释手指超行程的动力学成因。"
        "当前未实施限位修复，失抓与先前手指越界的因果关系仍未确认。",
        *details,
    ]
    lines += [
        "",
        "## 证据边界",
        "",
        "每个样本的replay-verification.json比较全部历史物理字段（仅新episode_id不同）、控制器返回步、逐项动作边界和违规步集合。重放不一致时，A/B/C均保留UNDETERMINED。",
        (
            "在线原检查覆盖七个机械臂关节，位置容差1e-6 rad；独立评价还检查两个手指关节，"
            "容差分别为1e-4 rad和1e-4 m。诊断原始值保留单位，不能把米与弧度混用。"
        ),
        "A描述在线手指覆盖缺口；它本身不说明手指物理越界的动力学成因。B需真实映射或边界差异证据；C需要目标/轨迹分析，不能仅凭幅度超过1e-3推断。",
        "",
        "## 下一轮修复输入",
        "",
        "先核对违规关节的上下界、控制目标和接触状态，区分软约束响应与控制目标越界；再设计包含手指行程的在线监测与停止策略。任何容差调整需物理依据和正负例验证，不修改原始评价来追求通过。",
        (
            "现有控制器、PhysicsStepObservation、PhysicalSample和episode_evaluator保持原样。"
            "原始40项结果不因诊断重放改写，正式验收仍为NOT_ACCEPTED。"
        ),
        "",
    ]
    (root / "root-cause-analysis.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    (root / "root-cause-analysis.md").write_text("\n".join(lines))
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
