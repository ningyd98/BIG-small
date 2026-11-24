"""Publish the original readback and the stricter radial native software gate after both passed."""

from pathlib import Path
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import semantic_replay as fixture
from semantic_release import CANDIDATE

READ, WRITE, CHECK, SHA = fixture.READ, fixture.WRITE, fixture.CHECK, fixture.SHA


def copy_new(src, dest):
    with src.open("rb") as inp, dest.open("xb") as out:
        shutil.copyfileobj(inp,out)
    CHECK(SHA(src)==SHA(dest),"published bytes differ")


def publish(private, full_old, static_source):
    rd, root, replay = fixture.ROUND, fixture.ROOT, fixture.replay
    report = READ(private/"semantic/semantic-equivalence.public.json")
    CHECK(report["eligible"] and report["all_candidate_outputs_byte_equivalent"] and
          report["independently_implemented_native_scorer_closed_at_1e_minus_10_m"] and
          report["detector_files_sha256"]==CANDIDATE and all(SHA(root/k)==v for k,v in CANDIDATE.items()),
          "not software-qualified")
    locked = READ(private/"semantic/semantics-inputs.public.json")
    source = dict(locked["input_artifacts_sha256"])
    def pin(p):
        source[fixture.rel(p)] = SHA(p)
    def attach(p, name):
        path = rd / name
        copy_new(p,path)
        pin(path)
    generic = rd/"qualification"
    generic.mkdir(exist_ok=False)
    copy_new(fixture.PREVIOUS/"replay-legacy-red.public.json",generic/"replay-legacy-red.public.json")
    replay.publish(private,generic)
    normal = generic/"replay-release.public.json"
    gate = READ(normal)
    CHECK(gate["eligible"] and all(gate["historical_gates"].values()) and
          gate["historical_frames"]==778 and gate["first_refusals_recovered"]==8 and
          gate["positive_controls"]==4 and gate["negative_controls"]==16 and not gate["false_positive_controls"] and
          SHA(full_old) == locked["old_complete_historical_bytes_sha256"], "generic or old gate changed")
    source.update(gate["input_artifacts_sha256"])
    pin(normal)
    for p in sorted((private/"semantic").iterdir()):
        attach(p,p.name)
    attach(full_old,"full-historical-baseline.public.json.gz")
    attach(private/"historical-full-candidate.json.gz","full-historical-candidate.public.json.gz")
    for gen in ("baseline","candidate"):
        for mode in ("dynamic",*fixture.STATIC):
            name=gen+"-"+mode
            attach(private/(name+".json.gz"),name+".public.json.gz")
    static_private = {str(static_source/v["source_packet_file"]):v["file_sha256"] for v in locked["static_packets"].values()}
    CHECK(all(SHA(Path(p))==h for p,h in static_private.items()), "static packet changed after readback")
    # Full raw RGB-D remains in its registered local acquisition store. Each index and pixel digest is retained.
    local_manifest = {"schema":"g1.radial-native-local-raw-bindings.v1",
                      "static_registered_raw_inputs_sha256":static_private,"dynamic_registered_raw_inputs_sha256":{},
                      "static_registered_source_table":fixture.rel(fixture.MECHANICAL/"screen-optical-15.public.json.gz"),
                      "formal_current_rgbd_index":fixture.rel(replay.PACKETS/"index.json")}
    for v in locked["dynamic_packets"].values():
        p=fixture.BASE/"batches"/v["batch"]/"d02/instance/frames"/v["file"]
        CHECK(SHA(p)==v["file_sha256"],"historical acquisition changed after measurement")
        local_manifest["dynamic_registered_raw_inputs_sha256"][fixture.rel(p)]=v["file_sha256"]
    local_file = rd/"software-local-raw-bindings.public.json"
    WRITE(local_file,local_manifest)
    pin(local_file)
    for p in (rd/"plan.json",rd/"plan.md",rd/"semantic_replay.py",rd/"semantic_release.py",
              rd/"test_semantic_release.py",Path(__file__),fixture.REFERENCE_SCRIPT,replay.PACKETS/"index.json",
              root/"scripts/graduation/g1_visibility_radial.py",root/"scripts/graduation/g1_visibility_replay.py",
              *(root/k for k in CANDIDATE)):
        pin(p)
    CHECK(all(SHA(root/k)==v for k,v in source.items()),"source changed before software release")
    results = {**gate,"timing_plan_sha256":fixture.PLAN, "baseline_runtime_build_sha256":fixture.BASELINE,
               "detector_files_sha256":CANDIDATE,"radial_offset_mm":15,"same_all_fields":True,
               "d02_frames":list(fixture.BATCHES.values()),"d02_all_fields_equal":True,
               "d02_actual_observer_frames":[report["d02"][k]["actual_observer_calls"] for k in fixture.BATCHES],
               "d02_actual_servo_targets":[report["d02"][k]["servo_shield_targets"] for k in fixture.BATCHES],
               "static_anchors":22,"static_pixel_inputs":44,"static_all_fields_equal":True,"static_geometry_qualified":True,
               "static_geometry_registration_id":locked["geometry_identity"]["registration_id"],
               "static_geometry_asset_sha256":locked["geometry_identity"]["pose_marker"]["marked_asset_sha256"],
               "immutable_source_snapshot_sha256":SHA(rd/"source-snapshot.public.json.gz"),
               "full_semantics_sha256":SHA(rd/"semantic-equivalence.public.json"),
               "native_conflict_rejected_m":report["native_disagreement_refusal_m"],
               "claim_scope":"Offline development software equivalence and registered geometry only.",
               "input_artifacts_sha256":source}
    out = rd/"replay-release.public.json"
    WRITE(out,results)
    CHECK(READ(out)==results,"software gate readback mismatch")
    print(SHA(out),len(source),out)


if __name__=="__main__":
    publish(*map(Path,sys.argv[1:]))

