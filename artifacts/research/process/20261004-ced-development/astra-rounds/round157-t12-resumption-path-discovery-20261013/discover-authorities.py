"""One R157 metadata recovery; product files are hashed without decoding."""
import datetime
import hashlib
import json
import re
import sys
import traceback
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round157-t12-resumption-path-discovery-20261013'
I = D / 'implementation'
CHECKS = []


def check(name, condition, **details):
    CHECKS.append({'name': name, 'valid': bool(condition), **details})
    if not condition:
        raise ValueError(name)


def read_pin(p, group):
    check('pin_schema', isinstance(p, dict) and isinstance(p.get('path'), str)
          and type(p.get('bytes')) is int and p['bytes'] >= 0
          and isinstance(p.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', p['sha256']) is not None)
    raw = Path(p['path']).read_bytes(); sha = hashlib.sha256(raw).hexdigest()
    check('exact_bytes_sha', len(raw) == p['bytes'] and sha == p['sha256'],
          group=group, path=p['path'], bytes=len(raw), sha256=sha)
    return raw


def typed_json(raw, label):
    obj = json.loads(raw)
    check('JSON_object', isinstance(obj, dict), label=label)
    return obj


def audit():
    raw = (D / 'plan.json').read_bytes()
    check('frozen_plan', len(raw) == 18266 and hashlib.sha256(raw).hexdigest()
          == '1a51b05400f27976f059a8c1a45c85ac09ebbc1572bb21a06e1c9e4b0eccf8a8')
    plan = typed_json(raw, 'R157')
    gate = typed_json((D / 'script-gate.json').read_bytes(), 'script_gate')
    activation = typed_json((D / 'root-activation.json').read_bytes(), 'activation')
    check('activation', activation.get('activated') is True and gate.get('full_text_reviewed') is True)
    check('script_pin', read_pin(gate['script'], 'reader') == Path(__file__).read_bytes())
    check('preconditions', typed_json((D / 'input-check.json').read_bytes(), 'input_check').get('all_valid') is True
          and (ROOT / '.venv/bin/python').is_file())
    check('metadata_input_schema', isinstance(plan.get('inputs'), list) and len(plan['inputs']) == 20)
    metadata = {p['path']: read_pin(p, 'metadata') for p in plan['inputs']}
    pins = {p['path']: p for p in plan['inputs']}
    check('distinct_metadata', len(metadata) == 20)

    def by_tail(tail):
        paths = [p for p in metadata if p.endswith(tail)]
        check('unique_named_authority', len(paths) == 1, tail=tail)
        return paths[0]

    r156_path = by_tail('/round156-p6-postpush-receipt-path-recovery-20261012/plan.json')
    r155_path = by_tail('/round155-p6-disjoint-head-finite-delivery-20261012/plan.json')
    r156 = typed_json(metadata[r156_path], 'R156')
    check('R156_input_list', isinstance(r156.get('inputs'), list))
    links = [p for p in r156['inputs'] if isinstance(p, dict) and p.get('path') == r155_path]
    check('R156_binds_R155', len(links) == 1 and all(links[0].get(k) == pins[r155_path][k] for k in ('path','bytes','sha256')))
    r155 = typed_json(metadata[r155_path], 'R155')
    check('R155_payload_object', isinstance(r155.get('payload'), dict))
    manifest_path = r155['payload'].get('static_manifest')
    check('R155_binds_exact_manifest', isinstance(manifest_path, str) and manifest_path in metadata)
    manifest = typed_json(metadata[manifest_path], 'manifest')
    files = manifest.get('files')
    check('manifest_records', isinstance(files, list) and len(files) == 830
          and all(isinstance(x, dict) and isinstance(x.get('path'), str) for x in files))
    table = {x['path']: x for x in files}
    check('manifest_unique_paths', len(table) == 830)
    chain = plan['authority_chain']
    check('authority_chain_object', isinstance(chain, dict))
    design_path = chain['b_contract']; r113_dir = str(Path(design_path).parent) + '/'
    r151_dir = chain['actual_r151'] + '/'
    targets = [p for p in metadata if p.startswith(r113_dir) or p.startswith(r151_dir)
               or p == chain['current_a_source_authority']]
    check('twelve_authorities', len(targets) == 12)
    for path in targets:
        check('exact_frozen_manifest_authority', path in table
              and table[path].get('relative_path') == str(Path(path).relative_to(ROOT))
              and all(table[path].get(k) == pins[path][k] for k in ('path','bytes','sha256')), path=path)
    current = plan['current_source_candidates']
    check('current_candidate_schema', isinstance(current, list) and len(current) == 7)
    freeze = typed_json(metadata[chain['current_a_source_authority']], 'later_A_freeze')
    sources = freeze.get('sources'); protected = freeze.get('protected')
    check('freeze_source_schema', isinstance(sources, list) and len(sources) == 6
          and all(isinstance(x, dict) and isinstance(x.get('source'), str) for x in sources))
    check('freeze_protected_schema', isinstance(protected, list)
          and all(isinstance(x, dict) and isinstance(x.get('path'), str) for x in protected))
    source_table = {x['source']: x for x in sources}; protected_table = {x['path']: x for x in protected}
    for p in current:
        read_pin(p, 'current_source_bytes_only')
        old = source_table.get(p['path'], protected_table.get(p['path']))
        check('later_A_current_byte_authority', isinstance(old, dict)
              and all(old.get(k) == p[k] for k in ('bytes','sha256')), path=p['path'])
    design_lines = metadata[design_path].decode().splitlines()
    starts = [n for n,line in enumerate(design_lines) if line == chain['b_heading']]
    check('exact_B_heading', len(starts) == 1 and starts[0] + 1 == chain['b_heading_line'])
    start = starts[0]
    end = next((n for n in range(start+1,len(design_lines)) if design_lines[n].startswith('### ')),len(design_lines))
    section = [{'line': n+1,'text':design_lines[n]} for n in range(start,end)]
    check('bounded_B_section', len(section) <= 600)
    matrix_path = by_tail('/round113-p6-operational-runtime-closure-20261008/cpu-matrix.json')
    next_path = chain['next_b9_inputs']
    check('next_inputs_pinned', isinstance(next_path,str) and next_path in metadata)
    return {'status':'EXACT_T12_B_AUTHORITIES_RECOVERED_METADATA_ONLY','metadata_count':20,
            'current_source_byte_count':7,'authority_count':12,'authorities':[pins[p] for p in targets],
            'authority_chain':chain,'B_section':section,
            'cpu_matrix':typed_json(metadata[matrix_path],'cpu_matrix'),
            'next_b9_inputs':typed_json(metadata[next_path],'next_b9_inputs'),
            'reader_runs':1,'reader_remaining':0,'new_Git_commands':0,'new_product_test_review_commands':0,
            'B9_open':True,'P6_complete':False,'T12_complete':False,'native_actual_formal_accepted':False,
            'source_read_boundary':'Seven product/test files were read as bytes for hashes only; no decoding/import/AST/runtime.',
            'history_boundary':'Original R113 pins remain historical; current source binds later A freeze. No full raw/fixture scan.'}


if __name__ == '__main__':
    I.mkdir(exist_ok=True)
    if (I / 'discovery.json').exists():
        raise RuntimeError('Reader already consumed; never replay.')
    report = {'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}; code=0
    try:
        report.update(audit())
    except Exception as error:
        code=1; report.update({'status':'STOPPED_ACTUAL_METADATA_FAILURE','error_type':type(error).__name__,'error':str(error)})
        traceback.print_exc()
    report.update({'all_valid':code==0,'checks':CHECKS,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    with (I / 'discovery.json').open('xb') as f:f.write(raw)
    print(json.dumps({'status':report['status'],'all_valid':report['all_valid'],'checks':len(CHECKS),
                      'path':str(I/'discovery.json'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},ensure_ascii=False))
    sys.exit(code)
