"""生成明确的诊断交付路径清单；不暂存、不提交、不接触运行数据库。"""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
R373 = HERE.parent
R374 = R373.parent / 'round374-diagnostic-runtime-prerequisites-20261101'
R375 = R373.parent / 'round375-diagnostic-database-scope-20261101'
SELECTED = set()
RECEIPTS = {
    'invocation.json', 'result.json', 'source-before.json', 'source-after.json',
    'stdout.log', 'stderr.log', 'junit.xml', 'pytest-events.jsonl',
    'prerequisite.json', 'process-identity.json', 'cleanup.json',
    'preflight.json', 'database-path-inventory.json',
}


def add(path):
    if path.is_file() and not path.is_symlink():
        SELECTED.add(path)


def named(directory, names):
    for name in names:
        add(directory / name)


def direct(directory, suffixes):
    if directory.exists():
        for path in directory.iterdir():
            if path.suffix in suffixes:
                add(path)


def stage(directory):
    named(directory, RECEIPTS)
    if directory.name.startswith('dashboard_e2e'):
        add(directory / 'backend.py')
        add(directory / 'test-results/.last-run.json')
        for path in (directory / 'test-results').glob('*/error-context.md'):
            add(path)
    if directory == R373 / 'implementation/static_docs':
        SELECTED.discard(directory / 'stdout.log')


def main():
    final = R374 / 'reporting/summary.json'
    assert final.exists() and json.loads(final.read_text())['final']
    assert (R374 / 'continuation-v2/completion.json').exists()
    assert (R375 / 'implementation/workbench_module_without_runtime_db/result.json').exists() or (R375 / 'not-run.json').exists()
    named(R373, ['plan.md', 'plan.json', 'stages.json', 'assignment-manifest.json',
                 'batch-start.json', 'run_diagnostics.py', 'phase-step-report.md',
                 'phase-summary.md', 'findings.json', 'issue-analysis.md'])
    direct(R373 / 'inputs', {'.json'})
    direct(R373 / 'adapters', {'.py', '.ts', '.diff'})
    add(R373 / 'adapters/research-tests/research-evidence.spec.ts')
    direct(R373 / 'preflight', {'.json', '.stdout', '.stderr'})
    for name in ['ruff-check', 'ruff-format', 'mypy']:
        named(R373 / 'preflight' / name, ['result.json', 'stdout.log', 'stderr.log'])
    for directory in (R373 / 'implementation').iterdir():
        if directory.is_dir():
            stage(directory)
    for directory in [HERE / 'remote-preflight', HERE / 'remote-preflight-environment-retry']:
        direct(directory, {'.json', '.log'})
    named(HERE, ['BOUNDARY.md', 'select_delivery.py', 'verification.json'])
    named(R374, ['plan.md', 'plan.json', 'scope-clarification.md', 'scope-order-clarification.md',
                 'run_diagnostics.py', 'stages.json', 'resume-manifest.json',
                 'successor-pins.json', 'successor.diff', 'reconcile.py', 'phase-step-report.md'])
    direct(R374 / 'inputs', {'.json'})
    named(R374, ['marker-registration-readonly-audit.json', 'marker-source-history-readonly.json'])
    direct(R374 / 'process', {'.json'})
    for directory in (R374 / 'implementation').iterdir():
        if directory.is_dir():
            stage(directory)
    for name in ['continuation', 'continuation-v2']:
        direct(R374 / name, {'.json', '.jsonl', '.py'})
    for child in (R374 / 'continuation-v2/children').iterdir():
        named(child, ['stages.json', 'process-identity.json', 'cleanup.json'])
        stage(child / 'implementation' / child.name)
    for path in (R374 / 'reporting').iterdir():
        if path.suffix in {'.json', '.md'} and '-live' not in path.name:
            add(path)
    direct(R374 / 'review', {'.md', '.json'})
    direct(R374 / 'review/snapshots', {'.md', '.json'})
    direct(R375, {'.md', '.json', '.py'})
    direct(R375 / 'outer-run', {'.json', '.log'})
    stage(R375 / 'implementation/workbench_module_without_runtime_db')
    named(ROOT / 'docs', ['current_authoritative_status.md'])
    add(ROOT / 'docs/research/process/continuation_20261004.md')
    rows = []
    for path in sorted(SELECTED):
        raw = path.read_bytes()
        assert len(raw) < 10 * 1024 * 1024, path
        assert not any(p in path.parts for p in ('persistent-basetemp', 'pycache', 'resources', 'runtime', 'fixture'))
        rows.append({'path': str(path.relative_to(ROOT)), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
    manifest = {'schema': 'bigsmall.r373-r375.selected-delivery.v1',
                'generated_utc': datetime.now(UTC).isoformat(), 'files': rows,
                'file_count': len(rows), 'total_bytes': sum(r['bytes'] for r in rows),
                'self_excluded': str((HERE / 'selected-files.json').relative_to(ROOT)),
                'boundary': str((HERE / 'BOUNDARY.md').relative_to(ROOT)),
                'full_raw_reproduction_package': False,
                'git_mutated': False}
    (HERE / 'selected-files.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
