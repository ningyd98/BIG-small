import ast
import importlib.util
import sys
from pathlib import Path
from pip._vendor.resolvelib.structs import build_iter_view
from pip._vendor.resolvelib import Resolver
from pip._vendor.resolvelib.reporters import BaseReporter
from packaging.requirements import Requirement

SOURCE=Path(__file__).resolve().parents[2]/"round515-dlm-serving-stack-clarification-20261109/implementation/resolve_official_wheels.py"
spec=importlib.util.spec_from_file_location("r517_provider_test",SOURCE);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def provider(conflict=False):
    obj=module.MetadataProvider.__new__(module.MetadataProvider);obj.sources={};obj.details={};calls=[]
    def get(name,version=None):
        calls.append((name,version))
        versions=["9.16.0.29"] if name=="nvidia-cudnn-cu12" else ["1.0.0","2.0.0","3.0.0"]
        if version is None:return {"releases":{v:[{"yanked":False}] for v in versions}}
        deps=["leaf==2.0.0"] if conflict and name=="demo" and version=="3.0.0" else []
        return {"info":{"requires_python":">=3.9","requires_dist":deps},"urls":[{"filename":name.replace('-','_')+"-"+version+"-py3-none-any.whl","packagetype":"bdist_wheel","yanked":False}]}
    obj.get=get
    return obj,calls


def test_factory_and_first_candidate_are_lazy():
    p,calls=provider();factory=p.find_matches("demo",{"demo":[Requirement("demo")]},{"demo":[]})
    assert callable(factory)
    view=build_iter_view(factory);assert not any(v is not None for n,v in calls)
    assert next(iter(view)).version=="3.0.0"
    assert [v for n,v in calls if v is not None]==["3.0.0"]
    assert bool(view) and next(iter(view)).version=="3.0.0"
    assert [v for n,v in calls if v is not None]==["3.0.0"]
    assert [c.version for c in view]==["3.0.0","2.0.0","1.0.0"]


def test_actual_resolver_keeps_backtracking():
    p,calls=provider(conflict=True);result=Resolver(p,BaseReporter()).resolve([Requirement("demo"),Requirement("leaf==1.0.0")],max_rounds=100)
    assert result.mapping["demo"].version=="2.0.0" and result.mapping["leaf"].version=="1.0.0"


def test_actual_postoverride_consumer():
    p,calls=provider();tree=ast.parse(SOURCE.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    expression=next(n.value for n in main.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="post" for t in n.targets))
    selected=eval(compile(ast.Expression(expression),str(SOURCE),"eval"),{**module.__dict__,"provider":p})
    assert selected.version=="9.16.0.29" and (selected.name,selected.version) in p.details
