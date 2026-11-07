"""Execute one frozen R454 stage; do not reuse prior stage directories."""
import hashlib
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def pin(name):
    raw = (ROOT/name).read_bytes()
    return dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def run(stage):
    plan = json.loads((ROUND/'plan.json').read_text())
    commands = {key:json.loads((ROUND/value).read_text()) for key,value in plan['validation']['spec_templates'].items()}
    stages = list(commands)
    if stage not in stages:
        raise ValueError('undeclared stage')
    for earlier in stages[:stages.index(stage)]:
        result = json.loads((ROUND/'validation'/earlier/'result.json').read_text())
        expected_rc = 1 if earlier == 'conversion-red' else 0
        if earlier == 'conversion-red':
            cases = ET.parse(ROUND/'validation'/earlier/'junit.xml').findall('.//testcase')
            if len(cases) != 1 or cases[0].find('failure') is None or "['reset', 'guard']" not in cases[0].find('failure').text:
                raise ValueError('RED did not match the declared reset-to-guard omission')
        if result['returncode'] != expected_rc or result['remaining_live'] or result['source_drift'] or not result['reaped']:
            raise ValueError('previous stage did not pass')
    command_path = ROUND/'implementation/commands.json'
    if not command_path.exists():
        save(command_path, commands)
    if json.loads(command_path.read_text()) != commands:
        raise ValueError('frozen commands changed')
    spec = commands[stage]
    directory = Path(spec['directory'])
    directory.mkdir(parents=True, exist_ok=False)
    for arg in spec['argv']:
        if arg.startswith('--basetemp=') and Path(arg.split('=',1)[1]).exists():
            raise ValueError('preserve old basetemp')
    for key in ('TMPDIR','XDG_CACHE_HOME','BIGSMALL_R158_T2_RESOURCE_DIR','BIGSMALL_R175_RESOURCE_DIR',
                'BIGSMALL_R223_RESOURCE_ROOT','BIGSMALL_R223_CASE_ROOT','DASHBOARD_ARTIFACT_ROOT'):
        Path(spec['env'][key]).mkdir(parents=True, exist_ok=True)
    source = BASE/'round439-full-execution-independent-calibration-20261107'
    original = json.loads((source/'plan.json').read_text())
    baseline = json.loads((source/'implementation/baseline.json').read_text())['files']
    previous = json.loads((BASE/'round449-archived-tracker-clock-20261108/plan.json').read_text())
    allowed = set(original['allowed_source_edits']+original['allowed_new_products']+original['allowed_new_tests']+previous['allowed_edits']+plan['allowed_product_paths'])
    current = {row['path']:pin(row['path']) for row in baseline}
    drift = [r['path'] for r in baseline if current[r['path']] != r and r['path'] not in allowed]
    permitted = set(plan['allowed_product_paths'])
    allowed.update(permitted)
    prior = json.loads((BASE/'round451-instance-background-originals-20261108/implementation/step-report.json').read_text())
    approved_prior = {row['path']:row['after_sha256'] for row in prior['changes']}
    prior2 = json.loads((BASE/'round452-observer-failure-accounting-20261108/implementation/step-report.json').read_text())
    approved_prior.update({row['path']:row['after_sha256'] for row in prior2['changes']})
    prior3 = json.loads((BASE/'round453-source-effect-graph-20261108/implementation/step-report.json').read_text())
    approved_prior.update({row['path']:row['after_sha256'] for row in prior3['changes']})
    allowed.update(approved_prior)
    for row in json.loads((ROUND/plan['input_pins']).read_text()):
        actual = pin(row['path'])
        if (actual['sha256'] != row['sha256'] or actual['bytes'] != row['bytes']) and row['path'] not in permitted and actual['sha256'] != approved_prior.get(row['path']):
            drift.append(row['path'])
        current[row['path']] = actual
    if drift:
        raise ValueError(drift)
    for name in allowed:
        if (ROOT/name).exists():
            current[name] = pin(name)
    for path in (ROUND/'plan.json',ROUND/'plan.md',Path(__file__),command_path):
        name = str(path.relative_to(ROOT))
        current[name] = pin(name)
    save(directory/'preflight/runtime-source-pins.json',dict(files=list(current.values())))
    save(directory/'preflight/generation.json',dict(unplanned_drift=drift))
    save(directory/'spec.json',spec)
    definition=importlib.util.spec_from_file_location('r454_bounded', BASE/'round413-full-long-validation-20261103/bounded_stage.py')
    module=importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND=directory
    module.run(directory/'spec.json')


if __name__=='__main__':
    run(sys.argv[1])
