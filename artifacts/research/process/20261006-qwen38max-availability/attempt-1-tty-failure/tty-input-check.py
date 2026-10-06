"""Check real terminal echo handling without credentials or network calls."""
import argparse
import importlib.util
import json
import os
import termios
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
if not output.is_relative_to(BASE):
    raise ValueError('output outside test directory')
spec = importlib.util.spec_from_file_location('availability_probe', BASE / 'probe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fd = os.open('/dev/tty', os.O_RDWR)
before = termios.tcgetattr(fd)
record = {'network_calls': 0, 'real_credential_used': False, 'echo_disabled_observed': False}

def fake_hidden_input(prompt):
    record['echo_disabled_observed'] = not bool(termios.tcgetattr(fd)[3] & termios.ECHO)
    assert record['echo_disabled_observed'], 'terminal echo remains enabled'
    return 'TTY_CHECK_NON_SECRET'

module.getpass.getpass = fake_hidden_input
try:
    assert module.read_key() == 'TTY_CHECK_NON_SECRET'
    assert termios.tcgetattr(fd) == before, 'terminal settings were not restored'
    record.update({'status': 'PASS', 'terminal_state_restored': True})
except Exception as exc:
    record.update({'status': 'FAIL', 'error_type': type(exc).__name__, 'error_message': str(exc),
                   'terminal_state_restored': termios.tcgetattr(fd) == before})
finally:
    os.close(fd)
output.parent.mkdir(parents=True, exist_ok=True)
with output.open('x') as f:
    json.dump(record, f, indent=2)
    f.write('\n')
print(json.dumps(record))
raise SystemExit(0 if record['status'] == 'PASS' else 1)
