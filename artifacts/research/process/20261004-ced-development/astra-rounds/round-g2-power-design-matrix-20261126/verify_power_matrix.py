"""Cold readback of the unexecuted seven-method CED power design."""

import argparse
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.network import NetworkSchedule
from cloud_edge_robot_arm.research.protocol import NETWORKS, STRATA
from cloud_edge_robot_arm.research.resource_plan import METHOD_IDS


def require(predicate, reason):
    if not predicate:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def expected_groups(pools):
    groups, seen = {}, set()
    sizes = dict(selection=120, foundation=120, power=120, formal=2400, recovery=200, ood=300)
    require(set(pools) == set(sizes), "six frozen pools required")
    for name, count in sizes.items():
        require(len(pools[name]) == count, f"wrong count for {name}")
        for index, base in enumerate(pools[name], start=1):
            scene = SceneSpec.model_validate(base["scene"])
            identity = f"{name}-{index:04d}"
            stratum = STRATA[(index - 1) % len(STRATA)]
            require(
                base["assignment_id"] == identity
                and base["stratum_id"] == stratum
                and base["scene_hash"] == scene.scene_hash
                and scene.group_id not in seen,
                f"pool identity, stratum or overlap: {identity}",
            )
            seen.add(scene.group_id)
            if name == "power":
                rtt = int(stratum.split("_RTT")[1])
                schedule = NetworkSchedule(
                    schedule_id=identity,
                    rtt_ms=rtt,
                    loss_rate=dict(NETWORKS)[rtt],
                    seed=scene.seed,
                ).model_dump(mode="json")
                groups[identity + "::METHODS_NOT_INTEGRATED"] = (base, scene, schedule)
    return groups


def verify(output, pools, matrix, summary):
    expected = expected_groups(pools)
    rows = matrix["planned_episodes"]
    assignments = read(output / "assignments.json")
    records = read(output / "results.json")
    pool_hash = content_digest(pools)
    require(
        matrix["schema_version"] == "ced.power-design-matrix.v1"
        and matrix["scope"] == "DESIGN_ONLY"
        and matrix["execution_admitted"] is False
        and matrix["executed_episodes"] == 0
        and matrix["planned_groups"] == 120
        and matrix["planned_method_episodes"] == len(rows) == 840
        and matrix["resource_methods"] == list(METHOD_IDS)
        and matrix["statistical_pair_methods"] == ["B0", "JOINT"]
        and matrix["power_group_manifest_hash"] == content_digest(assignments),
        "incorrect design envelope",
    )
    require(
        summary["power_design_matrix_hash"] == content_digest(matrix)
        and summary["assignment_manifest_hash"] == content_digest(assignments)
        and summary["pools_hash"] == pool_hash
        and summary["stage"] == "power"
        and summary["planned_groups"] == 120
        and summary["planned_method_episodes"] == 840
        and summary["assigned_denominator"] is None
        and summary["recorded_denominator"] == 120
        and summary["actual_research_status"] == "NOT_RUN"
        and summary["execution_mode"] == "NOT_EXECUTED"
        and summary["method_runtime_integrated"] is False
        and summary["executed_episodes"] == summary["accepted_success"] == 0
        and summary["freeze_ready"] is False
        and summary["selected_period_s"] is None
        and summary["terminal_status_counts"] == {"NOT_EXECUTED": 120},
        "design was misrepresented as actual research",
    )
    for dataset in (assignments, records):
        require(
            Counter(row["assignment_id"] for row in dataset) == Counter(expected.keys()),
            "one source record per original power group required",
        )
    require(
        {item.name for item in (output / "cases").iterdir()} == expected.keys(),
        "unexpected actual case directories",
    )
    for row in assignments:
        identity = row["assignment_id"]
        base, scene, schedule = expected[identity]
        require(
            row["stage"] == "power"
            and row["base_assignment"] == base
            and row["scene_hash"] == scene.scene_hash
            and row["group_id"] == scene.group_id
            and row["stratum_id"] == base["stratum_id"]
            and row["physics_seed"] == scene.seed
            and row["network_schedule"] == schedule
            and row["pools_hash"] == pool_hash
            and row["period_s"] is row["role_bundle_hash"] is None
            and row == read(output / "cases" / identity / "assignment.json"),
            f"source group drift: {identity}",
        )
    for row in records:
        identity = row["assignment_id"]
        require(
            row["status"] == "NOT_EXECUTED"
            and row["cloud_requests"] == 0
            and row["accepted_success"] is False
            and row["wall_duration_s"] == 0
            and row == read(output / "cases" / identity / "case-result.json"),
            f"unexpected execution record: {identity}",
        )
    pair_coverage = Counter()
    for row in rows:
        identity, method = row["group_assignment_id"], row["method_id"]
        require(identity in expected, f"foreign power design group: {identity}")
        base, scene, schedule = expected[identity]
        require(
            method in METHOD_IDS
            and row["planned_episode_id"] == f"{base['assignment_id']}::{method}"
            and row["base_assignment"] == base
            and row["group_id"] == scene.group_id
            and row["scene_hash"] == scene.scene_hash
            and row["stratum_id"] == base["stratum_id"]
            and row["physics_seed"] == scene.seed
            and row["network_schedule"] == schedule
            and row["pools_hash"] == pool_hash
            and row["role_bundle_hash"] is row["method_hash"] is row["b0_period_s"] is None,
            f"planned episode changed its registered inputs: {identity}, {method}",
        )
        pair_coverage[identity, method] += 1
    require(
        pair_coverage
        == Counter((identity, method) for identity in expected for method in METHOD_IDS),
        "an original group has missing or repeated method episodes",
    )
    strata = Counter(base["stratum_id"] for base, _, _ in expected.values())
    require(strata == Counter({name: 10 for name in STRATA}), "power strata are unbalanced")
    paired_rows = sum(
        count for (_, method), count in pair_coverage.items() if method in {"B0", "JOINT"}
    )
    return {
        "groups": len(expected),
        "episodes": len(rows),
        "statistical_projection_rows": paired_rows,
        "statistical_projection_groups": len(expected),
        "strata": dict(strata),
    }


def controls(output, pools, matrix, summary):
    accepted = []
    for scenario in (
        "two_methods",
        "duplicate",
        "changed_network_seed",
        "selection_injection",
        "claims_actual_execution",
    ):
        mutant = deepcopy(matrix)
        rows = mutant["planned_episodes"]
        if scenario == "two_methods":
            rows[:] = [row for row in rows if row["method_id"] in {"B0", "JOINT"}]
            mutant["planned_method_episodes"] = len(rows)
        elif scenario == "duplicate":
            rows[1] = deepcopy(rows[0])
        elif scenario == "changed_network_seed":
            rows[1]["network_schedule"]["seed"] += 1
        elif scenario == "selection_injection":
            rows[1]["group_assignment_id"] = "selection-0001::METHODS_NOT_INTEGRATED"
        else:
            mutant["execution_admitted"] = True
            mutant["executed_episodes"] = 840
        stamped = {**summary, "power_design_matrix_hash": content_digest(mutant)}
        try:
            verify(output, pools, mutant, stamped)
        except ValueError as error:
            accepted.append({"fixture": scenario, "rejected": str(error)})
        else:
            raise ValueError(f"negative control accepted: {scenario}")
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("frozen_pools", type=Path)
    args = parser.parse_args()
    source = args.frozen_pools.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    require(
        source_sha == "e86ac4858fffb0040301c38a0481da7261bece6070e3531cfe9fc2e863c10618",
        "original six-pool bytes changed",
    )
    pools = json.loads(source)
    require(read(args.output / "pools.json") == pools, "CLI pool copy differs from frozen source")
    matrix = read(args.output / "power-design-matrix.json")
    summary = read(args.output / "summary.json")
    report = verify(args.output, pools, matrix, summary)
    report["frozen_pool_file_sha256"] = source_sha
    report["negative_controls"] = controls(args.output, pools, matrix, summary)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
