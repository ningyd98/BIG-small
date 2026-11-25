"""Independent depth decoder and outcomes, including best possible cross-frame fusion."""
import base64
import collections
import gzip
import hashlib
import io
import json
import struct
from pathlib import Path

from PIL import Image

HERE=Path(__file__).resolve().parent
BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
RAW=BASE/"temporal-subpixel-01"
CASE=BASE/"batches/train-full-04/cvfix-t02/instance"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def decoded(p, expected):
    assert sha(p)==expected
    source=p.read_bytes()
    packet=json.loads(gzip.decompress(source) if p.suffix==".gz" else source)
    return packet,base64.b64decode(packet["depth_float32_base64"])


def main():
    registration=json.loads((HERE/"optical-diagnostic-registration.json").read_bytes())
    source=json.loads((RAW/"index.json").read_bytes())
    rows={(r["id"],r["seed"]):r for r in source["generated_files"]}
    first_reader=json.loads((HERE/"pairs-diagnostic.public.json").read_bytes())
    first_flags={(r["id"],r["seed"]):r for r in first_reader["rows"]}
    unobservable=[]
    for case in registration["rows"]:
        identical=0
        for seed in registration["seeds"]:
            row=rows[case["id"],seed]
            clean=rows[case["group"]+"-clean-0",seed]
            assert sha(RAW/(case["id"]+".xml"))==row["xml_sha256"]
            f,z=decoded(RAW/row["file"],row["file_sha256"])
            c,cz=decoded(RAW/clean["file"],clean["file_sha256"])
            color=lambda fr:Image.open(io.BytesIO(base64.b64decode(fr["rgb_png_base64"]))).convert("RGB").tobytes()
            eq_rgb=color(f)==color(c)
            assert eq_rgb==(first_flags[case["id"],seed]["full_different_rgb_pixels"]==0)
            assert (z==cz)==(first_flags[case["id"],seed]["full_different_depth_pixels"]==0)
            identical+=eq_rgb and z==cz
        if identical==len(registration["seeds"]) and case["width_mm"]>0:
            unobservable.append(case["id"])

    entries=json.loads((CASE/"pixel-index.json").read_bytes())["frames"]
    best={}
    for row in entries:
        if row["physics_step"]>=2112:continue
        f,z=decoded(CASE/row["file"],row["file_sha256"])
        assert f["checksum_sha256"]==row["checksum_sha256"]
        for y in range(121,124):
            for x in range(170,173):
                p=(x,y)
                v=struct.unpack_from("<f",z,4*(y*320+x))[0]
                if p not in best or v>best[p][0]:
                    best[p]=(v,row["physics_step"],row["frame_id"])
    t=next(row for row in entries if row["frame_id"]=="rgbd-eb76862a12354f5cba8f681a74a81f88")
    _,z=decoded(CASE/t["file"],t["file_sha256"])
    target=struct.unpack_from("<f",z,4*(122*320+171))[0]
    least=max_depth_limit=min(v[0] for v in best.values())
    weaker=[list(k) for k,v in best.items() if v[0]<target]
    summary=dict(indistinguishable_even_on_clean_table=unobservable,
      input_index_sha256=sha(RAW/"index.json"),source_sha256=sha(Path(__file__)),
      registered_minimum_shape_certified=False,closed_fixture_image_only_exception=False,open_or_unverified_epoch_exception=False,
      clean_and_physical_solid_independent_capture_pairs=len(rows)-2*len(registration["seeds"]),
      clean_and_blocked_reference_witnesses=2,unverified_native_production_isolation=True,
      empirical_gate="any observed local or other unregistered nearer return keeps original guard; clean sampled rays alone do not certify the subpixel volume",
      cross_frame_per_pixel_max_depth=[dict(uv=list(k),maximum_m=v[0],step=v[1],frame_id=v[2]) for k,v in best.items()],
      optimistic_minimum_of_maxima_m=least,current_query_m=target,insufficient_uv=weaker,
      optimistic_gap_m=least-target,gap_after_4mm_band_m=least-.004-target,
      scope="3x3 sensor-neighborhood test at common queried depth; not proof every failing ray actually belongs to the exact physical hazard volume. No complete 3-D hazard-volume proof available.")
    text=json.dumps(summary,indent=2,sort_keys=True)+"\n"
    path=HERE/"cold-coverage.public.json"
    if path.exists():assert path.read_text()==text
    else:path.open("x").write(text)
    print(sha(path))

if __name__=="__main__":
    main()
