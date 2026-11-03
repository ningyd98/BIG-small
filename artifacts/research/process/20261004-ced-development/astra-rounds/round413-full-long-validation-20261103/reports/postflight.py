"""Read-only final provenance/ownership audit after the real controller ends."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parents[1]
R415 = ROUND.parent / 'round415-unstarted-tail-resource-parent-handoff-20261103'
BASELINE = 'ab18abd0f82a024b62f4423c946c6585f8d18c65'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output(['git', *args], cwd=ROOT, env=environment).decode().strip()


def alive(identity):
    try:
        stat = (Path('/proc') / str(identity['pid']) / 'stat').read_text()
    except FileNotFoundError:
        return False
    return int(stat[stat.rfind(')') + 2:].split()[19]) == int(identity['starttime_ticks'])


def main():
    receipt = read(ROUND / 'postflight/controller-terminal.json')
    assert receipt['actual_terminal_received'] and receipt['exit_code'] == 0
    assert receipt['unified_exec_session'] == 24010
    assert read(R415 / 'resume-terminal.json')['status'] == 'FINISHED'
    assert (R415 / 'resume-complete.json').exists()
    pins = read(ROUND / 'preflight/runtime-source-pins.json')['files']
    drift = [item['path'] for item in pins if sha(ROOT / item['path']) != item['sha256']]
    assert not drift, drift
    results = []
    live_owned = []
    identities_count = 0
    prerequisites = []
    for path in sorted((ROUND / 'specs').glob('*.json')):
        spec = read(path)
        directory = Path(spec['directory'])
        result_path = directory / 'result.json'
        assert result_path.exists(), spec['id']
        result = read(result_path)
        assert not result.get('source_drift') and not result.get('remaining_live') and not result.get('errors'), spec['id']
        if result.get('launched'):
            assert result.get('reaped'), spec['id']
            identities = read(directory / 'owned-process-identities.json')
            identities_count += len(identities)
            live_owned.extend({'stage_id': spec['id'], **identity} for identity in identities if alive(identity))
        if spec.get('nodes') and result.get('launched'):
            prerequisite = read(directory / 'prerequisite.json')
            prerequisites.append({'stage_id': spec['id'], 'accepted': prerequisite['accepted_prerequisite'],
                                  'sha256': sha(directory / 'prerequisite.json')})
        results.append({'stage_id': spec['id'], 'state': result['state'], 'launched': result.get('launched'),
                        'returncode': result.get('returncode'), 'result_sha256': sha(result_path)})
    assert not live_owned, live_owned
    assert all(item['accepted'] for item in prerequisites)
    head = git('rev-parse', 'HEAD')
    branch = git('branch', '--show-current')
    assert head == BASELINE and branch == 'research/20261004-continuation'
    staged = git('diff', '--cached', '--name-only')
    assert not staged, 'Existing index changes must be preserved and reviewed separately.'
    scopes = ['src', 'scripts', 'tests', 'configs', 'docs', 'dashboard', 'pyproject.toml',
              '.github', 'README.md', 'CHANGELOG.md', 'AGENTS.md']
    source_diff = git('diff', '--no-ext-diff', '--ignore-submodules=all', '--name-status', 'HEAD', '--', *scopes)
    assert not source_diff, source_diff
    main_head = git('rev-parse', 'main')
    assert main_head == 'fdb2e94d3d7bc041e7d958f2514a08406fad4668'
    protected = [
        'artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-baseline',
        'artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-h3']
    gitlinks = git('ls-files', '-s', '--', *protected).splitlines()
    assert len(gitlinks) == 2
    assert all(line.startswith('160000 ddbeb92a1aa1dfa8039f6260d6b5887c58072383 0\t') for line in gitlinks)
    from cloud_edge_robot_arm.real_robot.provenance import current_source_tree_hash
    official_hash = current_source_tree_hash()
    assert official_hash == read(ROUND / 'preflight/official-source-hash.json')['source_tree_hash']
    progress = [json.loads(line) for line in (ROUND / 'progress.jsonl').read_text().splitlines()]
    summary = read(ROUND / 'reports/summary.json')
    assert summary['final'] and summary['python_started'] == 4751 and not summary['integrity_issues']
    report = {'schema': 'r413.final-source-ownership-audit.v1', 'observed_utc': datetime.now(UTC).isoformat(),
              'batch_started_utc': next(row['at_utc'] for row in progress if row['event'] == 'batch_start'),
              'batch_completed_utc': read(R415 / 'resume-complete.json')['at_utc'],
              'tested_commit': head, 'branch': branch, 'official_source_tree_hash': official_hash,
              'runtime_pin_count': len(pins), 'runtime_source_drift': drift,
              'tracked_development_source_diff': source_diff, 'whole_workspace_clean_claimed': False,
              'main_head': main_head, 'protected_gitlinks_outer_index_only': gitlinks,
              'protected_gitlink_directories_entered': False, 'index_empty_before_delivery': True,
              'refs_before_delivery': git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes', 'refs/tags').splitlines(),
              'stage_records': results, 'observed_owned_identities': identities_count,
              'owned_identities_still_alive_in_approved_host_proc': live_owned,
              'python_prerequisite_records': prerequisites,
              'original075_no_junit': not (ROUND / 'implementation/py-module-075/junit.xml').exists(),
              'python_junit_confirmed': summary['junit_confirmed_python_nodes'],
              'python_started': summary['python_started'], 'full_raw_remote_package_claimed': False,
              'source_algorithm_note': 'Official real_robot fingerprint, normalized NUL audit manifest, and Phase12 provenance hashes have distinct documented algorithms; their different digest strings are not compared as if they were the same algorithm.'}
    target = ROUND / 'postflight/checks.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'source_matches': True, 'head': head, 'runtime_pins': len(pins),
                      'owned_still_alive': len(live_owned), 'python_prerequisites': len(prerequisites)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
