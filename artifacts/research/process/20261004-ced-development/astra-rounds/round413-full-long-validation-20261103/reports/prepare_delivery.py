"""Build an exact small evidence selection; never select databases or big raw batches."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import stat
import subprocess

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
R = Path(__file__).resolve().parents[1]
ROUNDS = [R, R.parent / 'round414-workbench-db-scope-preflight-handoff-20261103',
          R.parent / 'round415-unstarted-tail-resource-parent-handoff-20261103']
R416 = R.parent / 'round416-selected-report-ignore-admission-20261103'
R416_EXACT = {'plan.md', 'plan.json', 'intake/ignore-evidence.json',
              'implementation-step.json', 'step-report.md', 'admission/core-ignore-audit.json'}
R417 = R.parent / 'round417-delivery-interpreter-invocation-20261103'
R417_EXACT = {'plan.md', 'plan.json', 'intake/failure.json',
              'implementation-step.json', 'step-report.md'}
STAGE_FILES = {'invocation.json', 'result.json', 'terminal.json', 'raw-exit.json',
               'exit-observation-before-cleanup.json', 'owned-process-identities.json',
               'source-before.json', 'ports-before.json', 'pytest-events.jsonl', 'junit.xml',
               'prerequisite.json', 'resource-observations.jsonl', 'stdout.log', 'stderr.log',
               'native-queue-receipt.json', 'comparison.json', 'openapi.json.diff', 'schema.d.ts.diff',
               'observed-summary.json'}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def record(path):
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_path(path):
    rel = path.relative_to(ROOT)
    assert rel.parts and '..' not in rel.parts and not rel.is_absolute()
    assert not any(ord(c) < 32 or ord(c) == 127 or c in '*?[]' for c in str(rel))
    assert not any(part.startswith(':') for part in rel.parts)
    assert any(path.is_relative_to(base) for base in ROUNDS) or (
        path.is_relative_to(R416) and str(path.relative_to(R416)) in R416_EXACT) or (
        path.is_relative_to(R417) and str(path.relative_to(R417)) in R417_EXACT)
    assert path.resolve(strict=True).is_relative_to(ROOT.resolve(strict=True))
    assert stat.S_ISREG(path.lstat().st_mode)
    for ancestor in path.parents:
        assert not ancestor.is_symlink(), str(ancestor)
    assert path.suffix.lower() not in {
        '.db', '.sqlite', '.sqlite3', '.png', '.jpg', '.jpeg', '.webp', '.gif',
        '.zip', '.tar', '.gz', '.pdf', '.mp4', '.pt', '.pth', '.onnx', '.safetensors'}
    assert not path.name.endswith(('-wal', '-shm'))
    assert not any(part.lower() in {
        'tmp', 'cache', '.cache', 'runtime', 'resources', 'resources-a', 'node_modules',
        'pycache', '__pycache__', 'weights', 'sdk', 'credentials', 'traces'} for part in rel.parts)
    assert path.name not in {'raw_runs.jsonl', 'run_manifests.jsonl', 'events.jsonl'}
    assert not (path.parent.name == 'static-docs' and path.name == 'stdout.log')


def ignore_audit(paths):
    names = [str(path.relative_to(ROOT)) for path in sorted(paths)]
    assert len(names) == len(set(names)) and all(names)
    data = b''.join(name.encode('utf-8') + b'\0' for name in names)
    cp = subprocess.run(['git', 'check-ignore', '-v', '-z', '--stdin'], cwd=ROOT,
                        input=data, capture_output=True, timeout=60)
    assert cp.returncode in {0, 1}, (cp.returncode, cp.stderr.decode('utf-8', 'replace'))
    pieces = cp.stdout.split(b'\0')
    assert pieces[-1] == b''
    pieces.pop()
    assert len(pieces) % 4 == 0
    matches = []
    for i in range(0, len(pieces), 4):
        source, line, pattern, name = [item.decode('utf-8') for item in pieces[i:i + 4]]
        path = ROOT / name
        assert name in names and source == '.gitignore' and pattern == 'reports/'
        assert any(path.is_relative_to(base / 'reports') for base in ROUNDS), name
        matches.append({'path': name, 'source': source, 'line': int(line), 'pattern': pattern})
    return {'schema': 'r416.exact-ignore-admission.v1', 'created_utc': datetime.now(UTC).isoformat(),
            'command': ['git', 'check-ignore', '-v', '-z', '--stdin'], 'returncode': cp.returncode,
            'candidate_count': len(names), 'candidate_paths': names, 'ignored_count': len(matches),
            'matches': matches, 'all_ignored_admitted': True,
            'policy': 'Only reports/ matches inside the three authorized reports directories; exact -f add only.',
            'no_git_mutation_performed': True}


def main():
    assert (R / 'reports/development-progress.md').is_file()
    assert (R / 'reports/test-report.md').is_file()
    assert json.loads((R / 'reports/summary.json').read_text())['final']
    chosen = set()
    for base in ROUNDS:
        for path in base.iterdir():
            if path.is_file() and path.suffix in {'.json', '.md', '.py'}:
                chosen.add(path)
        for name in ['preflight', 'specs', 'postflight', 'continuations']:
            directory = base / name
            if directory.exists():
                for path in directory.iterdir():
                    if path.is_file() and path.suffix in {'.json', '.md', '.stdout', '.stderr'}:
                        chosen.add(path)
        directory = base / 'reports'
        if directory.exists():
            for path in directory.iterdir():
                if path.is_file() and path.suffix in {'.json', '.md', '.py'}:
                    chosen.add(path)
            if (directory / 'evidence').exists():
                chosen.update(path for path in (directory / 'evidence').iterdir() if path.is_file())
        directory = base / 'implementation'
        if directory.exists():
            for stage in directory.iterdir():
                if not stage.is_dir():
                    continue
                for name in STAGE_FILES:
                    path = stage / name
                    if path.is_file() and path.stat().st_size <= 2_000_000:
                        if stage.name == 'static-docs' and name == 'stdout.log':
                            continue  # Raw sensitive-content findings remain local; sanitized audit is selected.
                        chosen.add(path)
                verification = stage / 'verification'
                if verification.exists():
                    chosen.update(path for path in verification.glob('*.json') if path.is_file())
        chosen.update(path for path in [base / 'resume.stdout.log', base / 'resume.stderr.log'] if path.is_file())
    adapters = R / 'adapters'
    chosen.update(path for path in adapters.iterdir() if path.is_file() and path.name != 'r413_tracking.py')
    artifact = R / 'implementation/phase12-full/artifacts'
    for name in ['manifests/provenance.json', 'runs/run_summary.json', 'aggregates/phase12_aggregate.json',
                 'statistics/phase12_statistics.json', 'paired/paired_summary.json', 'demo_bundle/demo_summary.json']:
        path = artifact / name
        if path.is_file():
            chosen.add(path)
    for name in sorted(R416_EXACT - {'admission/core-ignore-audit.json'}):
        path = R416 / name
        assert path.is_file(), str(path)
        chosen.add(path)
    for name in sorted(R417_EXACT):
        path = R417 / name
        assert path.is_file(), str(path)
        chosen.add(path)
    delivery = R / 'delivery'
    delivery.mkdir(exist_ok=True)
    readme = delivery / 'README.md'
    with readme.open('x', encoding='utf-8') as stream:
        stream.write('''# R413 精选证据交付边界

被测代码为 ab18abd0f82a024b62f4423c946c6585f8d18c65；报告提交只新增证据，不表示对新报告提交重新执行整套长测。

core-manifest.json 是whole-evidence review前的精确路径/字节/SHA选择。最终selected-manifest.json还会纳入fresh review与本交付说明等明确文件；实际Git stage列表使用独立NUL路径文件。推送回执在本目录本地保存，因包含本次commit SHA而不属于该commit。

R416补充计划仅处理.gitignore的reports/准入，见../../{r416}/step-report.md。它允许一次字面路径NUL清单的git add -f；这只是登记明确报告文件，不授权force push，也不修改.gitignore。

审核后元数据只允许追加本目录core-manifest.json、core-paths.txt、selected-paths.nul、selected-manifest.json，../review/whole-evidence-review.md与.json，以及R416/admission/final-ignore-audit.json。README本身已在核心清单。核心字节审核后冻结；新增文件也逐路径审计忽略规则。selected-paths.nul先写定（包括自身及最终manifest路径），selected-manifest.json记录其SHA及其它每个文件SHA，但不包含自身SHA；最终manifest另在本地Git门禁回执单独hash，以避免自指。最终清单未获通过前不stage。

完整批量raw、运行数据库/WAL/SHM、/tmp、缓存、重复fixtures、图像/trace、凭据、模型权重和SDK保持本地，不在精选包内。Phase12完整raw/manifest只记录SHA与大小；精选审计和个别原始回执不能冒充完整远端复现包。原static-docs敏感内容扫描详情保留本地；提交中使用脱敏分类。

报告保留35项Python失败、6项backend参数化skip、1项未完成及2项真实数据未运行。Mypy入口未形成有效源码类型检查，不能视为类型检查通过。正式研究/实体硬件验收未完成。源/清理/唯一STARTED核验与原始失败分开记录。
'''.replace('{r416}', R416.name))
    chosen.add(readme)
    for path in chosen:
        validate_path(path)
    audit_path = R416 / 'admission/core-ignore-audit.json'
    audit_path.parent.mkdir(exist_ok=True)
    save(audit_path, ignore_audit(chosen | {audit_path}))
    validate_path(audit_path)
    chosen.add(audit_path)
    files = [record(path) for path in sorted(chosen)]
    local_only = []
    for name in ['runs/raw_runs.jsonl', 'manifests/run_manifests.jsonl', 'runs/events.jsonl']:
        path = artifact / name
        if path.is_file():
            local_only.append(record(path))
    manifest = {'schema': 'r413.selected-evidence-core.v1', 'created_utc': datetime.now(UTC).isoformat(),
                'tested_commit': 'ab18abd0f82a024b62f4423c946c6585f8d18c65',
                'files': files, 'file_count': len(files), 'total_bytes': sum(row['bytes'] for row in files),
                'local_only_large_raw_examples': local_only,
                'local_runtime_locations': [str(base / 'implementation') for base in ROUNDS] +
                    ['/tmp/bigsmall-r413-*', '/tmp/bigsmall-r414-*', '/tmp/bigsmall-r415-*'],
                'full_remote_reproduction_package': False,
                'excluded_classes': ['complete batch raw/manifest/event JSONL', 'DB/WAL/SHM', 'tmp/cache/resources',
                                     'duplicate input fixtures', 'images/traces/video', 'credentials', 'models/SDK',
                                     'unrelated untracked files', 'both dirty gitlinks', 'raw static-docs sensitive findings'],
                'self_hash_rule': 'This core manifest does not include itself; the final stage manifest pins it separately.'}
    save(delivery / 'core-manifest.json', manifest)
    with (delivery / 'core-paths.txt').open('x', encoding='utf-8') as stream:
        stream.write(''.join(row['path'] + '\n' for row in files))
    print(json.dumps({'selected_files': len(files), 'selected_bytes': manifest['total_bytes'],
                      'complete_remote_raw_package': False}))


if __name__ == '__main__':
    main()
