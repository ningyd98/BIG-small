"""Install isolated wheels; pip HTTPS sockets use the repository's strict bound backend."""

import os
from pathlib import Path

import pip._vendor.urllib3.connection as urllib_connection
import pip._vendor.urllib3.util.connection as util_connection
from pip._internal.cli.main import main

from cloud_edge_robot_arm.datasets.external.network import (
    DirectNetworkBackend,
    validate_network_policy,
)

HERE = Path(__file__).parent
POLICY = validate_network_policy(
    {
        "mode": "direct",
        "interface": "enp7s0",
        "dns_servers": ["223.5.5.5", "223.6.6.6"],
        "allowed_hosts": ["pypi.tuna.tsinghua.edu.cn", "pypi.org", "files.pythonhosted.org"],
    }
)
backend = DirectNetworkBackend(POLICY)


def bound_connection(address, timeout=None, source_address=None, socket_options=None):
    stream = backend.connect_tcp(address[0], address[1], timeout=60)
    return stream.get_extra_info("socket")


util_connection.create_connection = bound_connection
urllib_connection.connection.create_connection = bound_connection
for k in list(os.environ):
    if k.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
        os.environ.pop(k)
# Use target to avoid spawning an unpatched child; executable scripts are not needed.
target = HERE.parents[3] / ".venv-vlm/lib/python3.12/site-packages"
args = [
    "install",
    "--target",
    str(target),
    "--index-url",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "--disable-pip-version-check",
    "--no-input",
    "--no-cache-dir",
    "--report",
    str(HERE / "internvl8-dependency-install.json"),
    "torch==2.6.0",
    "torchvision==0.21.0",
    "transformers==4.48.3",
    "accelerate==1.3.0",
    "bitsandbytes==0.45.2",
    "timm==1.0.14",
    "sentencepiece==0.2.0",
    "einops==0.8.0",
    "fastapi==0.115.8",
    "uvicorn==0.34.0",
]
raise SystemExit(main(args))
