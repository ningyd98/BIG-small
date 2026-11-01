"""等待已启动的 T3 批次结束，再串行启动已冻结的剩余覆盖清单。"""
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
MANIFEST = json.loads((HERE / 'planned-stages.json').read_text())
PREDECESSORS = [f'p6_t3_{i:02}' for i in range(1, 10)] + ['r223_env_corrected']
cutoff = MANIFEST['original_wall_start']['started_epoch_s'] + 28800 - 900
while True:
    if (ROUND / 'STOP_BETWEEN_STAGES').exists() or (HERE / 'STOP_BETWEEN_STAGES').exists():
        raise SystemExit('STOP_BETWEEN_STAGES before continuation')
    if time.time() >= cutoff:
        raise SystemExit('Original wall allowance exhausted before continuation')
    results = [ROUND / 'implementation' / stage / 'result.json' for stage in PREDECESSORS]
    if all(p.exists() for p in results):
        values = [json.loads(p.read_text()) for p in results]
        if not all(v.get('reaped') is True for v in values):
            raise RuntimeError('Predecessor cleanup not confirmed')
        print('T3 and R223 predecessor results complete; starting frozen continuation', flush=True)
        os.execv(sys.executable, [sys.executable, str(HERE / 'run_remaining.py'), '--run'])
    time.sleep(2)
