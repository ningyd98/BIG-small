"""Apply the unchanged preregistered d02 budget to the second radial pixel candidate."""

import importlib.util
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "round-g1-radial-native-timing-20261125"
METHOD = OLD / "native_window_budget.py"
FIT_PLAN = "70d6f895fa88b80d0e5b2415c5cb51b63f39f17abe53252da2eb782be5535c5f"


def calculate():
    spec = importlib.util.spec_from_file_location("frozen_window_budget", METHOD)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    plan_file = HERE / "plan.json"
    prior_file = OLD / "paired-budget.public.json"
    old.require(old.sha(plan_file) == FIT_PLAN, "fit-reuse plan changed")
    plan = old.load(plan_file)
    prior = old.load(prior_file)
    old.require(
        old.sha(METHOD) == "6f1fc4c94dd77813e3910bf444b6a7b3509aa3078d3685f00ca23c09c2bc3ba8"
        and old.sha(prior_file) == plan["failed_budget_sha256"]
        and prior["eligible"] is False,
        "previous calculation, negative qualification or original source changed",
    )
    inputs = HERE / "pixel-timing-samples.public.json.gz"
    summary_path = HERE / "pixel-timing-summary.public.json"
    raw, pixel = old.load(inputs), old.load(summary_path)
    groups = Counter(row["group"] for row in raw["samples"])
    old.require(
        groups
        == {"cycle": plan["hot_cycle"], "neighbors": plan["hot_neighbors"], "cold": plan["cold"]}
        and raw["baseline_generation"] == plan["native_baseline_generation"]
        and pixel["samples_sha256"] == old.sha(inputs),
        "changed sample count, comparison population or source",
    )
    with tempfile.TemporaryDirectory() as tmp:
        direct = Path(tmp) / "unmodified-budget.json"
        detail = HERE / "paired-window-rows.public.json.gz"
        report = old.budget(inputs, detail, direct)
        old.require(
            report == old.load(direct) and report["limits_ms"] == prior["limits_ms"],
            "budget differs from the frozen method",
        )
        report["original_method_result_sha256"] = old.sha(direct)
    report["fit_reuse_plan_sha256"] = FIT_PLAN
    report["prior_failed_budget_sha256"] = old.sha(prior_file)
    report["sample_group_counts"] = dict(groups)
    report["eligible"] = bool(report["eligible"] and pixel["all_warm_pixel_gates"])
    report["input_artifacts_sha256"].update(
        {
            old.rel(p): old.sha(p)
            for p in (Path(__file__).resolve(), plan_file, prior_file, summary_path)
        }
    )
    old.dump(HERE / "paired-budget.public.json", report)
    print(
        {
            k: report[k]
            for k in (
                "eligible",
                "estimated_p95_ms",
                "estimated_max_ms",
                "pixel_p95_ms",
                "pixel_max_ms",
            )
        }
    )


if __name__ == "__main__":
    calculate()
