"""Verify sealed observer outputs against native feedback, both scorers and physical radial poses."""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import semantic_replay as fixture

BASE, ROOT, ROUND = fixture.BASE, fixture.ROOT, fixture.ROUND
READ, WRITE, CHECK, SHA = fixture.READ, fixture.WRITE, fixture.CHECK, fixture.SHA
prior, replay = fixture.prior, fixture.replay
GRID_SHA = "c0e80c0b3b36ad397a4d26146e9dc8c6d2063669dd28244bb9beb29f6b211e69"
VISION_SHA = "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169"
CANDIDATE = dict(zip(fixture.DETECTORS, (GRID_SHA, VISION_SHA), strict=True))


def independent_difference(diff):
    path = diff["path"]
    geometry = (len(path) == 2 and path[0] in {"tcp_m", "top_m"}) or (
        len(path) == 4 and path[0] == "per_id" and path[1] in {"7", "8"} and path[2] in {"center_m", "tcp_m", "top_m"}
    )
    return (geometry and type(path[-1]) is int and 0 <= path[-1] <= 2 and
            type(diff["old"]) is float and type(diff["new"]) is float and abs(diff["old"] - diff["new"]) <= 1e-10)


def negative_conflict(r):
    return (not r["usable"] and r["selected_id"] is None and r["usable_ids"] == [7, 8] and
            r["tcp_m"] is None and r["top_m"] is None and r["reason"] == "dual_marker_grasp_conflict"
            and r["target_disagreement_m"] > 0.010)


def control_endpoint(initial, reference, current):
    return {axis: initial[axis] + (v - r) for axis, v, r in zip("xyz", current, reference, strict=True)}


def control_trace(audit, labels, raw):
    feedbacks = {k for k,r in labels.items() if r["label"].endswith("/feedback")}
    shield = {d["frame_id"]: d for d in audit if "target_pose" in d and d["phase"] == "FEEDBACK"}
    initial = {d["grounded_step"]["skill"]: d["grounded_step"]["parameters"]["target_pose"]
               for d in audit if "grounded_step" in d}
    expected, fresh = {}, {}
    controller_seen = 0
    for d in audit:
        if "visual_samples" not in d:
            continue
        skill = d["skill"]
        CHECK(skill in {"MOVE_ABOVE", "APPROACH"}, "new servo mode needs an independently registered endpoint rule")
        ref, = [k for k,row in labels.items() if row["label"] == skill + "/servo_reference"]
        ref_grasp = raw[ref]["measurement"]["grasp_world_m"]
        ctrls = {r["physics_step"]: r["target_pose"] for r in d["control_samples"]}
        for sample in d["visual_samples"]:
            i = sample["development_dual_marker"]["frame_id"]
            native = sample["development_dual_marker"]
            m = raw[i]["measurement"]
            CHECK(i in feedbacks and m["usable"] and i in shield and
                  sample["target_source"] == "CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE" and
                  sample["ground_truth_used_for_control"] is False and shield[i]["shield"]["allowed"] and
                  sample["target_pose"] == shield[i]["target_pose"], "feedback did not reach its recorded Shield target")
            step = labels[i]["physics_step"]
            if step in ctrls:
                CHECK(ctrls[step] == sample["target_pose"], "native controller received a different target")
                controller_seen += 1
            identity = {"calibration": sample["calibration_version"], "source": sample["target_source"],
                        "controller_completion": step in ctrls, "step": step, "skill": skill}
            expected[i] = {**identity, "marker": native, "target_pose": sample["target_pose"]}
            fresh[i] = {**identity, "marker": {k:m[k] for k in native},
                        "target_pose": control_endpoint(initial[skill], ref_grasp, m["grasp_world_m"])}
    CHECK(set(expected) == set(shield) and set(expected) <= feedbacks, "Shield/accepted population changed")
    stopped = sorted(feedbacks - set(expected))
    CHECK(all(not raw[i]["measurement"]["usable"] and raw[i]["measurement"]["grasp_world_m"] is None for i in stopped),
          "unaccounted feedback without an independently registered refusal")
    return expected, fresh, {"attempted": len(feedbacks), "servo_shield_targets":len(expected),
                             "completed_native_controller_rows": controller_seen, "refusals":stopped}


def snapshot(tree):
    return {str(p.relative_to(tree)):SHA(p) for p in sorted(tree.rglob("*")) if p.is_file()}


def main(private, source_tree, historical_baseline):
    locked = READ(private / "inputs.json")
    CHECK(locked["timing_plan_sha256"] == fixture.PLAN and
          all(SHA(ROOT / k) == v for k,v in locked["input_artifacts_sha256"].items()), "post-capture inputs changed")
    source_tree = source_tree.resolve()
    before, after = snapshot(fixture.OLD_TREE), snapshot(source_tree)
    delta = [k for k in before if before[k] != after[k]]
    CHECK(before.keys() == after.keys() and delta == [fixture.DETECTORS[0]] and
          all(after[k] == v == SHA(ROOT / k) for k,v in CANDIDATE.items()), "non-detector dependency changed")
    old_sources = {k:before[k] for k in fixture.DETECTORS}
    prev = fixture.PREVIOUS
    old_release = READ(prev / "replay-release.public.json", locked["input_artifacts_sha256"][fixture.rel(prev/"replay-release.public.json")])
    CHECK(old_release["detector_files_sha256"] == old_sources, "prior release differs from baseline")
    old_hist = READ(historical_baseline, locked["old_complete_historical_bytes_sha256"])
    new_hist = READ(private / "historical-full-candidate.json.gz")
    CHECK(old_hist["detector_files_sha256"] == old_sources and new_hist["detector_files_sha256"] == CANDIDATE and
          old_hist["index_sha256"] == new_hist["index_sha256"] == replay.INDEX_SHA, "incorrect full historical capture")
    diffs, counts, exact_sections, native_sections, imports = {}, {}, [], [], {}
    def compare(name, old, new, native=False):
        counts[name] = prior.compare(name, old, new, diffs)
        (native_sections if native else exact_sections).append(name)
    def prior_file(path):
        return READ(path, old_release["input_artifacts_sha256"][fixture.rel(path)])
    compare("historical_complete_measure_frame", old_hist["frames"], new_hist["frames"])
    compare("controls_complete_measure_frame", old_hist["controls"], new_hist["controls"])
    seal, blind = replay.sealed_products(private / "blind")
    CHECK({k:seal["detector_files_sha256"][k] for k in CANDIDATE} == CANDIDATE and
          all(after[k] == v for k,v in blind["project_sources_sha256"].items()), "blind reader used unrelated sources")
    imports["independent_historical_readers"] = blind["project_sources_sha256"]
    compare("historical_blind_archived_and_new", prior_file(prev / "replay-blind-frames.public.json.gz")["frames"], blind["frames"])
    report = private / "report"
    q = READ(report/"qualification.json")
    gate = READ(report/"replay-historical.public.json", q["historical_sha256"])
    controls = READ(report/"replay-controls.public.json", q["control_sha256"])
    compare("twenty_interventions_with_acquisition_checks", prior_file(prev/"replay-controls.public.json")["cases"], controls["cases"])
    collision = new_hist["controls"]["same-RGB-and-altered-identity-depth-calibration"]
    conflict = controls["cases"]["true-two-target-conflict"]
    CHECK(all(v for v in collision.values() if isinstance(v,bool)) and negative_conflict(conflict["result"]) and
          conflict["qualification_witness"] and controls["positive_controls"] == 4 and controls["negative_controls"] == 16 and
          controls["false_positive_controls"] == 0 and controls["all_control_witnesses"], "negative/positive witness failed")
    sets = {}
    for mode in ("dynamic", *fixture.STATIC):
        oo, nn = (READ(private / (x + "-" + mode + ".json.gz")) for x in ("baseline","candidate"))
        CHECK(oo["detector_files_sha256"] == old_sources and nn["detector_files_sha256"] == CANDIDATE and
              oo["index_sha256"] == nn["index_sha256"] == locked["index_sha256"][mode],
              "incorrect observer or pixel group")
        for tag,read,application in (("baseline",oo,before),("candidate",nn,after)):
            imp = read["imported_files_sha256"]
            CHECK(all(imp[k] == application[k] for k in imp) and set(CANDIDATE) <= set(imp), "foreign observer dependency")
            imports[tag + "-" + mode] = imp
        sets[mode] = (oo["frames"],nn["frames"])
    per_batch = {}
    for label,count in fixture.BATCHES.items():
        folder = BASE/"batches"/label
        instance = folder/"d02/instance"
        labels = {k:v for k,v in locked["dynamic_packets"].items() if v["batch"]==label}
        CHECK(len(labels) == count, "lost d02 sample")
        old,new = ({k:d[k] for k in labels} for d in sets["dynamic"])
        compare(label+"/old_vs_candidate_complete",old,new)
        online = READ(instance/"online-vision.json")["frames"]
        missing = set(new)-set(online)
        CHECK(len(missing) == 1 and all(labels[k]["label"]=="terminal" for k in missing), "unaccounted online observation")
        compare(label+"/native_online_complete", {k:v["measurement"] for k,v in online.items()}, {k:new[k]["measurement"] for k in online})
        score = READ(folder/"score.json")
        token = SHA(instance/"pixel-index.json")
        archived = []
        for i,side in enumerate(("blind-one","blind-two")):
            d = folder/"scoring"/side
            archive = READ(d/"seal.json",score["blind_seals_sha256"][i])
            CHECK(archive["n_frames"] == count and archive["index_sha256"] == score["pixel_index_sha256"], "wrong native scoring seal")
            archived.append({v["frame_id"]: v for v in READ(d/(token+".json"),archive["packets"][token])})
        CHECK(prior.canonical(archived[0]) == prior.canonical(archived[1]), "previous native readers diverged")
        derived = {}
        for k,row in new.items():
            m = row["measurement"]
            projected = {**row, **m, "tcp_m":m["grasp_world_m"],"top_m":m["object_top_world_m"]}
            derived[k] = {f:projected[f] for f in archived[0][k]}
        compare(label+"/independent_native_archived", archived[0], derived, native=True)
        expected, actual, trace_counts = control_trace(READ(instance/"online-audit.json"), labels, new)
        compare(label+"/actual_native_servo_shield_controller",expected,actual)
        refused = max([k for k in labels if labels[k]["label"].endswith("/feedback")], key=lambda k:labels[k]["physics_step"])
        m = new[refused]["measurement"]
        if label == "train-feedback-deadline-01":
            CHECK(not m["usable"] and m["reason"]=="ambiguous_marker_identity" and m["observed_ids"]==[7,28] and
                  refused in trace_counts["refusals"], "old ambiguous approach was admitted")
        else:
            CHECK(m["usable"] and m["selected_id"]==7 and refused in expected, "old accepted feedback changed")
        per_batch[label] = {"frames":count, "actual_observer_calls":len(online), "unobserved_terminal":sorted(missing),
                            **trace_counts, "last_feedback":{"frame_id":refused, "step":labels[refused]["physics_step"],
                            **{k:m[k] for k in ("observed_ids","usable_ids","usable","selected_id","reason","registration_id","grasp_world_m")}}}
    old_table = READ(fixture.MECHANICAL/"screen-optical-15.public.json.gz")
    screen_summary = {}
    for mode in fixture.STATIC:
        old,new = sets[mode]
        compare(mode+"/actual_registered_old_vs_candidate",old,new)
        original, current, max_mm = {}, {}, 0.0
        errors = []
        for anchor in old_table["frames"]:
            reference = anchor[mode]
            i, = [k for k,v in locked["static_packets"].items() if v["source_packet_file"] == reference["packet_file"]]
            row = new[i]
            m = row["measurement"]
            identity = locked["geometry_identity"]
            CHECK(m["asset_sha256"]==identity["pose_marker"]["marked_asset_sha256"] and m["registration_id"]==identity["registration_id"] and
                  reference["qualified"] and m["usable"] and m["selected_id"] in m["usable_ids"] and
                  (not reference["requires_both_codes"] or m["usable_ids"] == [7,8]), "wrong static registration or solution")
            truth = reference["truth"]
            CHECK(truth["correct_registered_id"] and set(row["per_id"]) == set(truth["per_id"]), "wrong registered print")
            independent = {}
            for code, xyz in row["per_id"].items():
                metrics = {axis+"_error_mm":1000*math.dist(xyz[axis+"_m"],truth["truth_"+axis+"_world_m"]) for axis in ("center","top","tcp")}
                CHECK(all(metrics[k]<=10 for k in metrics) and
                      all(abs(metrics[k]-truth["per_id"][code][k])<=1e-7 for k in metrics), "current independent static truth exceeds limit")
                independent[code]=metrics
                max_mm=max(max_mm, metrics["top_error_mm"], metrics["tcp_error_mm"])
            if len(row["per_id"])==2:
                CHECK(m["target_disagreement_m"]<=.010, "static dual target conflicts")
            original[i]=reference["measurement"]
            current[i]={k:m[k] for k in reference["measurement"]}
            errors.append({"case":anchor["case"], "role":anchor["role"], "step":anchor["step"], "frame_id":i,
                           "registered_identity":m["registration_id"], "selected_id":m["selected_id"], "independent_error_mm":independent})
        compare(mode+"/original_static_screen_all_published_fields",original,current)
        screen_summary[mode]={"samples":len(new), "maximum_current_top_or_tcp_error_mm":max_mm, "anchors":errors}
    exact = all(counts[k]["scalar_differences"] == 0 for k in exact_sections)
    independently_closed = all(independent_difference(d) for k in native_sections for records in diffs.get(k,{}).values() for d in records)
    signature = {"schema":"g1.radial-native-source-snapshot.v1","baseline_runtime_build_sha256":fixture.BASELINE,
                 "changed_files":delta,"baseline_files_sha256":before,"candidate_files_sha256":after,
                 "worker_imports_sha256":imports,"candidate_qualification_source_sha256":CANDIDATE,
                 "source_boundary":"Independent readback overlay. The original parent runtime-build.json remains evidence of that parent."}
    out = private/"semantic"
    out.mkdir(exist_ok=False)
    WRITE(out/"source-snapshot.public.json.gz",signature)
    WRITE(out/"semantics-differences.public.json.gz", {"all_field_differences":diffs})
    WRITE(out/"semantics-inputs.public.json",locked)
    semantic = {"schema":"g1.radial-native-complete-equivalence.v1","timing_plan_sha256":fixture.PLAN,"baseline_runtime_build_sha256":fixture.BASELINE,
                "detector_files_sha256":CANDIDATE,"all_candidate_outputs_byte_equivalent":exact,
                "independently_implemented_native_scorer_closed_at_1e_minus_10_m":independently_closed,
                "eligible": bool(exact and independently_closed and q["eligible"] and gate["all_historical_gates"]),
                "sections":counts, "native_independent_scorer_sections":native_sections,
                "d02":per_batch,"radial_static":screen_summary, "historical_gates":gate["gates"], "source_context_controls":collision,
                "native_disagreement_refusal_m":conflict["result"]["target_disagreement_m"],"native_disagreement_reason":conflict["result"]["reason"],
                "blind_pids":seal["pids"],"sealed_before_truth":seal["products_identical"],"new_formal_trials":0,
                "canonical_comparison":"Sorted-key JSON with list order, scalar types, finite round-trip floats and signed zero. Only cross-implementation native scorer rigid XYZ is separately assessed at 1e-10 m."}
    WRITE(out/"semantic-equivalence.public.json",semantic)
    print({k:(v["records"],v["scalar_differences"]) for k,v in counts.items()},flush=True)
    print("SOFTWARE ELIGIBLE",semantic["eligible"],flush=True)


if __name__=="__main__":
    main(*map(Path,sys.argv[1:]))

