"""Resolve once, then require exact wheel SHA hashes using bound physical sockets."""
import json
import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))
import pip._vendor.urllib3.connection as urllib_connection
import pip._vendor.urllib3.util.connection as util_connection
from pip._internal.cli.main import main
from cloud_edge_robot_arm.datasets.external.network import DirectNetworkBackend, validate_network_policy
POLICY = validate_network_policy({"mode": "direct", "interface": "enp7s0", "dns_servers": ["223.5.5.5", "223.6.6.6"], "allowed_hosts": ["pypi.tuna.tsinghua.edu.cn", "pypi.org", "files.pythonhosted.org"]})
backend = DirectNetworkBackend(POLICY)
def bound_connection(address, timeout=None, source_address=None, socket_options=None):
    return backend.connect_tcp(address[0], address[1], timeout=60).get_extra_info("socket")
util_connection.create_connection = bound_connection
urllib_connection.connection.create_connection = bound_connection
for key in list(os.environ):
    if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
        os.environ.pop(key)
base = ["install", "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--only-binary", ":all:", "--disable-pip-version-check", "--no-input", "--no-cache-dir"]
lmfe_only = "--lmfe-only" in sys.argv
stem = "minicpm-json" if lmfe_only else "minicpm-dependency"
resolved = HERE / (stem + "-resolution.json")
packages = ["lm-format-enforcer==0.11.3"] if lmfe_only else ["transformers==5.7.0", "huggingface-hub==1.5.0", "tokenizers==0.22.2", "regex==2025.10.22"]
code = main(base + ["--dry-run", "--upgrade", "--report", str(resolved)] + packages)
if code:
    raise SystemExit(code)
rows = json.loads(resolved.read_text())["install"]
lines = [f"{r['metadata']['name']}=={r['metadata']['version']} --hash=sha256:{r['download_info']['archive_info']['hashes']['sha256']}" for r in rows]
lock = HERE / (stem + "-requirements.txt")
lock.write_text("\n".join(lines) + "\n")
(HERE / "minicpm-pip-network-policy.json").write_text(json.dumps(POLICY, indent=2) + "\n")
raise SystemExit(main(base + ["--no-deps", "--upgrade", "--require-hashes", "--report", str(HERE / (stem + "-install.json")), "-r", str(lock)]))
