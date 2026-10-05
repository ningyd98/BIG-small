"""Build only from declared immutable bases + four owned live final files.

Run after root releases both dependencies. No import or simulator/model call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
PACKAGE = Path(__file__).resolve().parent
OWNED = [
    'src/cloud_edge_robot_arm/repositories/event_autonomy/protocol.py',
    'src/cloud_edge_robot_arm/repositories/event_autonomy/memory.py',
    'src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py',
    'tests/test_visual_bootstrap_repository.py',
]
WORKER = ['src/cloud_edge_robot_arm/vision/worker_owner.py','tests/test_visual_worker_owner.py']
BOOTSTRAP = ['src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py','tests/test_visual_bootstrap.py']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def declared(package):
    hashes = json.loads((package / 'source-hashes.json').read_text())
    for name, expected in hashes.items():
        assert sha((package / 'source' / name).read_bytes()) == expected, name
    return hashes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker-package', type=Path, required=True)
    parser.add_argument('--bootstrap-package', type=Path, required=True)
    args=parser.parse_args()
    old = PACKAGE.parent / 't12-live-verification-routing-module'
    base = declared(old)
    worker = declared(args.worker_package)
    bootstrap = declared(args.bootstrap_package)
    output=PACKAGE/'source'
    if output.exists():
        raise SystemExit('Refuse overwriting an existing candidate source; archive it separately first')
    output.mkdir()
    files = {}
    for name, expected in base.items():
        files[name]=(old/'source'/name,expected)
    for names, package, hashes in [(WORKER,args.worker_package,worker),(BOOTSTRAP,args.bootstrap_package,bootstrap)]:
        for name in names:
            files[name]=(package/'source'/name,hashes[name])
    for name in OWNED:
        files[name]=(REPO/name,sha((REPO/name).read_bytes()))
    for name,(source,expected) in sorted(files.items()):
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        assert sha(target.read_bytes())==expected,name
    hashes={name:expected for name,(_,expected) in sorted(files.items())}
    (PACKAGE/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    summary={'source_count':len(files),'manifest_sha256':sha((PACKAGE/'source-hashes.json').read_bytes()),
             'old_route_package':str(old),'old_route_count':len(base),
             'worker_package':str(args.worker_package),'bootstrap_package':str(args.bootstrap_package),
             'owned':OWNED,'old_route_frozen_sources_unchanged':True,'actual_calls':0}
    (PACKAGE/'ownership.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
