"""Recompute the graduation evidence matrix and optionally read back a local Harness episode."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUNDS = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
ROUND = ROUNDS / "round-graduation-integration-20261123"
MATRIX = ROUND / "requirements-evidence.public.json"
SOURCES = {
    "proposal": "docs/开题报告_集成电路工程_20261024.md",
    "design": "docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md",
    "component": ROUNDS / "round-p1-hard-limit-prefix-resume-20261120/final-batch-summary.json",
    "teacher": ROUNDS / "round-v10-phase6-20261122/validation.public.json",
    "replay": ROUNDS / "round-v10-phase7-20261123/validation.public.json",
    "baseline_inputs": ROUNDS / "round-p1-development-readiness-20261119/b0/step-report.md",
    "allocation": ROUND / "allocation.public.json",
    "perception": ROUND / "perception.public.json",
    "decisions": ROUND / "decisions.public.json",
    "installation": ROUND / "installation.public.json",
}


def matrix(root: Path) -> dict:
    sources, data = {}, {}
    for key, relative in SOURCES.items():
        raw = (root / relative).read_bytes()
        sources[key] = {"path": str(relative), "sha256": hashlib.sha256(raw).hexdigest()}
        if str(relative).endswith(".json"):
            data[key] = json.loads(raw)
    teacher, replay = data["teacher"], data["replay"]
    audit = teacher["registered_readback"]
    groups = dict(audit["group_scores"])
    unrun = audit["not_run_groups"]
    first = audit["first_group"]
    releases = teacher["registration"]["released_assignments"]
    if (
        releases != [first["assignment_id"]]
        or unrun != sorted(set(groups) - set(releases))
        or teacher["registration"]["claim_count"] != 1
        or teacher["formal_process"]["invocations"] != len(releases)
        or teacher["formal_runs_available_after_collection"] != 0
        or len(groups) != 9
        or any(v is not None for v in groups.values())
        or first["native_qualification"] != "UNKNOWN"
        or replay["historical_registry"]["v10"]["other_not_run"] != len(unrun)
    ):
        raise ValueError("formal group identity, score, or disposition changed")
    dev = data["component"]["development_fresh"]
    views = data["perception"]["holdout_by_view"]
    (held,) = (
        row
        for row in data["perception"]["by_split_and_mode"]
        if row["split"] == "holdout" and row["mode"] == data["perception"]["primary_mode"]
    )
    top = held["errors"]["object_top_center_3d_m"]
    dec, installation = data["decisions"], data["installation"]
    if (
        len(views) != 3
        or sum(v["allocated"] for v in views) != 162
        or sum(v["observed"] for v in views) != top["n"]
        or held["observed"] != top["n"]
        or any(v["observed"] > v["allocated"] or v["observed"] < 0 for v in views)
        or dec["formal_trials"]
        or dec["external_model_requests"]
        or dec["physical_executions"]
    ):
        raise ValueError("held-out allocation or decision scope changed")
    ledger = dec["cost"]["ledger"]["summary"]
    repaired = {
        r["method"]: {
            "rewritten_steps": len(r["actual_replaced_ids"]),
            "completed_nonrepeatable_in_pending": r["completed_nonrepeatable_in_pending"],
        }
        for r in dec["repair"]["paired"]
    }
    counts = {
        "formal_registered": len(groups),
        "formal_attempted": len(releases),
        "formal_qualified": 0,
        "formal_not_run": len(unrun),
        "first_group": first["assignment_id"],
        "first_verdict": first["native_qualification"],
        "first_frames": first["allocated_frames"],
        "first_steps": teacher["collection"]["physics_steps"],
        "component_successes": dev["component_complete"]["successes"],
        "development_poses": dev["assigned"],
        "independent_physical_successes": dev["physical_success"]["successes"],
        "held_out_groups": data["perception"]["holdout_groups"],
        "held_out_frames": held["allocated"],
        "held_out_observed": top["n"],
        "held_out_conditional_p90_mm": 1000 * top["p90"],
        "held_out_maximum_mm": 1000 * top["max"],
        "held_out_views": views,
        "software_repair": repaired,
        "fixture_application_bytes": ledger["application_bytes"],
        "fixture_sent_requests": ledger["model_requests"],
        "installed_package": installation["wheel"]["name"],
        "prepared_actions": installation["executed_actions"],
        "prepared_evidence_files": installation["evidence_files"],
    }

    def row(goal, target, state, observed, required, source):
        return dict(
            goal=goal,
            target=target,
            state=state,
            observed=observed,
            next_evidence=required,
            sources=source,
        )

    gates = [
        row(
            "G0",
            "已发生阶段全链追溯 100%，泄露、伪成功、跨组重复为零",
            "PARTIAL",
            "正式首组保留停止和全部分配帧。软件盲读、篡改和幂等负控另行验收。",
            "完整研究阶段来源与跨组审计",
            ["teacher", "replay", "installation", "decisions"],
        ),
        row(
            "G1",
            "有效且身份正确的物体顶心 3D 误差 P90 ≤10 mm，独立静态抓放 ≥90%",
            "NOT_QUALIFIED",
            "开发格的条件误差与覆盖见 held_out_views，20 个历史开发位姿的独立物理成功 5 次。"
            "正式首组 LIFT 两项 UNKNOWN。",
            "动作参考系、有效误差和采样间运动界，合格独立教师与抓放",
            ["component", "perception", "teacher"],
        ),
        row(
            "G2",
            "请求均值相对 B0 至少减少 30%，成功差单侧95%下界 >−3pp，安全差上界 ≤+1pp",
            "NOT_ESTIMABLE",
            "固定软件输入可比较候选选择。缺正式分层配对样本。",
            "合格 B0 和独立配对试次",
            ["design", "decisions", "baseline_inputs"],
        ),
        row(
            "G2a",
            "应用字节减少 ≥25%，含失败惩罚的任务耗时 P95 减少 ≥15%，分别判定",
            "NOT_ESTIMABLE",
            f"本地软件夹具记录 {ledger['application_bytes']} 应用字节。"
            "正式节省率、账单与差值为空。",
            "同一冻结预算下成对的字节、耗时及失败惩罚",
            ["design", "decisions"],
        ),
        row(
            "G3",
            "相对 B3 误放行减少 ≥50% 且绝对 ≤2%，有效安全机会误拒 ≤5%",
            "NOT_ESTIMABLE",
            "限时、超界和缺界的软件控制均已执行。历史协议固定机会证据为 0。",
            "独立的固定机会与安全标签，UNKNOWN 单列",
            ["decisions", "baseline_inputs"],
        ),
        row(
            "G4",
            "200 故障组恢复 ≥80%，对 B4 的惩罚中位时长减少 ≥30%，完成的不可重复动作重提 0",
            "NOT_ESTIMABLE",
            "开发软件修复的改写步骤见 software_repair。历史可恢复性证明 1/200。",
            "200 个可恢复故障的独立证据及正式配对回放",
            ["decisions", "baseline_inputs"],
        ),
        row(
            "G5",
            "可选，2000 组训练，域外成功提高 ≥5pp",
            "OPTIONAL_NOT_RUN",
            "本轮研究训练与域外比较未运行。",
            "若立项，500/1000/2000 学习曲线加 300 个域外组、3 个训练种子",
            ["design"],
        ),
    ]
    for k, target, obs, src in [
        (
            "B0",
            "0.5/1/2/5 s 周期，静态 ≥90%、总体 ≥80%、安全违规 ≤1%",
            "120 组 selection 未运行",
            "baseline_inputs",
        ),
        ("B1", "固定阈值触发", "无冻结配对样本", "design"),
        ("B2", "同一角色和预算的规则 AUTO", "固定软件成本扰动已复算", "decisions"),
        ("B3", "保留基础身份、时效及 SafetyShield", "与联合门对照的软件用例已执行", "decisions"),
        ("B4", "重规划全部剩余步骤，保护已完成效果及预算", "同图软件对照已执行", "decisions"),
        ("B5", "均匀采样", "正式配对样本待采", "design"),
    ]:
        gates.append(row(k, target, "FORMAL_NOT_RUN", obs, "正式机会集、共用冻结输入和清单", [src]))
    for k, target, required in [
        ("INITIAL", "锁定场景、机会、故障、预算选择与门槛", "合格教师、合格B0，另120组基础先导"),
        ("METHOD", "锁定完整方法、角色、模型、候选和预算", "完成开发调参与可复核的校准"),
        (
            "FINAL",
            "独立功效先导后锁定样本数、资产和执行哈希",
            "另120组功效先导，从600/1200/1800/2400中选择每方法N",
        ),
    ]:
        gates.append(
            row(
                k,
                target,
                "INCOMPLETE",
                "已有分组与阶段登记留存。",
                required,
                ["design", "baseline_inputs"],
            )
        )
    return {
        "schema": "graduation.requirements-evidence.v1",
        "research_date": "2026-11-23",
        "counts": counts,
        "gates": gates,
        "sources": sources,
    }


def live_demo(destination: Path, cli: str, calibration: Path | None) -> None:
    """Use fresh outputs for all replay work and read the published receipts as immutable inputs."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    decisions = destination / "decisions"
    subprocess.run(
        [sys.executable, "-m", "scripts.graduation.decision_replay", "--output", decisions],
        cwd=ROOT,
        check=True,
    )
    if (decisions / "decisions.public.json").read_bytes() != (
        ROOT / SOURCES["decisions"]
    ).read_bytes():
        raise ValueError("decisions replay differs from published result")
    if calibration:
        calibration = calibration.resolve(strict=True)
        published = ROOT / SOURCES["perception"]
        hashes = json.loads(published.read_text())["sha256"]
        regenerated = destination / "perception.public.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.graduation.perception_score",
                "--raw",
                calibration / "raw",
                "--estimates",
                calibration / "estimates",
                "--sensitivity",
                calibration / "sensitivity",
                "--allocation",
                ROOT / SOURCES["allocation"],
                "--allocation-sha256",
                hashes["allocation"],
                "--capture-sha256",
                hashes["capture_seal"],
                "--estimate-sha256",
                hashes["estimation_seal"],
                "--sensitivity-sha256",
                hashes["sensitivity"],
                "--detail",
                destination / "paired-residuals.json",
                "--public",
                regenerated,
            ],
            cwd=ROOT,
            check=True,
        )
        if regenerated.read_bytes() != published.read_bytes():
            raise ValueError("independent vision score differs from the published calibration")
    episode = destination / "episode"
    for name, command in [
        ("prepare", [cli, "prepare", "--source-checkout", ROOT, "--output", episode]),
        ("evidence", [cli, "evidence", episode]),
    ]:
        raw = subprocess.check_output(command, cwd=destination)
        (destination / f"{name}.json").write_bytes(raw)
        stage = json.loads(raw)
        if stage["episode"]["status"] != "PREPARED" or stage["episode"]["executed_actions"] != 0:
            raise ValueError(f"unexpected {name} result")
    print(
        json.dumps(
            {
                "decision_bytes_match": True,
                "calibration_bytes_match": True if calibration else None,
                "new_prepared_episode_verified": True,
                "model_calls": 0,
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-matrix", type=Path, help="save the derived matrix")
    parser.add_argument("--episode", type=Path, help="verify a local Harness evidence directory")
    parser.add_argument("--cli", default="bigsmall-harness", help="installed Harness executable")
    parser.add_argument(
        "--output",
        type=Path,
        help="fresh directory for decision replay and Harness prepare/readback",
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        help="local sealed sensor run for independent scoring with --output",
    )
    args = parser.parse_args()
    if args.calibration and not args.output:
        parser.error("--calibration requires --output")
    out = matrix(ROOT)
    if args.write_matrix:
        args.write_matrix.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    elif out != json.loads((ROOT / MATRIX).read_text()):
        raise ValueError("the published requirements matrix differs from its source records")
    print(json.dumps(out["counts"], ensure_ascii=False, indent=2))
    if args.episode:
        subprocess.run([args.cli, "evidence", str(args.episode.resolve())], check=True)
    if args.output:
        live_demo(args.output, args.cli, args.calibration)


if __name__ == "__main__":
    main()
