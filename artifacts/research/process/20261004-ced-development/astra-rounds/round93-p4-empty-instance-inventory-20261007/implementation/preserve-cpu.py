import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

out = Path(__file__).resolve().parent
stage = sys.argv[1]
assert stage in {"RED", "GREEN"}
source = Path("/tmp/bigsmall-t12-p4-r93-" + stage.lower())
target = out / "cpu-originals" / stage
assert source.is_dir() and not source.is_symlink()
assert not target.exists() and not target.is_symlink()
shutil.copytree(source, target, symlinks=True)
files = []
links = []
for path in sorted(source.rglob("*")):
    relative = path.relative_to(source)
    copied = target / relative
    if path.is_symlink():
        link = os.readlink(path)
        assert copied.is_symlink() and os.readlink(copied) == link
        links.append({"path": str(relative), "kind": "symlink", "target": link})
    elif path.is_file():
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        preserved = copied.read_bytes()
        assert preserved == raw
        files.append({"path": str(relative), "bytes": len(raw), "sha256": digest})
report = {"stage": stage, "source": str(source), "preserved": str(target), "regular_file_count": len(files),
          "total_regular_bytes": sum(row["bytes"] for row in files), "symlinks": links, "files": files,
          "scope": "CPU_ONLY_COMPLETE_LOCAL_ORIGINALS; SQLite copied/hash only, no connection"}
with (out / (stage + ".cpu-manifest.json")).open("x") as file:
    json.dump(report, file, indent=2)
print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))
