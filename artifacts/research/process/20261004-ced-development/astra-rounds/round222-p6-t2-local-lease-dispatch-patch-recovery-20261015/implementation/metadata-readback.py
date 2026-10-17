"""R222 bounded source readback candidate; never imports or executes products."""
from pathlib import Path
import hashlib
import json
import difflib

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D222 = ROUNDS / 'round222-p6-t2-local-lease-dispatch-patch-recovery-20261015'
D225 = ROUNDS / 'round225-p6-t2-patch-preparer-class-scope-20261015'
CHECKS = []


def require(condition, label):
    CHECKS.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def pin(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read_pin(record):
    path = Path(record['path'])
    require(not path.is_symlink(), 'input is not symlink: ' + str(path))
    data = path.read_bytes()
    require(pin(path, data) == {key: record[key] for key in ('path', 'bytes', 'sha256')}, 'exact input pin: ' + str(path))
    return data


def main():
    gate_path = D222 / 'root-activation.json'
    activation_bytes = gate_path.read_bytes()
    gate = json.loads(activation_bytes)['metadata_readback_gate']
    argv = [str(ROOT / '.venv/bin/python'), '-I', '-B', str(D222 / 'implementation/metadata-readback.py')]
    finite_env = {'PATH': str(ROOT / '.venv/bin') + ':/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    require(gate['state'] == 'RESERVED_BY_ROOT' and gate['authorized'] == gate['used'] == 1 and gate['remaining'] == 0, 'ROOT one readback reservation')
    require(gate['argv'] == argv and gate['cwd'] == str(ROOT) and gate['finite_env'] == finite_env and gate['timeout_seconds'] == 120, 'exact interpreter argv/cwd/finite env/external cap')
    require(gate['source_pin']['path'] == str(Path(__file__)), 'readback source identity')
    read_pin(gate['source_pin'])
    prepared_path = D222 / 'implementation/prepared-text-values.json'
    require(gate['prepared_values_pin']['path'] == str(prepared_path), 'prepared values identity')
    prepared_bytes = read_pin(gate['prepared_values_pin'])
    prepared = json.loads(prepared_bytes)
    require(gate['corrected_patch_pin']['path'] == str(D222 / 'implementation/corrected-patch.txt'), 'corrected patch identity')
    read_pin(gate['corrected_patch_pin'])
    require(gate['actual_apply_pin']['path'] == str(D222 / 'implementation/actual-patch-tool-return.json'), 'actual native receipt identity')
    actual_apply_bytes = read_pin(gate['actual_apply_pin'])
    # An apply_patch object is preserved as data; it is never turned into a process exit.
    actual_apply = json.loads(actual_apply_bytes)
    parent = json.loads((D222 / 'plan.json').read_bytes())
    expected = prepared['expected']
    require(list(expected) == parent['scope']['paths'] and len(expected) == 3, 'exact three authorized source paths')
    require(len(prepared['edit_units']) == 9 and len(prepared['function_regions']) == 7, 'nine original units/seven qualified functions')
    current, originals = {}, {}
    for path, item in expected.items():
        before = read_pin(item['before_archive'])
        require(pin(path, before) == item['before'], 'physical before source identity: ' + path)
        originals[path] = before
        after = Path(path).read_bytes()
        require(not Path(path).is_symlink(), 'after source is not symlink: ' + path)
        require(after == item['after_text'].encode('utf-8') and len(after) == item['after_bytes'] and hashlib.sha256(after).hexdigest() == item['after_sha256'], 'full exact intended after source: ' + path)
        require(Path(path).stat().st_mode == item['before_mode'], 'source mode unchanged: ' + path)
        require(before.endswith(b'\n') == after.endswith(b'\n') and b'\r' not in before and b'\r' not in after, 'newline/EOF unchanged: ' + path)
        current[path] = after
        cursor, reconstructed = 0, []
        regions = [region for region in prepared['function_regions'] if region['path'] == path]
        for region in regions:
            start, end = region['before_start'], region['before_end']
            require(cursor <= start < end, 'ordered exact before function interval: ' + region['qualified_function'])
            require(before.decode('utf-8')[start:end] == region['before_text'], 'before function bytes: ' + region['qualified_function'])
            require(after.decode('utf-8')[region['after_start']:region['after_end']] == region['after_text'], 'after function bytes: ' + region['qualified_function'])
            reconstructed.extend((before.decode('utf-8')[cursor:start], region['after_text']))
            cursor = end
        reconstructed.append(before.decode('utf-8')[cursor:])
        require(''.join(reconstructed).encode('utf-8') == after, 'all bytes outside seven functions unchanged: ' + path)
    for pair in prepared['manifest_pairs']:
        archive = read_pin(pair['archive'])
        require(pin(pair['source']['path'], archive) == pair['source'], 'original physical manifest pair')
        if pair['source']['path'] not in expected:
            require(read_pin(pair['source']) == archive, 'unaffected current manifest record')
    require(len(prepared['manifest_pairs']) == 25, '25 manifest records/22 unaffected')
    for record in prepared['r225_inputs']:
        if record['path'] in expected:
            require(record == expected[record['path']]['before'], 'only three exact historical live input exceptions')
            read_pin(expected[record['path']]['before_archive'])
        else:
            read_pin(record)
    require(len(prepared['protected']) == 211, '211 protected files')
    for record in prepared['protected']:
        read_pin(record)
    for role, record in prepared['role_pins'].items():
        ledger = json.loads(read_pin(record))
        red, green = ledger['commands']['t2_red'], ledger['commands']['t2_green']
        require(red['used'] == 1 and red['remaining'] == 0, role + ' RED remains spent')
        require(green['used'] == 0 and green['remaining'] == 1 and green['state'].startswith('HELD'), role + ' GREEN remains held')
    output_contract = parent['outputs']
    output_bytes = {}
    after_pins = []
    for path, data in current.items():
        archive_path = Path(output_contract['after_directory']) / Path(path).relative_to(ROOT)
        output_bytes[archive_path] = data
        after_pins.append({'source': pin(path, data), 'archive': pin(archive_path, data), 'before': expected[path]['before'], 'before_archive': expected[path]['before_archive']})
    diff = ''.join(''.join(difflib.unified_diff(originals[path].decode('utf-8').splitlines(keepends=True), current[path].decode('utf-8').splitlines(keepends=True), fromfile=path + ' (R222 physical before)', tofile=path + ' (exact original intent)', n=3)) for path in expected).encode('utf-8')
    output_bytes[Path(output_contract['limited_diff'])] = diff
    report = {'round': 'R222', 'status': 'SOURCE_TEXT_SCOPE_ONLY', 'before_after': after_pins, 'edit_units': prepared['edit_units'], 'function_regions': prepared['function_regions'], 'checks': CHECKS, 'actual_apply_pin': gate['actual_apply_pin'], 'actual_apply_receipt': actual_apply, 'prepared_values_pin': gate['prepared_values_pin'], 'corrected_patch_pin': gate['corrected_patch_pin'], 'product_execution': False, 'GREEN': {'used': 0, 'remaining': 1, 'state': 'HELD'}, 'runtime_evidence': None}
    output_bytes[Path(output_contract['change_report'])] = encode(report)
    output_bytes[Path(output_contract['source_index'])] = encode({'round': 'R222', 'sources': after_pins, 'unaffected_manifest_records': [pair for pair in prepared['manifest_pairs'] if pair['source']['path'] not in expected], 'protected': prepared['protected']})
    result = {'round': 'R222', 'command': 'metadata_readback', 'exit_code': 0, 'attempt': 1, 'retry': 0, 'argv': argv, 'cwd': str(ROOT), 'finite_env': finite_env, 'timeout_seconds': 120, 'source_pin': gate['source_pin'], 'activation_pin': pin(gate_path, activation_bytes), 'checks': CHECKS, 'outputs': [pin(path, data) for path, data in output_bytes.items()], 'source_changes': 3, 'qualified_function_regions': 7, 'edit_units': 9, 'unaffected_records': 22, 'protected_count': 211, 'test_execution': False, 'product_commands': 0, 'runtime_evidence': None}
    output_bytes[Path(output_contract['step_json'])] = encode(result)
    output_bytes[Path(output_contract['step_md'])] = ('# R222 source readback\n\nExact original-intent source bytes checked in three paths and seven qualified functions. Nine original edit units preserved; 22 unaffected manifest records and 211 protected files unchanged. No product/test/static execution; GREEN remains HELD. Actual apply receipt is preserved data, with no fabricated numeric exit.\n').encode('utf-8')
    require(all(not path.exists() for path in output_bytes), 'all readback outputs absent before writes')
    # No source mutation is authorized; recheck every observed current byte before metadata writes.
    for path, data in current.items():
        require(Path(path).read_bytes() == data, 'final source CAS: ' + path)
    for pair in prepared['manifest_pairs']:
        if pair['source']['path'] not in expected:
            read_pin(pair['source'])
    for record in prepared['protected']:
        read_pin(record)
    for path, data in output_bytes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            require(handle.write(data) == len(data), 'complete exclusive metadata write: ' + str(path))
        require(path.read_bytes() == data, 'metadata output readback: ' + str(path))
    summary = {'status': 'SOURCE_TEXT_SCOPE_ONLY', 'source_changes': 3, 'functions': 7, 'edit_units': 9, 'protected': 211, 'step_result': pin(Path(output_contract['step_json']), output_bytes[Path(output_contract['step_json'])]), 'source_index': pin(Path(output_contract['source_index']), output_bytes[Path(output_contract['source_index'])]), 'limited_diff': pin(Path(output_contract['limited_diff']), diff), 'product_execution': False}
    rendered = json.dumps(summary, ensure_ascii=False)
    require(len((rendered + '\n').encode('utf-8')) <= 6000, 'bounded stdout')
    print(rendered)


if __name__ == '__main__':
    main()
