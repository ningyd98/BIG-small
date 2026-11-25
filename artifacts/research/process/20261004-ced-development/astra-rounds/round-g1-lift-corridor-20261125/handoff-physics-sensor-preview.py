"""Prepare and validate discrete native-course preview from measured RGB-D/robot/drive state."""
import argparse
import fcntl
import importlib.util
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('refined',HERE/'handoff-physics-candidate-refinement.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);s=module.s;io=s.io
EXTRA=io.read(HERE/'handoff-physics-sensor-preview-preregistration.json');BASE=io.read(HERE/'handoff-physics-candidate-refinement-design.json');s.DESIGN['candidates']+=BASE['candidate_set'];s.DESIGN['cases']+=BASE['validation_cases']+EXTRA['extra_fit_poses'];s.target=module.target

def prep(root,out,cases):
    with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for n in cases:s.prepare(root,out,n)

def features(out,case):
    p=out/'prefix'/case;v=io.read(p/'prefix.json')['above']['observed_center_m'];ret=np.load(p/'return.npz');q,dq=ret['q'],ret['qvel'];cmd=ret['command_q'];
    # Center anchors the candidate in the sensed cell; a distinct block independently captures
    # arm configuration, inherited motion, target residual and open-finger motion.
    return [np.asarray(v),q[:7],dq[:7],cmd-q[:7],q[7:9],dq[7:9]]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--mode',choices=['prepare-fit','simulate-fit','fit-freeze','prepare-validation','validate'],required=True);ap.add_argument('--case',action='append');a=ap.parse_args();root=a.root.resolve();out=a.out.resolve();cases=a.case or [c['name'] for c in EXTRA['extra_fit_poses']];study=HERE/'handoff-physics-sensor-preview-freeze.public.json'
    if a.mode in ('prepare-fit','simulate-fit'):
        if not set(cases)<={c['name'] for c in EXTRA['extra_fit_poses']}:raise ValueError('foreign extra fit case')
        if a.mode=='prepare-fit':prep(root,out,cases)
        else:
            for n in cases:s.simulate(root,out,n,[EXTRA['comparison'],*EXTRA['candidates']])
    elif a.mode=='fit-freeze':fit(out,study)
    else:
        fr=io.read(study)
        if fr['prospective_design_sha256']!=io.sha(HERE/'handoff-physics-sensor-preview-preregistration.json') or not set(cases)<={c['name'] for c in BASE['validation_cases']}:raise ValueError('unfrozen heldout')
        if a.mode=='prepare-validation':prep(root,out,cases)
        else:
            for n in cases:
                x=features(out,n);decision=rank(fr,[v.tolist() for v in x]);rec=out/'prefix'/n/'selection.json';io.write(rec,dict(case=n,freeze_sha256=io.sha(study),selection=decision));fixed=io.read(HERE/'handoff-physics-refinement-fixed-freeze.public.json')['selected_id'];choices=[EXTRA['comparison'],fixed];
                if decision['choice'] and decision['choice'] not in choices:choices.append(decision['choice'])
                s.simulate(root,out,n,choices)


def distance(banks,point,scales):
    # Each sensor block has equal weight independent of channel count.
    return np.sqrt(sum(np.mean(((np.asarray(bank)-z)/scale)**2,axis=1) for bank,z,scale in zip(banks,point,scales,strict=True))/len(banks))


def local(bank,indices,d,candidate):
    y=np.array(bank['margins'][candidate]);flags=np.asarray(bank['success'][candidate]);top=indices[np.argsort(d[indices])[:3]];w=1/np.maximum(d[top],1e-6);avg=float(w@y[top]/sum(w));return top,avg,float(y[top].min()),bool(flags[top].all())


def rank(bank,x):
    d=distance(bank['blocks'],x,[np.asarray(z) for z in bank['scales']]);idx=np.arange(len(d));scores={};
    for c in bank['candidates']:
        near,avg,low,ok=local(bank,idx,d,c);v=min(avg-bank['overprediction_m'][c],low);scores[c]=dict(neighbors=[bank['names'][j] for j in near],nearest=float(d[near[0]]),estimate_m=avg,lower_empirical_margin_m=v,all_local_feasible=ok)
    supported=[c for c,r in scores.items() if r['all_local_feasible'] and r['lower_empirical_margin_m']>0 and r['nearest']<=bank['max_within_fit_nearest']];return dict(choice=min(supported,key=lambda c:(-scores[c]['lower_empirical_margin_m'],c)) if supported else None,all_scores=scores)


def fit(out,path):
    names=sorted([d.name for d in (out/'prefix').glob('fit*')]+[c['name'] for c in EXTRA['extra_fit_poses']]);blocks=[np.stack(v) for v in zip(*[features(out,n) for n in names],strict=True)];floors=[np.array([.003,.003,.002]),.015,.008,.001,.00025,.00005];scales=[np.maximum(np.ptp(a,axis=0)/2,f) for a,f in zip(blocks,floors,strict=True)];
    bank=dict(names=names,candidates=EXTRA['candidates'],input_schema=['optical_xyz_m','arm_q_rad','arm_dq_rad_s','effective_target_minus_q_rad','finger_q_m','finger_dq_m_s'],blocks=[z.tolist() for z in blocks],scales=[z.tolist() for z in scales],margins={},success={},fit_sha256={},overprediction_m={},prospective_design_sha256=io.sha(HERE/'handoff-physics-sensor-preview-preregistration.json'))
    for c in EXTRA['candidates']:
        margins=[];ok=[];sources=[]
        for n in names:
            p=out/'courses'/n/c/'result.json';a=io.read(p);clock=a['source_return_step'];elapsed=[]
            for stage in a['actions']:elapsed.append((stage['end']-clock)/240);clock=stage['end']
            margins.append(.001-a['lift_peak_lateral_m'] if a['lift_peak_lateral_m'] is not None else -.001);ok.append(a['eligible'] and max(elapsed)<=8);sources.append(io.sha(p))
        bank['margins'][c]=margins;bank['success'][c]=ok;bank['fit_sha256'][c]=sources
    all_i=np.arange(len(names));ds=[distance(blocks,[block[i] for block in blocks],scales) for i in all_i];bank['max_within_fit_nearest']=max(min(d[all_i!=i]) for i,d in enumerate(ds));bank['loo_error_source']={}
    for c in EXTRA['candidates']:
        errors=[]
        for i,d in enumerate(ds):
            _,avg,_,_=local(bank,all_i[all_i!=i],d,c);errors.append(avg-bank['margins'][c][i])
        bank['overprediction_m'][c]=max(0,max(errors));bank['loo_error_source'][c]=names[int(np.argmax(errors))]
    if any((out/'prefix'/c['name']).exists() for c in BASE['validation_cases']):raise ValueError('fresh validation already open')
    io.write(path,bank)

if __name__=='__main__':main()
