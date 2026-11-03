"""Read-only R413 collection inventory; no test behavior or assertions changed."""
import json
import os
from pathlib import Path

def pytest_collection_finish(session):
    rows = [{"nodeid": i.nodeid, "path": str(i.path), "markers": sorted({m.name for m in i.iter_markers()})} for i in session.items]
    with Path(os.environ["R413_COLLECTION"]).open("x",encoding="utf-8") as out:
        json.dump({"nodes": rows, "count": len(rows), "collection_errors": session.testsfailed}, out,ensure_ascii=False,indent=2)
        out.write("\n")
