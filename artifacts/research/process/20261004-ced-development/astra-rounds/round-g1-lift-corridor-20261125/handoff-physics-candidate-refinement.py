"""Refine only the physical APPROACH target while preserving the registered native controller."""
import argparse
import fcntl
import importlib.util
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate_engine',HERE/'handoff-physics-candidates.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def target(center,cand):
    c=np.asarray(center,float);r=c[:2]/np.linalg.norm(c[:2]);t=np.array([-r[1],r[0]])
    return np.r_[c[:2]+(cand['radial_mm']*r+cand.get('tangential_mm',0)*t)/1000,c[2]+cand['height_above_estimated_center_mm']/1000]

def main():
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--case',action='append',required=True);a.add_argument('--mode',choices=['fit','prepare-held','validate'],required=True);a.add_argument('--freeze',type=Path);ns=a.parse_args();root=ns.root.resolve();out=ns.out.resolve();extra=s.io.read(HERE/'handoff-physics-candidate-refinement-design.json');s.DESIGN['candidates']+=extra['candidate_set'];s.DESIGN['cases']+=extra['validation_cases'];s.target=target
    if ns.mode=='fit':
        for case in ns.case:
            if case not in extra['fixed_optical_fit_prefix_inputs'] or s.io.sha(out/'prefix'/case/'prefix.json')!=extra['fixed_optical_fit_prefix_inputs'][case]:raise ValueError('unbound fit pose')
            s.simulate(root,out,case,[d['id'] for d in extra['candidate_set']])
        return
    if ns.freeze is None:raise ValueError('unseen study requires locked fit')
    freeze=s.io.read(ns.freeze)
    if freeze['refinement_registration_sha256']!=s.io.sha(HERE/'handoff-physics-candidate-refinement-design.json') or not freeze['selected_id']:raise ValueError('no admissible frozen candidate')
    for c in ns.case:
        if c not in {i['name'] for i in extra['validation_cases']}:raise ValueError('foreign unseen case')
    if ns.mode=='prepare-held':
        with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for c in ns.case:s.prepare(root,out,c)
    else:
        for c in ns.case:s.simulate(root,out,c,['rad+0_h10',freeze['selected_id']])

if __name__=='__main__':main()
