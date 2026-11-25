"""Recompute native frame observations and conservative history bounds without simulation labels."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BASE = Path("experiments/results/g1-complete-cv-repair-20261125")
RAW = BASE / "temporal-subpixel-01"
CASE = BASE / "batches/train-full-04/cvfix-t02/instance"
BAND = 0.004
QUERY = (171, 122)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(path, expected):
    assert digest(path) == expected
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    row = json.loads(data)
    depth = np.frombuffer(base64.b64decode(row["depth_float32_base64"]),"<f4").reshape(240, 320)
    return row, depth


def subset(arr, uv, radius):
    u,v=uv
    return arr[v-radius:v+radius+1,u-radius:u+radius+1]


def history():
    index = json.loads((CASE/"pixel-index.json").read_bytes())["frames"]
    receipt = json.loads((CASE/"acquisition-seal.json").read_bytes())
    assert receipt["index_sha256"] == digest(CASE/"pixel-index.json")
    target = next(e for e in index if e["frame_id"]=="rgbd-eb76862a12354f5cba8f681a74a81f88")
    fr,depth = decode(CASE/target["file"], target["file_sha256"])
    required = float(depth[QUERY[1],QUERY[0]])
    out = {}
    for uv in (QUERY,(148,147),(180,145)):
        for radius in (1,2):
            entries=[]
            for e in index:
                if e["physics_step"]>=target["physics_step"]: continue
                frame,z=decode(CASE/e["file"],e["file_sha256"])
                assert frame["checksum_sha256"]==e["checksum_sha256"]
                local=subset(z,uv,radius)
                if (local>0).all():
                    entries.append((float(local.min()),float(np.ptp(local)),e["frame_id"],e["physics_step"]))
            best=max(entries,key=lambda a:a[0])
            first=entries[0]
            out[f"{uv[0]},{uv[1]} radius={radius}"]=dict(best_min_depth_m=best[0],best_neighborhood_spread_m=best[1],
                      best_frame=best[2],best_step=best[3],num_observations=len(entries),first_min_depth_m=first[0],
                      first_spread_m=first[1],best_minus_query_m=best[0]-required if uv==QUERY else None,
                      best_after_one_band_minus_query_m=best[0]-BAND-required if uv==QUERY else None)
    return dict(index_sha256=digest(CASE/"pixel-index.json"),index_entries=len(index),target_file_sha256=target["file_sha256"],
                target_uv=QUERY,target_depth_m=required,strictly_earlier_only=True,interval_direction="optical z",
                sampled_neighborhoods=out,certified_full_foreign_object_volume=False)


def read_pairs():
    reg=json.loads((HERE/"optical-diagnostic-registration.json").read_bytes())
    idx=json.loads((RAW/"index.json").read_bytes())
    assert idx["registration_sha256"]==digest(HERE/"optical-diagnostic-registration.json")
    assert len(idx["generated_files"])==len(reg["rows"])*len(reg["seeds"])
    items={(r["id"],r["seed"]):r for r in idx["generated_files"]}
    calib=BASE/"calibration-gpu-01"
    m=json.loads((calib/"manifest.json").read_bytes())
    bg=np.load(calib/"table.npy",allow_pickle=False)
    assert digest(calib/"table.npy")==m["maps"]["table"]["depth_sha256"]
    pairs=[]
    for case in reg["rows"]:
        for seed in reg["seeds"]:
            row=items[case["id"],seed]
            clean=items[case["group"]+"-clean-0",seed]
            f,z=decode(RAW/row["file"],row["file_sha256"]); cf,cz=decode(RAW/clean["file"],clean["file_sha256"])
            assert f["checksum_sha256"]==row["checksum"] and f["frame_id"]==row["frame_id"] and f["sim_time_s"]==0.
            hits=(bg>0)&(z>0)&(bg-z>2*BAND)
            missing=(bg>0)&(z<=0)
            def rgb(raw):
                return np.asarray(Image.open(io.BytesIO(base64.b64decode(raw["rgb_png_base64"]))).convert("RGB"))
            color=np.any(rgb(f)!=rgb(cf),axis=2)
            dz=cz-z
            local=subset(hits,case["uv"],2)
            pairs.append(dict(id=case["id"],seed=seed,full_different_depth_pixels=int((dz!=0).sum()),
                              full_different_rgb_pixels=int(color.sum()),max_nearer_than_matched_clean_mm=float(dz.max()*1000),
                              whole_known_table_near_pixels=int(hits.sum()),whole_known_table_missing=int(missing.sum()),
                              local_near_pixels=int(local.sum()),local_max_nearer_than_clean_mm=float(subset(dz,case["uv"],2).max()*1000),
                              local_missing=int(subset(missing,case["uv"],2).sum()),
                              local_all_known=bool((subset(bg,case["uv"],2)>0).all())))
    return dict(raw_index_sha256=digest(RAW/"index.json"),renderer=idx["renderer"],samples=idx["offsamples"],
                camera_sha256=idx["native_camera_sha256"],source_sha256=idx["source_sha256"],rows=pairs,physics_steps=0,
                runtime_isolation_verified=False,hardware_actions=0,formal_trials=0,production_gate_unchanged=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["history","pairs"])
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    result=history() if args.mode=="history" else read_pairs()
    payload=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n"
    path=HERE/(args.mode+"-diagnostic.public.json")
    if args.verify:
        assert path.read_text()==payload
    else:
        path.open("x").write(payload)
    print(digest(path))

if __name__=="__main__":
    main()
