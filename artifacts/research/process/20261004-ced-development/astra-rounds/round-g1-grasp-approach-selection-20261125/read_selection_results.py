"""Check the cast of mechanical and optical evidence for every preregistered placement."""

import argparse
from collections import Counter
from pathlib import Path

import physics_selection_model as selection
import physics_selection_study as study

FREEZE = "8c5382db250d76e7462e176bd774f82f6ff09e4bfeb244aa5b5666f40bd229c2"
NOMINAL = "h10_t+0"


def verified_read(path, sha, catalog):
    digest = study.sha(path)
    if sha is not None and sha != digest:
        raise ValueError(f"sealed candidate evidence differs at {path}")
    catalog[path] = digest
    return study.read(path)


def one(root, label, bank, fit, catalog):
    raw = root / study.RAW
    prefix = raw / "prefix" / label
    decision_path = prefix / "decision.json"
    decision = verified_read(decision_path, None, catalog)
    assert decision["freeze_sha256"] == FREEZE and decision["externally_authorized"] is False
    fields = verified_read(
        prefix / "measured-input.json", decision["measured_input_sha256"], catalog
    )
    replay = selection.predict(bank, fields["features"])
    assert all(decision[k] == v for k, v in replay.items())
    checked = {}
    for candidate in bank["candidate_ids"]:
        course = raw / "courses" / label / candidate / "result.json"
        original = verified_read(course, None, catalog)
        owner = raw / "owner-registered-physics" / "labels" / label / (candidate + ".json")
        owned = verified_read(owner, None, catalog)
        assert catalog[course] == owned["prior_sha256"]
        if owned["actual_suffix"]:
            path = raw / "owner-registered-physics" / "courses" / label / candidate / "result.json"
            verified_read(path, owned["owner_course_sha256"], catalog)
        physical = raw / "physical-reader" / label / candidate
        wrench = verified_read(physical / "wrench.json", None, catalog)
        verified_read(physical / "physical.json", wrench["raw_sha256"], catalog)
        optics_path = raw / "optical-reader" / label / (candidate + ".json")
        optical = verified_read(optics_path, None, catalog)
        acquisition = raw / "independent-exposures" / label / candidate
        source = verified_read(acquisition / "exposure.json", optical["exposures_sha256"], catalog)
        assert [r["frame_id"] for r in optical["frames"]] == [
            r["frame_id"] for r in source["frames"]
        ]
        for frame in source["frames"]:
            path = acquisition / frame["file"]
            assert study.sha(path) == frame["sha256"]
            catalog[path] = frame["sha256"]
        info = selection.label(raw, label, candidate)
        checked[candidate] = dict(info, first_native_failure=original["terminal_error"])
    return dict(
        placement=label,
        role=fit,
        choice=replay["provisional_physical_optical_choice"],
        selection_ms=decision["selection_ms"],
        results=checked,
    )


def joint(v):
    return v["mechanical"] and v["all_three"]


def summarize(rows, bank):
    eligible = {r["placement"]: [k for k, v in r["results"].items() if joint(v)] for r in rows}
    by_id = dict()
    for key in bank["candidate_ids"]:
        results = [row["results"][key] for row in rows]
        by_id[key] = dict(
            physical=sum(row["mechanical"] for row in results),
            optical_all_three=sum(row["all_three"] for row in results),
            optical_frames=sum(row["optical_frame_passes"] for row in results),
            actual_images=sum(row["frame_count"] for row in results),
            joint=sum(joint(row) for row in results),
            gains_over_nominal=sum(
                joint(r["results"][key]) and not joint(r["results"][NOMINAL]) for r in rows
            ),
            losses_over_nominal=sum(
                joint(r["results"][NOMINAL]) and not joint(r["results"][key]) for r in rows
            ),
            physical_refusals=Counter(
                row["first_native_failure"] for row in results if row["first_native_failure"]
            ),
        )
    return dict(
        placements=len(rows),
        compared=len(rows) * len(bank["candidate_ids"]),
        selections=sum(row["choice"] is not None for row in rows),
        any_measured_joint_choice=sum(bool(options) for options in eligible.values()),
        choices_by_placement=eligible,
        per_candidate=by_id,
    )


def main(root, output):
    catalog = {}
    bank = verified_read(selection.FREEZE, FREEZE, catalog)
    reg = verified_read(study.REG, bank["registration_sha256"], catalog)
    rows, sections = [], {}
    for region in ("blind_mechanical_first", "blind_optical_first"):
        subset = [one(root, q["name"], bank, region, catalog) for q in reg[region]]
        sections[region] = summarize(subset, bank)
        rows.extend(subset)
    aggregate = summarize(rows, bank)
    result = dict(
        freeze_sha256=FREEZE,
        fit_placement_groups=len(bank["groups"]),
        fixed=bank["fixed"],
        aggregate=aggregate,
        prospective_groups=sections,
        independence="finite diagnostic placements",
        complete_runtime_qualification=False,
        integrated_evaluation_slots=0,
        new_formal=0,
        hardware=0,
        rows=rows,
        sources_sha256={
            path.relative_to(root).as_posix(): token for path, token in sorted(catalog.items())
        },
    )
    study.write(output, result)
    print("poses", aggregate["placements"], "tested courses", aggregate["compared"])
    print(
        "selection",
        aggregate["selections"],
        "any measured joint",
        aggregate["any_measured_joint_choice"],
    )
    for k, v in aggregate["per_candidate"].items():
        print(
            k,
            v["physical"],
            v["optical_all_three"],
            v["joint"],
            v["gains_over_nominal"],
            v["losses_over_nominal"],
        )
    print(len(catalog), "source receipts", study.sha(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(Path.cwd(), args.output)
