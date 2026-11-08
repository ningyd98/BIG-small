"""Append only the official processor's required requests dependency closure."""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
S473 = HERE.parent / "round473-taichu-quantized-dual-image-20261108"
ROOT = HERE.parents[5]
sys.path.insert(0, str(S473 / "implementation"))
import resolve_runtime_b_mirror as gate


def main():
    gate.R475 = HERE
    gate.PINS = HERE / "discovery-pins"
    gate.BODIES = HERE / "body-receipts"
    gate.PINS.mkdir(exist_ok=False)
    gate.BODIES.mkdir(exist_ok=False)
    before = json.loads((S473 / "wheel-manifest-b.json").read_text())["files"]
    constraints = HERE / "original-64-constraints.txt"
    constraints.write_text("\n".join(row["name"]+"=="+row["version"] for row in before)+"\n")
    for key in list(os.environ):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            os.environ.pop(key)
    gate.util_connection.create_connection = gate.bound_connection
    gate.urllib_connection.connection.create_connection = gate.bound_connection
    gate.pip_download.Downloader.__call__ = gate.download
    gate.pip_download.BatchDownloader.__call__ = gate.batch
    argv = ["install", "--dry-run", "--ignore-installed", "--only-binary=:all:",
            "--disable-pip-version-check", "--no-input", "--no-cache-dir", "--progress-bar", "off",
            "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--constraint", str(constraints),
            "--report", str(HERE / "resolver.json"), "requests==2.34.2"]
    gate.save(HERE / "resolver-argv.json", argv)
    if gate.main(argv):
        raise RuntimeError("requests closure resolution failed")
    from packaging.utils import canonicalize_name

    fixed = {canonicalize_name(row["name"]): row["version"] for row in before}
    selected = json.loads((HERE / "resolver.json").read_text())["install"]
    additions = []
    for row in selected:
        name = canonicalize_name(row["metadata"]["name"])
        version = row["metadata"]["version"]
        if name in fixed:
            if fixed[name] != version:
                raise ValueError("existing runtime version would change")
        else:
            filename = row["download_info"]["url"].split("/")[-1].split("#")[0]
            additions.append({"name": name, "version": version, "path": str(gate.CACHE / filename)})
    gate.save(HERE / "new-packages.json", {"packages": additions})
    clean = dict(os.environ)
    for key in ["PYTHONPATH", "PYTHONHOME"]:
        clean.pop(key, None)
    clean["PYTHONNOUSERSITE"] = "1"
    python = ROOT / ".venv-taichu-round473/runtime-b/bin/python"
    cache_cwd = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
    argv = [str(python), "-m", "pip", "install", "--no-index", "--no-deps",
            "--disable-pip-version-check", "--report", str(HERE / "install-report.json"),
            *[row["path"] for row in additions]]
    installed = subprocess.run(argv, env=clean, cwd=cache_cwd, capture_output=True)
    (HERE / "install.stdout").write_bytes(installed.stdout)
    (HERE / "install.stderr").write_bytes(installed.stderr)
    if installed.returncode:
        raise RuntimeError("offline processor dependency installation failed")
    check = subprocess.run([str(python), "-m", "pip", "check"], env=clean,
                           cwd=cache_cwd, capture_output=True)
    (HERE / "pip-check.stdout").write_bytes(check.stdout)
    (HERE / "pip-check.stderr").write_bytes(check.stderr)
    code = "import importlib.metadata as m,json;print(json.dumps({n:m.version(n) for n in " + repr(list(fixed)) + "}))"
    output = subprocess.run([str(python), "-c", code], env=clean, cwd=cache_cwd,
                            capture_output=True, text=True, check=True)
    actual = json.loads(output.stdout)
    unchanged = actual == fixed
    gate.save(HERE / "dependency-verification.json", {"status": "PASS" if check.returncode == 0 and unchanged
        else "FAILED", "pip_check_rc": check.returncode, "original_64_versions_unchanged": unchanged,
        "original_versions": actual, "added_packages": additions})
    print("PROCESSOR_DEPENDENCIES", check.returncode, unchanged, additions, flush=True)


if __name__ == "__main__":
    main()
