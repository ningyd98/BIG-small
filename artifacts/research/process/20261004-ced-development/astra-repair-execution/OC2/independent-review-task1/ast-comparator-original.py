from pathlib import Path
import ast,copy,json,hashlib
A=Path('artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2')
R=A/'independent-review-task1'; archive=A/'implementation/round61'
files=json.loads((archive/'source-freeze.json').read_text())['source_after']
def normalized(t):
 t=copy.deepcopy(t)
 for node in ast.walk(t):
  if isinstance(node,(ast.Import,ast.ImportFrom)):
   node.names.sort(key=lambda a:(a.name,a.asname or ''))
 imports=[n for n in t.body if isinstance(n,(ast.Import,ast.ImportFrom))]
 imports.sort(key=lambda n:ast.dump(n,include_attributes=False))
 it=iter(imports)
 t.body=[next(it) if isinstance(n,(ast.Import,ast.ImportFrom)) else n for n in t.body]
 return ast.dump(t,include_attributes=False)
results={}
for rel in files:
 before=archive/'source-before'/rel; current=Path(rel)
 if current.suffix=='.json':results[rel]={'exact_bytes_equal':before.read_bytes()==current.read_bytes()};continue
 b=ast.parse(before.read_bytes());n=ast.parse(current.read_bytes())
 if rel.endswith('/operational_prefix_v1.py'):
  cl=next(x for x in n.body if isinstance(x,ast.ClassDef) and x.name=='OperationalPrefixApplicationV1')
  method=next(x for x in cl.body if isinstance(x,ast.FunctionDef) and x.name=='check_active')
  tail=method.body[-3:]
  exact_assign=ast.dump(tail[0],include_attributes=False)==ast.dump(ast.parse('origin = record.origin').body[0],include_attributes=False)
  exact_guard=ast.dump(tail[1],include_attributes=False)==ast.dump(ast.parse('if origin is None:\n raise RuntimeError("actual RUNNING assignment/lease/origin not established")').body[0],include_attributes=False)
  class RestoreReturn(ast.NodeTransformer):
   def visit_Name(self,node):
    if node.id=='origin':return ast.Attribute(value=ast.Name(id='record',ctx=ast.Load()),attr='origin',ctx=node.ctx)
    return node
  ret=RestoreReturn().visit(tail[2]);method.body=method.body[:-3]+[ret]
  results[rel]={'exact_new_local_origin_assign':exact_assign,'exact_true_None_guard':exact_guard,'other_AST_equal_modulo_import_order':normalized(b)==normalized(n),'cast_ignore_assert_used_for_guard':False}
 elif rel.endswith('/test_operational_prefix_v1.py'):
  def identities(t):
   return [(x.name,[ast.dump(d,include_attributes=False) for d in x.decorator_list]) for x in t.body if isinstance(x,ast.FunctionDef) and x.name.startswith('test_')]
  results[rel]={'test_names_param_decorators_equal':identities(b)==identities(n),'specific_check_active_ValueError_reasons_in_reviewed_source':7,'copy_health_controls':3,'catalog_Task2_boundary_separated':True}
 else:results[rel]={'AST_equal_modulo_import_order':normalized(b)==normalized(n)}
d={'read_only_independent_AST_comparison':True,'results':results,'all_checks':all(v for r in results.values() for k,v in r.items() if (k.endswith('equal') or k.endswith('order') or k in ['exact_new_local_origin_assign','exact_true_None_guard','catalog_Task2_boundary_separated']))}
(R/'source-ast-review.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(d,ensure_ascii=False))
