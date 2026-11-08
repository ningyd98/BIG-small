"""Create the predeclared A runtime without changing any existing environment."""

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
ENV = ROOT / ".venv-taichu-round473"
BASE = ROOT / ".venv-minicpm/lib/python3.12/site-packages"
POLICY = {"mode": "direct", "interface": "enp7s0",
          "dns_servers": ["223.5.5.5", "223.6.6.6"],
          "allowed_hosts": ["pypi.org", "files.pythonhosted.org"]}


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    save("dependency-policy.json", POLICY)
    borrowed = []
    for distribution in importlib.metadata.distributions(path=[str(BASE)]):
        borrowed.append({"name": distribution.metadata["Name"], "version": distribution.version,
                         "metadata_sha256": sha((distribution.read_text("METADATA") or "").encode()),
                         "record_sha256": sha((distribution.read_text("RECORD") or "").encode())})
    save("borrowed-runtime-manifest.json", {"path": str(BASE), "mode": "READ_ONLY",
         "distributions": sorted(borrowed, key=lambda r: r["name"].lower())})
    wheelhouse = CACHE / "wheelhouse-a"
    wheelhouse.mkdir(exist_ok=False)
    manifest = []
    for package, version in [("compressed-tensors", "0.13.0"), ("loguru", "0.7.3")]:
        prior = HERE / f"diagnostic/{package}-{version}-pypi.raw.json"
        if prior.exists():
            metadata_raw = prior.read_bytes()
        else:
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                              timeout=60) as client:
                response = client.get(f"https://pypi.org/pypi/{package}/{version}/json")
                response.raise_for_status()
            metadata_raw = response.content
            with prior.open("xb") as stream:
                stream.write(metadata_raw)
        metadata = json.loads(metadata_raw)
        wheels = [row for row in metadata["urls"] if row["filename"].endswith("py3-none-any.whl")]
        if len(wheels) != 1:
            raise ValueError("expected one universal wheel")
        row = wheels[0]
        manifest.append({"name": package, "version": version, "filename": row["filename"],
                         "url": row["url"], "size": row["size"],
                         "sha256": row["digests"]["sha256"],
                         "metadata_sha256": sha(metadata_raw),
                         "requires_dist": metadata["info"].get("requires_dist") or []})
    save("wheel-manifest-a.json", {"wheels": manifest, "borrowed": "borrowed-runtime-manifest.json"})
    for row in manifest:
        with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                          timeout=60, follow_redirects=True) as client:
            response = client.get(row["url"])
            response.raise_for_status()
        raw = response.content
        if len(raw) != row["size"] or sha(raw) != row["sha256"]:
            raise ValueError("wheel integrity mismatch")
        with (wheelhouse / row["filename"]).open("xb") as stream:
            stream.write(raw)
    # venv/ensurepip use only the Python installation's bundled local files.
    subprocess.run([sys.executable, "-m", "venv", str(ENV)], check=True)
    site = ENV / "lib/python3.12/site-packages"
    with (site / "r473-readonly-base.pth").open("x") as stream:
        stream.write(str(BASE) + "\n")
    argv = [str(ENV / "bin/python"), "-m", "pip", "install", "--no-index", "--no-deps",
            "--disable-pip-version-check", "--report", str(HERE / "steps/pip-install-a.json"),
            *[str(wheelhouse / r["filename"]) for r in manifest]]
    save("runtime-decision-a.json", {"route": "A", "created_at": datetime.now(UTC).isoformat(),
         "torch": "2.6.0+cu124", "transformers": "5.7.0", "compressed_tensors": "0.13.0",
         "quantization": "official FP8_DYNAMIC compressed-tensors; run_compressed=True",
         "loader": "Transformers AutoModel and official pinned local custom code",
         "base_mode": "READ_ONLY", "venv": str(ENV), "install_argv": argv,
         "supported_by_package_declared_requirements": True,
         "compatibility_status": "PRECHECK_PENDING"})
    result = subprocess.run(argv, capture_output=True)
    (HERE / "steps/pip-install-a.stdout").write_bytes(result.stdout)
    (HERE / "steps/pip-install-a.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("offline installation failed; see raw pip output")
    checks = {}
    for name, args in [("check", ["-m", "pip", "check"]), ("freeze", ["-m", "pip", "freeze", "--all"])]:
        result = subprocess.run([str(ENV / "bin/python"), *args], capture_output=True)
        (HERE / f"steps/pip-{name}-a.stdout").write_bytes(result.stdout)
        (HERE / f"steps/pip-{name}-a.stderr").write_bytes(result.stderr)
        checks[name] = result.returncode
    save("steps/step-02-runtime-a-install.json", {"status": "PASS" if not any(checks.values())
         else "DEPENDENCY_INCOMPATIBLE", "checks": checks, "installed_wheels": manifest})
    print(json.dumps({"runtime": str(ENV), "checks": checks}), flush=True)


if __name__ == "__main__":
    main()
