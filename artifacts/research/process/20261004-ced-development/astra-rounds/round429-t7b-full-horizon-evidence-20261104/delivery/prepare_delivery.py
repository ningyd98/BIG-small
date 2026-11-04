"""Build an explicit, hashed software/evidence delivery list; never stage raw trees."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent
PRODUCTS = [
    'src/cloud_edge_robot_arm/vision/native_completion_horizon.py',
    'src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py',
    'tests/test_native_completion_horizon_v1.py',
    'tests/test_native_completion_horizon_originals_v1.py',
]
ROUNDS = [
    'round429-t7b-full-horizon-evidence-20261104',
    'round430-t7b-horizon-static-20261104',
    'round431-t7b-full-horizon-original-joins-20261104',
    'round432-t7b-horizon-type-variable-20261104',
    'round433-t7b-original-failure-retention-20261104',
]
OMIT = {'post-run-fixture-originals', '__pycache__', 'cache', 'tmp', 'resources',
        'xdg-cache', 'pycache', 'mypy-cache', 'ruff-cache', 'e2e-artifacts',
        'dashboard', 'local-raw'}
ALLOWED = {'.py', '.md', '.json', '.jsonl', '.log', '.xml', '.patch'}
DELIVERY_ALLOWED = {'pre-git-state.json', 'baseline-preservation.json', 'prepare_delivery.py'}
paths = set(PRODUCTS)
for name in ROUNDS:
    for here, dirs, files in os.walk(BASE / name, followlinks=False):
        dirs[:] = [d for d in dirs if d not in OMIT]
        for filename in files:
            path = Path(here) / filename
            if 'delivery' in path.relative_to(BASE / name).parts and filename not in DELIVERY_ALLOWED:
                continue
            if path.suffix not in ALLOWED or path.is_symlink():
                raise RuntimeError(f'Unclassified delivery candidate: {path}')
            paths.add(str(path.relative_to(ROOT)))
assert len([x for x in paths if x.startswith(('src/', 'tests/'))]) == 4
assert all(not any(part in OMIT for part in Path(x).parts) for x in paths)
assert all((ROOT / x).stat().st_size < 2_000_000 for x in paths)
check = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'], input=b'\0'.join(x.encode() for x in sorted(paths))+b'\0', cwd=ROOT, capture_output=True, check=False)
assert check.returncode in (0, 1), check.stderr
ignored = sorted(x.decode() for x in check.stdout.split(b'\0') if x)
ignore_path = ROUND / 'delivery/ignored-selected-paths.json'
ignore_path.write_text(json.dumps({'paths':ignored,'policy':'Only this explicit reviewed list may use git add -f; no recursive force-add.'},indent=2)+'\n')
paths.add(str(ignore_path.relative_to(ROOT)))
entries=[]
for name in sorted(paths):
    data=(ROOT/name).read_bytes()
    entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest_path=ROUND/'delivery/selected-manifest.json'
manifest={'schema':'research.explicit-delivery.v1','head_before':'aecf1fd836ff08819edb053a2e87b4b2a83235b0','branch':'research/20261004-continuation','software_files':PRODUCTS,'files':entries,'self_excluded_from_hashes':str(manifest_path.relative_to(ROOT)),'local_only_full_raw':True,'complete_remote_reproduction_bundle':False,'excluded_directory_names':sorted(OMIT),'payload_bytes':sum(x['bytes'] for x in entries)}
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
paths.add(str(manifest_path.relative_to(ROOT)))
(ROUND/'delivery/paths.nul').write_bytes(b'\0'.join(x.encode() for x in sorted(paths))+b'\0')
print(json.dumps({'stage_paths':len(paths),'hashed_payloads':len(entries),'payload_bytes':manifest['payload_bytes'],'ignored_explicit_files':len(ignored),'full_raw_included':False},indent=2))
