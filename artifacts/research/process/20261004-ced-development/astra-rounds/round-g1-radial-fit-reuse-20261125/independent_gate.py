"""Exercise the registered pixel and consumer gates using the sealed radial replay inputs."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROUND = Path(__file__).resolve().parent
V1 = ROUND.parent / "round-g1-radial-native-timing-20261125"
sys.path.insert(0, str(V1))
import semantic_release as checks
import semantic_replay as fixture

ROOT = fixture.ROOT
replay = fixture.replay
READ, WRITE, CHECK, SHA = fixture.READ, fixture.WRITE, fixture.CHECK, fixture.SHA
PLAN = "70d6f895fa88b80d0e5b2415c5cb51b63f39f17abe53252da2eb782be5535c5f"
V1_GATE = "284c149700f70b050fe92ddfc1d222fd105f229993becf0b8af1a78bc6cd2120"
SCOPES = ("dynamic", *fixture.STATIC)
VISION = "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169"
BASELINE = fixture.BASELINE
BASE_TREE = fixture.OLD_TREE
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")


def pair_receipt(rows):
    CHECK(len(rows) == 2 and len({r["pid"] for r in rows}) == 2 and
          all(r["exit_code"] == 0 and r["sha256"] for r in rows) and
          rows[0]["sha256"] == rows[1]["sha256"], "independent workers failed or produced different bytes")
    return rows[0]["sha256"]


def frozen_input(path):
    if path.parts[0] in {"scripts", "tests"}:
        return ROUND / "readback-inputs-v1" / path
    if path.name in {"pixel_residual_profile.py", "remaining-pixel-profile.public.json"}:
        return ROUND / "frozen-plan-inputs" / path.name
    return ROOT / path


def copy_new(origin, dest):
    with origin.open("rb") as src, dest.open("xb") as out:
        shutil.copyfileobj(src, out)
    CHECK(SHA(origin) == SHA(dest), "copy differs: " + str(dest))


def prepare(work, packets):
    plan = READ(ROUND/"plan.json", PLAN)
    CHECK(plan["native_baseline_generation"]==BASELINE and SHA(ROUND/"plan.md")==plan["plan_md_sha256"],
          "wrong physical baseline or specification")
    old_gate = READ(V1/"replay-release.public.json",V1_GATE)
    old_inputs = READ(V1/"semantics-inputs.public.json", plan["inputs_sha256"][fixture.rel(V1/"semantics-inputs.public.json")])
    bindings = {}
    def record(path,digest):
        CHECK(SHA(path) == digest, "unmatched input: " + str(path))
        bindings[fixture.rel(path)] = digest
    for k,v in plan["inputs_sha256"].items():
        record(frozen_input(Path(k)),v)
    supplemental_names = {"pixel_residual_profile.py":"solver_witness.py",
                          "remaining-pixel-profile.public.json":"solver-witness.public.json"}
    for k,v in plan["supplementary_worktree_inputs_sha256"].items():
        record(V1/supplemental_names[Path(k).name],v)
    for k,v in old_gate["input_artifacts_sha256"].items():
        path = Path(k)
        record(frozen_input(path) if k in plan["inputs_sha256"] else ROOT/path, v)
    record(V1/"replay-release.public.json",V1_GATE)
    for name in ("plan.json","plan.md"):
        record(ROUND/name,SHA(ROUND/name))
    for package,key in ((replay.PACKETS,replay.INDEX_SHA), *((packets/m,old_inputs["index_sha256"][m]) for m in SCOPES)):
        lock = replay.lock_packets(package,key)
        expected = 778 if package == replay.PACKETS else 335 if package.name=="dynamic" else 22
        CHECK(lock["frames_byte_verified"]==expected,"mismatched original pixel packets")
    work.mkdir(parents=True,exist_ok=False)
    for mode in SCOPES:
        p = V1/("baseline-"+mode+".public.json.gz")
        record(p, old_gate["input_artifacts_sha256"][fixture.rel(p)])
        copy_new(p,work/("baseline-"+mode+".json.gz"))
    record(V1/"full-historical-baseline.public.json.gz",old_inputs["old_complete_historical_bytes_sha256"])
    WRITE(work/"inputs.json", {**old_inputs, "timing_plan_sha256":PLAN,"previous_timing_plan_sha256":fixture.PLAN,
                               "previous_software_release_sha256":V1_GATE,"input_artifacts_sha256":bindings})
    print("Input bytes verified",len(bindings),flush=True)


def freeze(work, grid_sha):
    CHECK(len(grid_sha)==64 and grid_sha!=READ(V1/"replay-release.public.json",V1_GATE)["detector_files_sha256"][fixture.DETECTORS[0]],
          "new source has not been independently frozen")
    detector = dict(zip(fixture.DETECTORS,(grid_sha,VISION),strict=True))
    CHECK(all(SHA(ROOT/k)==v for k,v in detector.items()),"requested candidate SHA does not match either source")
    tree = work/"observer-source"
    shutil.copytree(BASE_TREE,tree)
    shutil.copyfile(ROOT/fixture.DETECTORS[0],tree/fixture.DETECTORS[0])
    previous, fresh = checks.snapshot(BASE_TREE), checks.snapshot(tree)
    CHECK(previous.keys()==fresh.keys() and [k for k in previous if previous[k]!=fresh[k]]==[fixture.DETECTORS[0]] and
          all(fresh[k]==v for k,v in detector.items()),"candidate contains another dependency change")
    WRITE(work/"candidate-sources.json",{"schema":"g1.fit-reuse.observer-source.v1","plan_sha256":PLAN,
          "physical_baseline_sha256":BASELINE,"detector_files_sha256":detector,
          "candidate_files_sha256":fresh,"baseline_manifest_sha256":SHA(fixture.OLD_TREE/"runtime-build.json")})
    print("Frozen observer",len(fresh),grid_sha,tree,flush=True)


def paired(work, name, make_command, expected):
    output = work/"independent"
    children=[]
    for lane in ("one","two"):
        product = output/(name+"-"+lane+".json.gz")
        args = make_command(product)
        proc = subprocess.Popen([sys.executable,"-I","-B",*map(str,args)],cwd=work,
                                env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        children.append((proc,product))
    receipts=[]
    for proc, product in children:
        stdout,stderr = proc.communicate()
        receipts.append({"pid":proc.pid,"exit_code":proc.returncode,"stdout":stdout,"stderr":stderr,"file":product.name,
                         "sha256":SHA(product) if proc.returncode==0 else None})
    WRITE(output/(name+"-processes.json"),receipts)
    signed=pair_receipt(receipts)
    CHECK(children[0][1].read_bytes()==children[1][1].read_bytes(),"independent packet bytes differ")
    record=READ(children[0][1],signed)
    CHECK(set(record["detector_files_sha256"])==set(fixture.DETECTORS) and len(record["frames"])==expected,
          "wrong detector or frame group")
    outfile = work/("historical-full-candidate.json.gz" if name=="historical" else "candidate-"+name+".json.gz")
    copy_new(children[0][1],outfile)
    return {"records":expected,"sha256":signed,"worker_receipts":receipts,"controls":len(record.get("controls",{}))}


def context_worker(tree, packets, digest, output):
    packets,tree,output=(p.resolve() for p in (packets,tree,output))
    replay.restrict_worker(packets,tree,output)
    sys.path[:0]=[str(tree),str(tree/"src")]
    from scripts.graduation import g1_visibility_vision as vision
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.g1_formal_runtime import bind_scene
    replay.cv2.setNumThreads(1)
    views={}
    for token,packet in READ(packets/"index.json",digest).items():
        if len(packet["frames"])!=130:
            continue
        g=packet["geometry"]
        who="radial" if g["development_dual"].get("radial_offset_mm")==15 else "parent"
        row=packet["frames"][-2]
        CHECK(row["physics_step"]==1088,"unknown context control frame")
        f=frame_from_row(packets/token,row,packet["episode"],packet["scene"],g)
        views[who]=(f,g)
    CHECK(set(views)=={"parent","radial"},"unknown mount")
    results=[]
    for view,geo in (("radial","radial"),("radial","parent"),("radial","radial"),
                     ("parent","parent"),("radial","radial")):
        f = views[view][0]
        g = views[geo][1]
        with bind_scene(f.scene_id):
            value = vision.measure_frame(f,g)
        CHECK(value["registration_id"]==g["registration_id"] and value["asset_sha256"]==g["pose_marker"]["marked_asset_sha256"]
              and value["frame_id"]==f.frame_id and value["checksum"]==f.checksum_sha256,"unbound register/packet")
        results.append(value)
    WRITE(output,{"frames":{str(i):row for i,row in enumerate(results)},"index_sha256":digest,
                  "detector_files_sha256":{k:SHA(tree/k) for k in fixture.DETECTORS}})


def run(work, packets):
    expected = READ(work/"candidate-sources.json")["detector_files_sha256"]
    tree=work/"observer-source"
    CHECK(all(SHA(tree/k)==v==SHA(ROOT/k) for k,v in expected.items()),"candidate changed after freeze")
    source = READ(work/"inputs.json")
    receipts={}
    (work/"independent").mkdir()
    # Two fresh isolated interpreters for every full native result, separately from the two geometric readers.
    def equivalent_scope(name):
        if name=="historical":
            return paired(work,name,lambda p:[fixture.REFERENCE_SCRIPT,"capture","historical",tree,p],778)
        if name=="context":
            return paired(work,name,lambda p:[__file__,"context",tree,packets/"dynamic",source["index_sha256"]["dynamic"],p],5)
        return paired(work,name,lambda p:[V1/"semantic_replay.py","capture",packets/name,source["index_sha256"][name],tree,p],
                      335 if name=="dynamic" else 22)
    def geometric():
        subprocess.run([sys.executable,str(replay.SOURCE),"blind",str(replay.PACKETS),replay.INDEX_SHA,str(work/"blind"),
                        "--runtime",str(tree)],cwd=ROOT,env=ENV,check=True)
        subprocess.run([sys.executable,str(replay.SOURCE),"qualify",str(work)],cwd=ROOT,env=ENV,check=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        legacy=pool.submit(geometric)
        futures={k:pool.submit(equivalent_scope,k) for k in ("historical",*SCOPES,"context")}
        for k,f in futures.items():
            receipts[k]=f.result()
        legacy.result()
    for record in receipts.values():
        one=READ(work/"independent"/record["worker_receipts"][0]["file"],record["sha256"])
        CHECK(one["detector_files_sha256"]==expected,"unrelated independent code generation")
    old_context=work/"context-physical-baseline.json.gz"
    subprocess.run([sys.executable,"-I","-B",str(Path(__file__).resolve()),"context",str(BASE_TREE),str(packets/"dynamic"),
                    source["index_sha256"]["dynamic"],str(old_context)],env=ENV,cwd=work,check=True)
    frozen,new=(READ(p)["frames"] for p in (old_context,work/"candidate-context.json.gz"))
    CHECK(fixture.prior.canonical(frozen)==fixture.prior.canonical(new),"mount switch differs from physical baseline")
    a,b,c,d,e=(new[str(i)] for i in range(5))
    correction=math.dist(a["grasp_world_m"],b["grasp_world_m"])
    CHECK(a==c==e and a["selected_id"]==b["selected_id"]==7 and a["checksum"]==b["checksum"] and
          a["registration_id"]!=b["registration_id"] and a["asset_sha256"]!=b["asset_sha256"] and
          abs(correction-.015)<=1e-10 and d["observed_ids"]==[7,28] and d["selected_id"] is None and not d["usable"],
          "wrong mount, stale target or old ambiguous frame was reused")
    WRITE(work/"full-blind-seals.json",{"independent_scope_receipts":receipts,"same_frame_changed_registration_tcp_delta_m":correction,
          "physical_baseline_context_sha256":SHA(old_context),"candidate_context_sha256":SHA(work/"candidate-context.json.gz"),
          "historical_rigid_seal_sha256":SHA(work/"blind/seal.json"), "source_manifest_sha256":SHA(work/"candidate-sources.json")})
    print("Independent software reads complete",flush=True)


def compare(work):
    checks.CANDIDATE = READ(work/"candidate-sources.json")["detector_files_sha256"]
    fixture.PLAN = PLAN
    checks.main(work,work/"observer-source",V1/"full-historical-baseline.public.json.gz")


if __name__=="__main__":
    mode,*args = sys.argv[1:]
    if mode=="prepare":
        prepare(*map(Path,args))
    elif mode=="freeze":
        freeze(Path(args[0]),args[1])
    elif mode=="context":
        context_worker(Path(args[0]),Path(args[1]),args[2],Path(args[3]))
    elif mode=="run":
        run(*map(Path,args))
    elif mode=="compare":
        compare(Path(args[0]))
    else:
        raise SystemExit("unknown operation")

