"""Read cold geometry reconstructions and compare the pre-motion forecasts to first contact."""

from pathlib import Path

from scripts.graduation.perception_io import pinned, read, sha, write

HERE = Path(__file__).resolve().parent
DIAGNOSIS = HERE.parent / "round-g1-dual-support-contact-diagnosis-20261125"
DEPTH = HERE.parent / "round-g1-rgbd-clearance-feasibility-20261125"
RAW = Path("experiments/results/g1-cv-grasp-validation-20261125")


def compare():
    seal = pinned(
        HERE / "sweep-seal.public.json",
        "23321cb174a9db4012af5560517c0ba6a669ac1e17b4581672b6bdeac5a8b02c",
    )
    assert seal
    history = pinned(
        HERE / "sweep-history.public.json",
        "ed3227b1823aac1878eb410e702b52a9ff995275fb14d29514e91ac1cfb0a14d",
    )
    readers = RAW / "independent-contact-readers"
    cold = read(readers / "cold-reader-receipts.json")
    assert len(cold) == len({v["pid"] for v in cold}) == 2
    assert all(r["exit_code"] == 0 for r in cold)
    reference = read(DIAGNOSIS / "dense-independent-seal.public.json")
    seals = [sha(readers / lane / "seal.json") for lane in ("one", "two")]
    assert seals == reference["two_seals_sha256"]
    for name, digest in reference["files_sha256"].items():
        assert all(sha(readers / lane / name) == digest for lane in ("one", "two"))

    matrix = read(readers / "one/matrix-summary.json")
    checks = []
    for mount, batch, key, pair, step in (
        (
            15,
            "train-radial15-timing-01",
            "right_finger_id8_plate",
            ("right_finger_geom", "g1_dual_id8_plate"),
            1221,
        ),
        (
            30,
            "train-radial30-contact-d02-02",
            "left_finger_id7_crossbar",
            ("left_finger_geom", "g1_dual_id7_crossbar"),
            1228,
        ),
    ):
        trajectory = matrix[f"trace{mount}_mount{mount}"]
        physical = trajectory["first_hazard"]
        assert physical["step"] == step
        assert {tuple(r["pair"]) for r in physical["unauthorized_contacts"]} == {pair}
        assert not trajectory["source_contact_multiplicity_differences"]
        gaps = [trajectory["critical"][str(t)][key]["certified_mm"] for t in (step - 1, step)]
        assert gaps[0] > 0 > gaps[1]
        predictions = []
        for row in history["frames"]:
            if batch not in Path(row["frame_file"]).parts:
                continue
            center = next(
                c
                for c in row["center_each"]
                if c["candidate_id"] == "existing_tool_closure_axis:+0.000000"
            )
            assert row["step"] < step and center["full_physical_clearance"] == "BLOCKED"
            reported = sorted({tuple(hit[1:3]) for hit in center["hits"]})
            predictions.append(
                dict(
                    observation_step=row["step"],
                    role=row["class_role"],
                    recorded_limiting_pairs=reported,
                    named_first_pair=pair in reported,
                )
            )
        assert len(predictions) == 2
        checks.append(
            dict(
                mount_radius_mm=100 + mount,
                cold_reconstructed_states=trajectory["states"],
                first_forbidden_step=step,
                first_forbidden_pair=pair,
                last_positive_then_contact_gap_mm=gaps,
                prior_center_forecasts=predictions,
            )
        )

    rechecked = {}
    for name, original in (
        ("postseal-late-estimates.json", "estimates.public.json"),
        ("postseal-late-comparison.json", "clearance-comparison.public.json"),
    ):
        digest = sha(RAW / name)
        assert digest == sha(DEPTH / original)
        counts = {key: len(v["frames"]) for key, v in read(RAW / name)["cases"].items()}
        assert counts == {"115mm": 9, "130mm": 9}
        rechecked[name] = dict(sha256=digest, frames=counts)
    return dict(
        pre_motion_candidate_seal_sha256=sha(HERE / "sweep-seal.public.json"),
        independent_cold_readers=cold,
        cold_result_seals=seals,
        original_trajectories=checks,
        late_depth_readbacks=rechecked,
        new_integration_steps=0,
    )


if __name__ == "__main__":
    write(HERE / "postseal-contact.public.json", compare())
