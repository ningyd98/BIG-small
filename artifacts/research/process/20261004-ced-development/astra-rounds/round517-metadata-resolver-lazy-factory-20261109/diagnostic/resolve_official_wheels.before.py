"""Resolve official PyPI JSON metadata before physical-route wheel downloads.

No synthetic wheels, no installer network, no model imports. The two official
source projects are candidates backed by their unchanged local pyproject files.
"""
import hashlib
import json
import os
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from packaging.requirements import Requirement
from packaging.version import Version, InvalidVersion
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.resolvelib import Resolver
from pip._vendor.resolvelib.providers import AbstractProvider
from pip._vendor.resolvelib.reporters import BaseReporter
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[5]
CACHE=ROOT/"datasets/model-cache/ordered-small-vlm-20261109"
SDK=CACHE/"sdk/GroundAnything-7791c0e0cf"
META=CACHE/"wheelhouse/groundanything-r515-metadata"
WHEELS=CACHE/"wheelhouse/groundanything-r515"
POLICY={"mode":"direct","interface":"enp7s0","dns_servers":["223.5.5.5","223.6.6.6"],"allowed_hosts":["pypi.org","files.pythonhosted.org"]}
TAGS=set(sys_tags())


@dataclass(frozen=True)
class Candidate:
    name:str
    version:str
    extras:frozenset


class MetadataProvider(AbstractProvider):
    def __init__(self):
        self.client=httpx.Client(transport=create_direct_transport(POLICY),trust_env=False,follow_redirects=True,timeout=httpx.Timeout(120,connect=20))
        self.cache={};self.details={};self.sources={}
        for folder in [SDK,SDK/"vendor/sglang"]:
            project=tomllib.loads((folder/"pyproject.toml").read_text())["project"]
            name=canonicalize_name(project["name"])
            self.sources[name]={"version":project["version"],"requires_dist":project.get("dependencies",[]),"path":str(folder)}

    def get(self,name,version=None):
        key=name+("-"+version if version else "-project")
        if key not in self.cache:
            path=META/(key+".raw.json")
            if path.exists():blob=path.read_bytes()
            else:
                url=f"https://pypi.org/pypi/{name}/"+(version+"/" if version else "")+"json"
                response=self.client.get(url);response.raise_for_status();blob=response.content
                with path.open("xb") as stream:stream.write(blob)
                print("METADATA",name,version or "releases",len(blob),flush=True)
            self.cache[key]=json.loads(blob)
        return self.cache[key]

    def identify(self,requirement_or_candidate):
        return canonicalize_name(requirement_or_candidate.name)

    def get_preference(self,identifier,resolutions,candidates,information,backtrack_causes):
        requirements=[i.requirement for i in information[identifier]]
        pinned=any(any(s.operator in ("==","===") and "*" not in s.version for s in r.specifier) for r in requirements)
        return (not pinned,identifier)

    def find_matches(self,identifier,requirements,incompatibilities):
        reqs=list(requirements[identifier]);bad=set(incompatibilities[identifier]);extras=frozenset(x for req in reqs for x in req.extras)
        if identifier in self.sources:
            versions=[self.sources[identifier]["version"]]
        else:
            releases=self.get(identifier)["releases"];versions=[]
            for text,files in releases.items():
                try:version=Version(text)
                except InvalidVersion:continue
                if version.is_prerelease or version.is_devrelease or not any(not row.get("yanked") for row in files):continue
                if all(not req.specifier or req.specifier.contains(version,prereleases=False) for req in reqs):versions.append(text)
            versions.sort(key=Version,reverse=True)
        def candidates():
            for version in versions:
                candidate=Candidate(identifier,version,extras)
                if candidate in bad or not all(self.is_satisfied_by(req,candidate) for req in reqs):continue
                if identifier in self.sources:
                    self.details[(identifier,version)]=self.sources[identifier]
                    yield candidate;continue
                data=self.get(identifier,version);python=data["info"].get("requires_python")
                if python and not Requirement("python"+python).specifier.contains("3.12.3",prereleases=True):continue
                options=[]
                for row in data["urls"]:
                    if row["packagetype"]!="bdist_wheel" or row.get("yanked"):continue
                    if not set(parse_wheel_filename(row["filename"])[3]) & TAGS:continue
                    if row.get("requires_python") and not Requirement("python"+row["requires_python"]).specifier.contains("3.12.3",prereleases=True):continue
                    options.append(row)
                if not options:continue
                self.details[(identifier,version)]={"version":version,"requires_dist":data["info"].get("requires_dist") or [],"artifact":options[0],"metadata_path":str(META/(identifier+"-"+version+".raw.json"))}
                yield candidate
        return candidates()

    def is_satisfied_by(self,requirement,candidate):
        return canonicalize_name(requirement.name)==candidate.name and (not requirement.specifier or requirement.specifier.contains(candidate.version,prereleases=True)) and requirement.extras.issubset(candidate.extras)

    def get_dependencies(self,candidate):
        result=[];detail=self.details[(candidate.name,candidate.version)]
        for text in detail["requires_dist"]:
            req=Requirement(text)
            if req.marker and not any(req.marker.evaluate({"extra":extra}) for extra in ("",*candidate.extras)):continue
            result.append(req)
        return result


def download(row):
    artifact=row["artifact"];path=WHEELS/artifact["filename"]
    if path.exists():
        with path.open("rb") as stream:checksum=hashlib.file_digest(stream,"sha256").hexdigest()
        assert path.stat().st_size==artifact["size"] and checksum==artifact["digests"]["sha256"]
        return {"name":row["name"],"path":str(path),"bytes":artifact["size"],"sha256":checksum,"reused":True}
    part=path.with_suffix(path.suffix+".part")
    for session in range(3):
        offset=part.stat().st_size if part.exists() else 0
        try:
            with httpx.Client(transport=create_direct_transport(POLICY),trust_env=False,follow_redirects=True,timeout=httpx.Timeout(120,connect=20)) as client:
                with client.stream("GET",artifact["url"],headers={"Range":f"bytes={offset}-"} if offset else {}) as response:
                    response.raise_for_status()
                    assert (offset==0 and response.status_code==200) or (offset>0 and response.status_code==206 and response.headers.get("content-range","").startswith(f"bytes {offset}-"))
                    with part.open("ab" if offset else "xb") as stream:
                        for chunk in response.iter_bytes(1024*1024):stream.write(chunk)
            break
        except (httpx.HTTPError,OSError):
            if session==2:raise
    assert part.stat().st_size==artifact["size"]
    with part.open("rb") as stream:checksum=hashlib.file_digest(stream,"sha256").hexdigest()
    assert checksum==artifact["digests"]["sha256"]
    part.rename(path)
    return {"name":row["name"],"path":str(path),"bytes":artifact["size"],"sha256":checksum,"url":artifact["url"]}


def main():
    META.mkdir(parents=True,exist_ok=True);WHEELS.mkdir(parents=True,exist_ok=True)
    provider=MetadataProvider()
    roots=[Requirement(text) for text in ["sglang==0.5.6.post2","grounding-anything==0.1.0","setuptools>=68","wheel","packaging","ninja","psutil","einops","PyYAML>=6,<7","torch==2.9.1","transformers==5.5.4","triton==3.5.1","sgl-kernel==0.3.20","flashinfer-python==0.5.3","flashinfer-cubin==0.5.3"]]
    resolved=Resolver(provider,BaseReporter()).resolve(roots,max_rounds=10000)
    selected=[]
    for name,candidate in sorted(resolved.mapping.items()):
        selected.append({"name":name,"version":candidate.version,"extras":sorted(candidate.extras),**provider.details[(name,candidate.version)]})
    # The official postoverride is separate from the satisfiable original graph.
    post=list(provider.find_matches("nvidia-cudnn-cu12",{"nvidia-cudnn-cu12":[Requirement("nvidia-cudnn-cu12==9.16.0.29")]},{"nvidia-cudnn-cu12":[]}))[0]
    post_row={"name":post.name,"version":post.version,"postoverride":True,**provider.details[(post.name,post.version)]}
    lock={"status":"METADATA_RESOLVED","source_sdk":"7791c0e0cf0236191bd868df9551c856c9b1b8f7","target_python":"3.12 Linux x86_64","roots":[str(req) for req in roots],"selected":selected,"official_postoverride":post_row,"policy":POLICY,"installed":False}
    with (HERE/"diagnostic/metadata-lock.json").open("x") as stream:json.dump(lock,stream,ensure_ascii=False,indent=2);stream.write("\n")
    jobs=[row for row in selected+[post_row] if "artifact" in row]
    print("CLOSURE_RESOLVED",len(selected),"WHEELS",len(jobs),"BYTES",sum(row["artifact"]["size"] for row in jobs),flush=True)
    records=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(download,row):row for row in jobs}
        for future in as_completed(futures):
            record=future.result();records.append(record)
            (HERE/"diagnostic/download-progress.local.json").write_text(json.dumps({"verified":records,"expected":len(jobs)},ensure_ascii=False,indent=2)+"\n")
            print("WHEEL_VERIFIED",record["name"],record["bytes"],flush=True)
    with (HERE/"diagnostic/wheelhouse-lock.json").open("x") as stream:json.dump({"status":"PASS","files":records,"count":len(records)},stream,ensure_ascii=False,indent=2);stream.write("\n")
    print("ALL_OFFICIAL_WHEELS_PASS",len(records),flush=True)


if __name__=="__main__":main()
