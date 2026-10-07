"""Stdlib evidence extraction; no source imports, product tests, or raw-byte edits."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

base = Path('artifacts/research/process/20261004-ced-development')
oc2 = base / 'astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007'

def pin(path):
    data = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write('\n')

def junit(path):
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    ids = [c.get('classname') + '::' + c.get('name') for c in cases]
    return {'path': str(path), 'pin': pin(path), 'nodes': ids, 'unique': len(set(ids)), 'total': len(cases), 'passed': sum(not any(c.find(tag) is not None for tag in ['failure','error','skipped']) for c in cases), 'failed': len(root.findall('.//failure')), 'errors': len(root.findall('.//error')), 'skipped': len(root.findall('.//skipped'))}

if sys.argv[1] == 'oc2-freeze':
    original = json.loads((oc2 / 'input-check.json').read_text())
    after = {p: pin(p) for p in original['nine_source_records']}
    copy_root = oc2 / 'source-after'
    for p in after:
        target = copy_root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    checks = {p: {'current': pin(p), 'expected': row['actual'], 'match': pin(p) == row['actual']} for p,row in original['bounded_checks'].items()}
    historical = json.loads((oc2 / 'historical-evidence-before.json').read_text())
    history_after = {p: {'current': pin(p), 'expected': row, 'match': pin(p) == row} for p,row in historical.items()}
    write(oc2/'input-check-after.json', {'bounded': checks, 'historical': history_after, 'all_match': all(c['match'] for c in checks.values()) and all(c['match'] for c in history_after.values()), 'source_after': after})
    outcomes = {name: junit(oc2 / (name + '.junit.xml')) for name in ['full_GREEN', 'R03_regression'] if (oc2 / (name + '.junit.xml')).exists()}
    write(oc2/'test-outcomes.json', outcomes)
    all_files = {}
    for temp in ['/tmp/bigsmall-oc2-round67-green','/tmp/bigsmall-oc2-round67-r03']:
        all_files.update({str(p): pin(p) for p in Path(temp).rglob('*') if p.is_file()})
    write(oc2/'cpu-originals-denominator.json', {'CPU_only': True,'file_count':len(all_files),'files':all_files,'raw_and_db_locations':[p for p in all_files if Path(p).suffix in ['.db','.sqlite','.sqlite3','.png','.npy','.npz']], 'full_remote_raw_DB_package':False,'original_bytes_modified':False})
    failures = {}
    copy_files = {}
    for app in Path('/tmp/bigsmall-oc2-round67-green').glob('*/app'):
        runner = app/'runner-failure.json'
        if not runner.exists():
            continue
        receipt = json.loads(runner.read_bytes())
        prefix = app/'prefix-originals'
        partial_file = prefix/'partial-attempts.json'
        partial = json.loads(partial_file.read_bytes()) if partial_file.exists() else None
        failures[str(app)] = {'primary':receipt.get('primary_error'),'secondary':receipt.get('secondary_errors'),'durable_complete':receipt.get('durable_failure_evidence_complete'),'source_prefix_complete':receipt.get('source_prefix_complete'),'live_catalog_file':(app/'capture-catalog.json').exists(),'events':len(partial['operational_ledger']['events']) if partial and 'operational_ledger' in partial else None,'backend_boundaries':len(partial['backend_operation_ledger']) if partial and 'backend_operation_ledger' in partial else None,'allocated_ids':partial['operational_ledger']['allocated_acquisition_ids'] if partial and 'operational_ledger' in partial else None}
        selected = [runner, app/'worker-attempt/result.json', *prefix.glob('stage-failures-*.json'),prefix/'prefix-failures.json', prefix/'publication-failure.json',partial_file,prefix/'operational-originals.json',prefix/'unbound-export.json']
        for p in selected:
            if not p.is_file():
                continue
            relative = p.relative_to('/tmp/bigsmall-oc2-round67-green')
            target = oc2/'cpu-review-originals'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
            copy_files[str(target)]={'original':str(p),**pin(target),'same_as_original':pin(p)==pin(target)}
    write(oc2/'failure-taxonomy.json',failures)
    write(oc2/'cpu-review-copy-manifest.json',{'selected_immutable_failure_originals':copy_files,'complete_raw_DB_remote_package':False,'not_all_cpu_files_copied':True})
    write(oc2/'source-freeze.json',after)
    print(json.dumps({'outcomes':{k:{f:v[f] for f in ['total','unique','passed','failed','errors','skipped']} for k,v in outcomes.items()},'source_paths':len(after),'cpu_file_count':len(all_files),'failure_cases':len(failures),'copied_files':len(copy_files),'pins_unchanged':all(c['match'] for c in checks.values()) and all(c['match'] for c in history_after.values())}))
