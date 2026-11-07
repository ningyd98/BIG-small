"""Execute one frozen R449 stage; do not reuse prior stage directories."""
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
    stages = [s for s in plan['verification_order'] if s in plan['verification_specs']]
    if stage not in stages:
        raise ValueError('undeclared stage')
    for earlier in stages[:stages.index(stage)]:
        result = json.loads((ROUND/'validation'/earlier/'result.json').read_text())
        expected_rc = 1 if earlier == 'clock-red' else 0
        if earlier == 'clock-red':
            cases = ET.parse(ROUND/'validation'/earlier/'junit.xml').findall('.//testcase')
            if len(cases) != 4 or any(c.find('failure') is None or 'AssertionError: R449' not in c.find('failure').text for c in cases):
                raise ValueError('RED did not match four registered missing APIs')
        if result['returncode'] != expected_rc or result['remaining_live'] or result['source_drift'] or not result['reaped']:
            raise ValueError('previous stage did not pass')
    commands = plan['verification_specs']
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
    allowed = set(original['allowed_source_edits']+original['allowed_new_products']+original['allowed_new_tests']+plan['allowed_edits'])
    current = {row['path']:pin(row['path']) for row in baseline}
    drift = [r['path'] for r in baseline if current[r['path']] != r and r['path'] not in allowed]
    permitted = set(plan['allowed_edits'])
    for row in plan['input_pins']:
        actual = pin(row['path'])
        if (actual['sha256'] != row['sha256'] or actual['bytes'] != row['bytes']) and row['path'] not in permitted:
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
    definition=importlib.util.spec_from_file_location('r449_bounded', BASE/'round413-full-long-validation-20261103/bounded_stage.py')
    module=importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    module.ROUND=directory
    module.run(directory/'spec.json')


if __name__=='__main__':
    run(sys.argv[1])
