"""Copy a tiny full-run evidence subset byte-for-byte after completion."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ART = R / 'implementation/phase12-full/artifacts'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    result = json.loads((R / 'implementation/phase12-full/result.json').read_text())
    assert result.get('reaped') and not result.get('source_drift') and not result.get('remaining_live')
    raw = ART / 'runs/raw_runs.jsonl'
    output = R / 'reports/evidence'
    output.mkdir(exist_ok=True)
    copies = []
    selected = None
    if raw.is_file():
        for line_number, line in enumerate(raw.read_bytes().splitlines(keepends=True), 1):
            row = json.loads(line)
            if row.get('experiment_id') == 'F20_STRESS_AND_RECOVERY':
                target = output / 'phase12-full-f20-first-row.jsonl'
                with target.open('xb') as stream:
                    stream.write(line)
                copies.append({'source_path': str(raw), 'source_line': line_number,
                               'copy_path': str(target.relative_to(R)), 'bytes': len(line),
                               'sha256': sha(line), 'copy_method': 'Exact original JSONL line bytes, no normalization.'})
                selected = row
                break
    if selected:
        receipt_path = ART / selected['source_artifact_path']
        assert receipt_path.resolve().is_relative_to(ART.resolve())
        if receipt_path.is_file():
            data = receipt_path.read_bytes()
            target = output / 'phase12-full-f20-first-runtime-receipt.json'
            with target.open('xb') as stream:
                stream.write(data)
            copies.append({'source_path': str(receipt_path), 'copy_path': str(target.relative_to(R)),
                           'bytes': len(data), 'sha256': sha(data), 'copy_method': 'Exact file bytes.'})
            receipt = json.loads(data)
            relative = receipt.get('main_job', {}).get('artifact_paths', {}).get('result')
            if relative:
                inner = ART / 'source_evidence' / selected['run_id'] / 'phase11_runtime/artifacts' / relative
                assert inner.resolve().is_relative_to(ART.resolve())
                if inner.is_file():
                    data = inner.read_bytes()
                    target = output / 'phase12-full-f20-first-main-result.json'
                    with target.open('xb') as stream:
                        stream.write(data)
                    copies.append({'source_path': str(inner), 'copy_path': str(target.relative_to(R)),
                                   'bytes': len(data), 'sha256': sha(data), 'copy_method': 'Exact file bytes.'})
    note = {'generated_utc': datetime.now(UTC).isoformat(), 'full_result_state': result['state'],
            'selected_run_id': selected.get('run_id') if selected else None, 'copies': copies,
            'scope': 'Small exact subset only; not the complete full raw package. Original files unchanged.',
            'sqlite_connections_opened': 0, 'additional_test_runs': 0}
    with (R / 'reports/full-receipt-selection.json').open('x', encoding='utf-8') as stream:
        json.dump(note, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'selected_run_id': note['selected_run_id'], 'copied_files': len(copies)}))


if __name__ == '__main__':
    main()
