"""Sign the complete fit-reuse readback only after frozen-input and consumer-equivalence checks."""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import independent_gate as verify

fixture, replay = verify.fixture, verify.replay
ROOT, ROUND, V1 = verify.ROOT, verify.ROUND, verify.V1
SHA, CHECK, READ, WRITE = verify.SHA, verify.CHECK, verify.READ, verify.WRITE
TEST_FILES = ("tests/test_graduation_g1_radial_fit_reuse.py", "tests/test_graduation_g1_radial_native_grid.py",
              "tests/test_graduation_g1_visibility_deadline.py", "tests/test_graduation_g1_visibility_replay.py")


def regressions(work):
    detector = READ(work/"candidate-sources.json")["detector_files_sha256"]
    CHECK(all(SHA(ROOT/k)==v for k,v in detector.items()),"foreign detector for boundary regression")
    files = [ROOT/k for k in TEST_FILES] + [ROUND/"test_independent_gate.py",V1/"test_semantic_release.py"]
    junit = work/"software-regressions-final.junit.xml"
    cmd = [sys.executable,"-m","pytest","-q","-p","no:cacheprovider","--junitxml",str(junit),*map(str,files)]
    proc = subprocess.run(cmd, cwd=ROOT, env=verify.ENV,capture_output=True,text=True)
    print(proc.stdout,proc.stderr,flush=True)
    CHECK(proc.returncode==0,"registered software regressions did not pass")
    suite = ET.parse(junit).getroot().find("testsuite")
    rows = [r.get("classname")+"::"+r.get("name") for r in suite.iter("testcase")]
    CHECK(int(suite.get("tests"))==len(rows) and all(any(p.stem in row for row in rows) for p in files)
          and all(int(suite.get(k))==0 for k in ("errors","failures","skipped")),
          "missing boundary regression")
    required = ("rank_deficient","near_cutoff","fallback","float32","other_width","borderline","native_order_strength")
    CHECK(all(any(k in row for row in rows) for k in required) and all(SHA(ROOT/k)==v for k,v in detector.items()),
          "unverified fit boundary or source changed")
    WRITE(work/"software-regressions.json",{"schema":"g1.fit-reuse.software-regressions.v1",
          "timing_plan_sha256":verify.PLAN,"detector_files_sha256":detector,"passed":len(rows),"all_passed":True,
          "test_files_sha256":{fixture.rel(p):SHA(p) for p in files},"junit_sha256":SHA(junit),"testcases":rows})


def publish(work):
    semantic = READ(work/"semantic/semantic-equivalence.public.json")
    locked = READ(work/"inputs.json")
    detector = READ(work/"candidate-sources.json")["detector_files_sha256"]
    suites = READ(work/"software-regressions.json")
    pair_seal = READ(work/"full-blind-seals.json")
    CHECK(semantic["eligible"] and semantic["all_candidate_outputs_byte_equivalent"] and
          semantic["independently_implemented_native_scorer_closed_at_1e_minus_10_m"] and
          semantic["detector_files_sha256"]==suites["detector_files_sha256"]==detector and
          suites["all_passed"] and all(SHA(ROOT/k)==v for k,v in detector.items()),
          "software equivalence or boundary regression failed")
    source = dict(locked["input_artifacts_sha256"])
    def pin(path,expected=None):
        digest = SHA(path)
        CHECK(expected is None or digest==expected, "publication prerequisite changed: "+str(path))
        source[fixture.rel(path)]=digest
    def attach(original, name, expected=None):
        dest=ROUND/name
        verify.copy_new(original,dest)
        pin(dest,expected)
    generic=ROUND/"qualification"
    generic.mkdir(exist_ok=False)
    verify.copy_new(V1/"qualification/replay-legacy-red.public.json",generic/"replay-legacy-red.public.json")
    replay.publish(work,generic)
    gate=READ(generic/"replay-release.public.json")
    CHECK(gate["eligible"] and gate["historical_frames"]==778 and gate["first_refusals_recovered"]==8
          and gate["false_positive_controls"]==0 and gate["positive_controls"]==4 and gate["negative_controls"]==16
          and gate["control_witnesses"] and all(gate["historical_gates"].values()),"historical/control gate failed")
    pin(generic/"replay-release.public.json")
    source.update(gate["input_artifacts_sha256"])
    for p in sorted((work/"semantic").iterdir()):
        attach(p,p.name)
    for key in ("historical",*verify.SCOPES,"context"):
        rec=pair_seal["independent_scope_receipts"][key]
        digest=verify.pair_receipt(rec["worker_receipts"])
        CHECK(digest==rec["sha256"],"invalid independent prejoin seal")
        for receipt in rec["worker_receipts"]:
            CHECK(SHA(work/"independent"/receipt["file"])==digest,"cold-read product changed after compare")
        attach(work/"independent"/rec["worker_receipts"][0]["file"], "candidate-full-"+key+".public.json.gz",digest)
    attach(work/"context-physical-baseline.json.gz","context-physical-baseline.public.json.gz",pair_seal["physical_baseline_context_sha256"])
    attach(work/"full-blind-seals.json","full-blind-seals.public.json")
    attach(work/"candidate-sources.json","candidate-sources.public.json",pair_seal["source_manifest_sha256"])
    attach(work/"software-regressions.json","software-regressions.public.json")
    attach(work/"software-regressions-final.junit.xml","software-regressions.public.xml",suites["junit_sha256"])
    for k,h in suites["test_files_sha256"].items():
        pin(ROOT/k,h)
    for p in (Path(__file__),ROUND/"independent_gate.py",ROOT/fixture.DETECTORS[0],ROOT/fixture.DETECTORS[1],
              V1/"publish_software_gate.py",V1/"semantic_release.py",V1/"semantic_replay.py"):
        pin(p)
    actual_file = ROUND/"actual-lapack-equivalence.public.json"
    actual = READ(actual_file)
    pin(ROUND/"fit_equivalence.py",actual["source_sha256"])
    pin(V1/"solver-witness.public.json",actual["baseline_system_evidence_sha256"])
    pin(ROUND/"detector-source.public.json")
    pin(ROUND/"pixel_timing.py")
    pin(V1/"pixel_seed_profile.py")
    original_systems = READ(V1/"solver-witness.public.json")["frames"]
    measured = READ(work/"candidate-dynamic.json.gz")["frames"]
    counts = {}
    for name,row in actual["frames"].items():
        frame = measured[row["frame_id"]]
        reference = original_systems[name]
        CHECK(row["all_x_rank_s_bitwise"] and frame["file_sha256"]==row["file_sha256"] and
              frame["checksum_sha256"]==row["checksum_sha256"] and
              fixture.prior.digest(frame["measurement"])==row["measurement_sha256"]==reference["measurement_sha256"] and
              Counter(g["inputs_sha256"] for g in row["grouped_inputs"])==
              Counter(g["inputs_sha256"] for g in reference["same_lapack_witness"]["groups"]),
              "actual fit inputs, measurement or independent singular-value witness differs")
        counts[name] = sum(g["systems"] for g in row["grouped_inputs"])
        CHECK(counts[name]==row["systems"],"lost actual fitted system")
    CHECK(actual["detector_files_sha256"]==detector and counts=={"frames/0127.json":272,"frames/0128.json":244},
          "actual fit system coverage changed")
    pin(actual_file)
    # Raw inputs are archived continuously in the physical cases and static/anonymous stores.
    previous_gate=READ(V1/"replay-release.public.json",verify.V1_GATE)
    old_file=V1/"software-local-raw-bindings.public.json"
    raw=READ(old_file,previous_gate["input_artifacts_sha256"][fixture.rel(old_file)])
    CHECK(all(SHA(Path(k))==v for k,v in raw["static_registered_raw_inputs_sha256"].items()) and
          all(SHA(ROOT/k)==v for k,v in raw["dynamic_registered_raw_inputs_sha256"].items()),"source pixel bytes changed")
    pin(old_file)
    CHECK(all(SHA(ROOT/k)==v for k,v in source.items()),"input changed before software release")
    mount=locked["geometry_identity"]
    result={**gate,"timing_plan_sha256":verify.PLAN,"fit_reuse_plan_sha256":verify.PLAN,
            "previous_timing_plan_sha256":locked["previous_timing_plan_sha256"],
            "previous_software_release_sha256":verify.V1_GATE,"baseline_runtime_build_sha256":verify.BASELINE,
            "detector_files_sha256":detector,"same_all_fields":True,"radial_offset_mm":15,
            "d02_frames":list(fixture.BATCHES.values()),"d02_all_fields_equal":True,
            "d02_actual_observer_frames":[semantic["d02"][k]["actual_observer_calls"] for k in fixture.BATCHES],
            "d02_actual_servo_targets":[semantic["d02"][k]["servo_shield_targets"] for k in fixture.BATCHES],
            "static_anchors":22,"static_pixel_inputs":44,"static_all_fields_equal":True,"static_geometry_qualified":True,
            "static_geometry_registration_id":mount["registration_id"],
            "static_geometry_asset_sha256":mount["pose_marker"]["marked_asset_sha256"],
            "native_conflict_rejected_m":semantic["native_disagreement_refusal_m"],
            "immutable_source_snapshot_sha256":SHA(ROUND/"source-snapshot.public.json.gz"),
            "full_semantics_sha256":SHA(ROUND/"semantic-equivalence.public.json"),
            "complete_cold_read_seals_sha256":SHA(ROUND/"full-blind-seals.public.json"),
            "source_switch_control_passed":True, "fit_boundary_regressions_passed":suites["passed"],
            "real_fits_with_bitwise_solution_rank_singular_values":sum(counts.values()),
            "claim_scope":"Offline development software qualification and registered static geometry.", "input_artifacts_sha256":source}
    dest=ROUND/"replay-release.public.json"
    WRITE(dest,result)
    CHECK(READ(dest)==result,"published software gate failed readback")
    print(SHA(dest),len(source),dest,flush=True)


if __name__=="__main__":
    {"regressions":regressions,"publish":publish}[sys.argv[1]](Path(sys.argv[2]))

