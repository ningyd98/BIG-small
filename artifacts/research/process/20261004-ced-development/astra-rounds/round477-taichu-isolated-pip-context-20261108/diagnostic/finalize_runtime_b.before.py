"""Install only the complete upstream-verified R475 resolver closure, offline."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
R475 = HERE.parent / "round475-taichu-dependency-mirror-20261108"
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/wheelhouse-b-discovery"
ENV = ROOT / ".venv-taichu-round473/runtime-b"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def main():
    resolved = json.loads((HERE / "steps/runtime-b-mirror-resolver.json").read_text())
    files = []
    for row in resolved["install"]:
        url = row["download_info"]["url"]
        filename = unquote(Path(urlsplit(url).path).name)
        if urlsplit(url).hostname not in ["pypi.tuna.tsinghua.edu.cn", "mirrors.tuna.tsinghua.edu.cn",
                                          "pypi.org", "files.pythonhosted.org"]:
            raise ValueError("resolver source outside exact allowlist")
        pin = json.loads((R475 / "discovery-pins" / (filename + ".json")).read_text())
        receipt = json.loads((R475 / "body-receipts" / (filename + ".json")).read_text())
        expected = row["download_info"]["archive_info"]["hashes"]["sha256"]
        path = CACHE / filename
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if expected != pin["sha256"] or actual != expected or path.stat().st_size != pin["size"]:
            raise ValueError("final resolver closure is not upstream verified")
        if not receipt.get("cache_reused") and receipt.get("pin_before_body") is not True:
            raise ValueError("body was not preceded by a durable pin")
        files.append({**pin, "cache_path": str(path), "actual_sha256": actual, "verified": True})
    if len({r["name"] for r in files}) != len(files):
        raise ValueError("duplicate distributions in closure")
    save(HERE / "wheel-manifest-b.json", {"files": files, "total_bytes": sum(r["size"] for r in files),
         "discovery_round": "R475", "all_upstream_verified": True})
    subprocess.run([sys.executable, "-m", "venv", str(ENV)], check=True)
    argv = [str(ENV / "bin/python"), "-m", "pip", "install", "--no-index", "--no-deps",
            "--disable-pip-version-check", "--report", str(HERE / "steps/pip-install-b.json"),
            *[row["cache_path"] for row in files]]
    save(HERE / "runtime-decision-b.json", {"route": "B", "venv": str(ENV),
         "torch": "2.10.0", "torchvision": "0.25.0", "transformers": "5.22.2",
         "compressed_tensors": "0.20.1", "use_optimized_inference": True,
         "dequantize": False, "device": "cuda:0", "base_borrowed": False,
         "install_argv": argv, "superseded_unexecuted_installer": "install_runtime_b.py"})
    result = subprocess.run(argv, capture_output=True)
    (HERE / "steps/pip-install-b.stdout").write_bytes(result.stdout)
    (HERE / "steps/pip-install-b.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("offline B installation failed; raw output retained")
    checks = {}
    for name, args in [("check", ["-m", "pip", "check"]), ("freeze", ["-m", "pip", "freeze", "--all"])]:
        result = subprocess.run([str(ENV / "bin/python"), *args], capture_output=True)
        (HERE / f"steps/pip-{name}-b.stdout").write_bytes(result.stdout)
        (HERE / f"steps/pip-{name}-b.stderr").write_bytes(result.stderr)
        checks[name] = result.returncode
    save(HERE / "steps/step-02-runtime-b-install.json", {"status": "PASS" if not any(checks.values())
         else "DEPENDENCY_INCOMPATIBLE", "checks": checks, "wheel_count": len(files)})
    print("B_RUNTIME_INSTALLED", len(files), checks, flush=True)


if __name__ == "__main__":
    main()
