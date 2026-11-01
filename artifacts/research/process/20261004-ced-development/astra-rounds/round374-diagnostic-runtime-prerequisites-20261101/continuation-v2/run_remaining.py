"""按 Astra 原额度续跑尚未启动的节点；不重试历史失败或改写原始证据。"""
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
MANIFEST = json.loads((HERE / 'planned-stages.json').read_text())
spec = importlib.util.spec_from_file_location('r374_runner', HERE.parent / 'run_diagnostics.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def members(pgid):
    found = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            raw = (p / 'stat').read_text()
            fields = raw[raw.rfind(')') + 2:].split()
            if int(fields[2]) == pgid and fields[0] != 'Z':
                found.append({'pid': int(p.name), 'pgid': pgid,
                              'starttime': fields[19], 'state': fields[0],
                              'cmdline': (p / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return found


def main():
    mismatches = [r['path'] for r in MANIFEST['inputs']
                  if hashlib.sha256((ROOT / r['path']).read_bytes()).hexdigest() != r['sha256']]
    if mismatches:
        raise RuntimeError({'input_drift': mismatches})
    if runner.source_check()['drift']:
        raise RuntimeError('Original R373 source baseline changed')
    if sys.argv[1:] == ['--inspect']:
        print(json.dumps({'input_pins_verified': len(MANIFEST['inputs']),
                          'groups': len(MANIFEST['groups']),
                          'children': sum(len(g['children']) for g in MANIFEST['groups'])}))
        return
    if sys.argv[1:] != ['--run']:
        raise SystemExit('Use --inspect or --run')
    predecessors = [f'p6_t3_{i:02}' for i in range(1, 10)] + ['r223_env_corrected']
    missing = [s for s in predecessors if not (HERE.parent / 'implementation' / s / 'result.json').exists()]
    if missing:
        raise RuntimeError({'T3_predecessors_not_terminal': missing})
    ledger_path = HERE / 'budget-ledger.jsonl'
    ledger = ledger_path.open('x')
    cutoff = MANIFEST['original_wall_start']['started_epoch_s'] + MANIFEST['max_wall_s'] - MANIFEST['reserve_report_s']
    for group in MANIFEST['groups']:
        spent = 0.0
        for planned in group['children']:
            remaining = group['budget_s'] - spent
            wall_remaining = cutoff - time.time()
            effective = min(planned['timeout_s'], remaining - MANIFEST['cleanup_reserve_s'],
                            wall_remaining - MANIFEST['cleanup_reserve_s'])
            if (HERE / 'STOP_BETWEEN_STAGES').exists() or effective <= 0:
                row = {'stage_id': planned['id'], 'group': group['group'], 'state': 'NOT_RUN_BUDGET',
                       'group_spent_s': spent, 'group_remaining_s': remaining,
                       'wall_remaining_s': wall_remaining}
                ledger.write(json.dumps(row) + '\n'); ledger.flush()
                continue
            child = HERE / 'children' / planned['id']
            child.mkdir(parents=True, exist_ok=False)
            actual = {**planned, 'timeout_s': effective}
            save(child / 'stages.json', [actual])
            runner.ROUND = child
            identity = {}
            original_monitor = runner.monitor

            def captured_monitor(process, started, stage, out, err, signals, result_state):
                identity.update(pid=process.pid, pgid=os.getpgid(process.pid),
                                members_at_launch=members(process.pid))
                save(child / 'process-identity.json', identity)
                return original_monitor(process, started, stage, out, err, signals, result_state)

            runner.monitor = captured_monitor
            started = time.monotonic()
            cleanup = {'signals': []}
            try:
                runner.run(planned['id'])
            finally:
                runner.monitor = original_monitor
                if identity:
                    pgid = identity['pgid']
                    cleanup['after_runner'] = members(pgid)
                    if cleanup['after_runner']:
                        os.killpg(pgid, signal.SIGTERM)
                        cleanup['signals'].append('SIGTERM')
                        until = time.monotonic() + 5
                        while members(pgid) and time.monotonic() < until:
                            time.sleep(0.1)
                        if members(pgid):
                            os.killpg(pgid, signal.SIGKILL)
                            cleanup['signals'].append('SIGKILL')
                            until = time.monotonic() + 5
                            while members(pgid) and time.monotonic() < until:
                                time.sleep(0.1)
                    cleanup['remaining_live'] = members(pgid)
                elapsed = time.monotonic() - started
                spent += elapsed
                save(child / 'cleanup.json', cleanup)
                row = {'stage_id': planned['id'], 'group': group['group'],
                       'effective_timeout_s': effective, 'charged_monotonic_s': elapsed,
                       'group_spent_s': spent, 'group_budget_s': group['budget_s'],
                       'ended_utc': datetime.now(UTC).isoformat()}
                ledger.write(json.dumps(row) + '\n'); ledger.flush()
            if cleanup.get('remaining_live'):
                raise RuntimeError('Owned descendants remain; no next child launch')
    ledger.close()
    save(HERE / 'completion.json', {'state': 'ALL_GROUPS_ACCOUNTED',
                                   'ended_utc': datetime.now(UTC).isoformat(),
                                   'source_after': runner.source_check()})


if __name__ == '__main__':
    main()
