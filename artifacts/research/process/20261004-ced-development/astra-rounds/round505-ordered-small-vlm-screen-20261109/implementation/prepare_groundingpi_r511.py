"""R511 rootless original archive extraction; no model or source mutation."""
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def extract_regular(archive, destination, expected):
    destination=Path(destination)
    assert not destination.exists()
    if any(p.is_symlink() for p in [destination,*destination.parents]):
        raise ValueError("symlink destination")
    with tarfile.open(archive) as tar:
        members=tar.getmembers();names=[];payload=[]
        for member in members:
            path=PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or any(p in ("..", ".", "") for p in member.name.split("/")):
                raise ValueError("non-regular or unsafe member")
            name=str(path)
            if name in names:raise ValueError("duplicate member")
            data=tar.extractfile(member).read()
            if name not in expected or hashlib.sha256(data).hexdigest()!=expected[name]:
                raise ValueError("unregistered member or hash difference")
            names.append(name);payload.append((name,data))
        if set(names)!=set(expected):raise ValueError("incomplete archive")
    destination.mkdir(parents=True,exist_ok=False)
    for name,data in payload:
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("xb") as stream:stream.write(data)


def main():
    root=Path.cwd();cache=root/"datasets/model-cache/ordered-small-vlm-20261109";sdk=cache/"sdk/GroundingPI-98641f0b8e"
    out=root/"artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi"
    entry=json.loads((sdk/"third_party/manifest.json").read_text())["dependencies"]["transformers"]
    old=[{"path":str(p.relative_to(sdk/"vendor")),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in (sdk/"vendor").rglob("*") if p.is_file()]
    archive=sdk/entry["archive"];assert hashlib.sha256(archive.read_bytes()).hexdigest()==entry["archive_sha256"]
    destination=sdk/entry["destination"];extract_regular(archive,destination,entry["files"])
    for name,digest in entry["files"].items():assert hashlib.sha256((destination/name).read_bytes()).hexdigest()==digest
    for row in old:assert hashlib.sha256((sdk/"vendor"/row["path"]).read_bytes()).hexdigest()==row["sha256"]
    import sys
    sys.path.insert(0,str(sdk))
    from models.dependency_contract import verify_dependency
    revision=verify_dependency("transformers",root=sdk)
    with (out/"source-verification-r511.json").open("x") as stream:
        json.dump({"status":"PASS","members":len(entry["files"]),"revision":revision,"archive_sha256":entry["archive_sha256"],"old_wrong_tree_unchanged":old,"official_fork_directory":str(destination)},stream,ensure_ascii=False,indent=2);stream.write("\n")
    print("SOURCE_EXTRACTION_PASS",len(entry["files"]),revision)


if __name__=="__main__":main()
