"""Software-only independent frozen-source lexical-root regression probe."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from cloud_edge_robot_arm.vision.worker_owner import pin_worker_source_inventory

root = Path(tempfile.mkdtemp(prefix='worker-owner-path-probe-'))
real = root / 'realroot'
real.mkdir()
(real / 'source.py').write_text('SOURCE = "software-only"\n', encoding='utf-8')
alias = root / 'alias'
alias.symlink_to(real, target_is_directory=True)
expected = {'source.py': hashlib.sha256((real / 'source.py').read_bytes()).hexdigest()}
lexical = alias / '..' / 'realroot'
print(json.dumps({'scope': 'SOFTWARE_ONLY', 'lexical_root': str(lexical),
                  'normalized_root': os.path.abspath(lexical),
                  'symlink_ancestor_before_normalization': str(alias),
                  'ancestor_is_symlink': alias.is_symlink(), 'expected': expected}, indent=2))
try:
    pin_worker_source_inventory(alias, expected, required_paths={'source.py'})
except ValueError as error:
    print('CONTROL direct symlink root rejected:', error)
else:
    raise AssertionError('control unexpectedly allowed direct symlink root')
try:
    returned = pin_worker_source_inventory(lexical, expected, required_paths={'source.py'})
except ValueError as error:
    print('EXPECTED guarded alias/../realroot rejection:', error)
else:
    print('COUNTEREXAMPLE alias/../realroot accepted:', json.dumps(dict(returned), sort_keys=True))
    print('QUALIFIED_FINDING lexical symlink ancestor erased before checking')
