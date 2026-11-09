import ast
import importlib.util
import sys
from pathlib import Path
import pytest
HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE.parent / "round505-ordered-small-vlm-screen-20261109/implementation/score_candidate.py"
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("score_modality_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tree = ast.parse(SOURCE.read_text())
score = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "score")
start = next(i for i,n in enumerate(score.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id == "positive")
end = next(i for i,n in enumerate(score.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id == "json_summary")
block = ast.Module(body=score.body[start:end], type_ignores=[])
result_node = next(n.value for n in score.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id == "result")
latency_expr = next(v for k,v in zip(result_node.keys,result_node.values) if isinstance(k,ast.Constant) and k.value == "latency")


def fixture():
    cases = {f"case-{i:04}": {"id":f"case-{i:04}", "kind":"positive" if i<=12 else "absent"} for i in range(1,17)}
    rows=[]
    for mode,warm,cold in [("box",1,10),("point",2,20)]:
        for i,key in enumerate(cases):
            for kind in ("target","destination"):
                absent=i>=12 and kind=="target"
                rows.append({"id":key,"query":kind,"stage":"NATIVE_RGB","repeat":False,
                             "end_to_end_s":cold if i==0 and kind=="target" else warm,
                             "modes":{mode:{"status":"REFUSAL" if absent else "DETECTED", "hit":(not absent and (mode=="box" or i<6)), "explicit_no_detection":absent}}})
        for _ in range(2):
            rows.append({"id":"case-0001","query":"target","stage":"NATIVE_RGB","repeat":True,"end_to_end_s":3 if mode=="box" else 4,"modes":{mode:{"hit":False,"status":"INVALID"}}})
    return cases,rows


def compute(cases,rows):
    scope={**module.__dict__,"cases":cases,"rows":rows}
    exec(compile(block,str(SOURCE),"exec"),scope)
    return scope["summary"],eval(compile(ast.Expression(latency_expr),str(SOURCE),"eval"),scope)


def test_production_multi_mode_counts_and_latency():
    cases,rows=fixture();summary,latency=compute(cases,rows)
    assert summary["box"]["joint_hits"]==12 and summary["point"]["joint_hits"]==6
    assert summary["box"]["coverage"]==summary["point"]["coverage"]==32
    modes=latency["native_by_mode"]
    for mode,warm,repeat in [("box",1,3),("point",2,4)]:
        assert modes[mode]["warm_excluding_first"]=={"n":31,"p50_s":warm,"p90_s":warm}
        assert modes[mode]["fixed_repetitions"]=={"n":2,"p50_s":repeat,"p90_s":repeat}
    assert modes["box"]["first_is_process_cold"] is True
    assert modes["point"]["first_is_process_cold"] is False
    assert modes["point"]["cold_first_request_s"] is None


def test_absent_mode_does_not_inflate_coverage():
    cases,rows=fixture();rows.pop(0);summary,_=compute(cases,rows)
    assert summary["box"]["coverage"]==31 and summary["point"]["coverage"]==32
    assert summary["box"]["screening_signal"] is False


def test_reversed_order_and_json_are_isolated():
    cases,rows=fixture();first,_=compute(cases,rows)
    reordered=rows[34:]+rows[:34]+[{"stage":"JSON_RGB","repeat":False,"end_to_end_s":900}]
    summary,_=compute(cases,reordered)
    assert summary==first


def test_shared_multimode_observation_keeps_one_call():
    cases,rows=fixture();rows=rows[:34]
    for row in rows:row["modes"]["mask"]=dict(row["modes"]["box"])
    summary,latency=compute(cases,rows)
    assert len(rows)==34
    assert summary["box"]==summary["mask"]
    assert latency["native_by_mode"]["box"]==latency["native_by_mode"]["mask"]
