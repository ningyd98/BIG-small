"""Recompute both whole-trajectory transfers before issuing the development handoff profile."""

from pathlib import Path

from scripts.graduation import g1_complete_cv_handoff as gate
from scripts.graduation.g1_complete_cv_handoff_fit import validate
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha


def qualify():
    here = Path(__file__).resolve().parent
    freeze = pinned(
        here / "handoff-motion-validation-freeze.public.json",
        "04811664819dae923571d546d55482fb4c9999c84a69716adc74bf75911f67ef",
    )
    for p, digest in freeze["source_sha256"].items():
        assert sha(ROOT / p) == digest
    old = ROOT / "experiments/results/g1-skill-handoff-20261125"
    new = old / "heldout-post-freeze-01"
    fit_path = old / "handoff-motion-fit-02.json"
    profile = read(fit_path)
    assert profile["qualified"] is False
    reports = {}
    for source, cases, name in (
        (old, ["unseen-d", "unseen-e"], "handoff-motion-transfer-02.json"),
        (new, ["sealed-left", "sealed-right"], "handoff-motion-new-02.json"),
    ):
        result = validate(source, profile, cases)
        assert result == read(old / name)
        tested = {r["skill"] for r in result if r["continued"]}
        assert tested == set(gate.STAGES[1:])
        for r in result:
            if r["continued"]:
                assert not r["actual_contact"] and r["actual_min_gap_m"] > 0
                assert r["envelope_pair_reserve_m"] >= 0 and r["envelope_vertex_reserve_m"] >= 0
        reports[name] = dict(
            sha256=sha(old / name),
            results=result,
            distinct_stops=sum(r["scheduled_stop_instants"] for r in result),
        )
    for case in ["sealed-left", "sealed-right"]:
        s = read(new / "physical-capture-01" / case / "summary.json")
        assert s["complete_skill_transitions"] == 7 and s["lift_terminal_120_bilateral_at_50mm"]
        assert s["final_120_settled_and_contained"] and s["forbidden_structural_contact_steps"] == 0
    destination = ROOT / "scripts/graduation/g1_complete_cv_handoff_profile.json"
    write_once(
        destination,
        profile
        | dict(
            qualified=True,
            fit_sha256=sha(fit_path),
            qualification_sha256={n: r["sha256"] for n, r in reports.items()},
        ),
    )
    out = here / "handoff-motion-qualification.public.json"
    write_once(
        out,
        dict(
            fit_sha256=sha(fit_path),
            profile_sha256=sha(destination),
            scope="development",
            cold_reads=reports,
            scored_native_attempts=0,
        ),
    )
    print(sha(destination), sha(out))


if __name__ == "__main__":
    qualify()
