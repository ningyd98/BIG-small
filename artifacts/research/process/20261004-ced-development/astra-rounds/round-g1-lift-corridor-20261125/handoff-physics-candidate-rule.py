"""Apply the post-fit frozen, camera-only rank and its paired baseline on four new physical courses."""
import argparse
import fcntl
import importlib.util
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('selection',HERE/'handoff-physics-candidates.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def choose(center):
    reg=s.io.read(HERE/'handoff-physics-candidate-rule-freeze.public.json');r=math.hypot(*center[:2]);shift=min((0,4),key=lambda k:abs(r+k/1000-reg['registered_radius_m']));return 'rad%+d_h18'%shift

def main():
    opts=argparse.ArgumentParser();opts.add_argument('--root',type=Path,required=True);opts.add_argument('--out',type=Path,required=True);opts.add_argument('--mode',choices=('prepare','simulate'),required=True);opts.add_argument('--case',action='append',required=True);a=opts.parse_args();root=a.root.resolve();out=a.out.resolve();freeze=HERE/'handoff-physics-candidate-rule-freeze.public.json';r=s.io.read(freeze)
    if r['fit_results_sha256']!=s.io.sha(HERE/'handoff-physics-candidate-fit.public.json') or any(n not in r['locked_unseen'] for n in a.case):raise ValueError('foreign candidate rule or physical data')
    if a.mode=='prepare':
        with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for name in a.case:s.prepare(root,out,name)
    else:
        for name in a.case:
            prefix=out/'prefix'/name/'prefix.json';center=s.io.read(prefix)['above']['observed_center_m'];chosen=choose(center)
            decision=out/'prefix'/name/'frozen-choice.json';s.io.write(decision,dict(case=name,freeze_sha256=s.io.sha(freeze),prefix_sha256=s.io.sha(prefix),selected_id=chosen,measured_center_m=center));s.simulate(root,out,name,[r['comparator'],chosen])

if __name__=='__main__':main()
