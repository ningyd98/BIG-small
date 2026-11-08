"""Resolve the predeclared B runtime using wheel metadata and bound HTTPS."""

import json
import os
from pathlib import Path

import pip._vendor.urllib3.connection as urllib_connection
import pip._vendor.urllib3.util.connection as util_connection
from pip._internal.cli.main import main

from cloud_edge_robot_arm.datasets.external.network import DirectNetworkBackend, validate_network_policy

HERE = Path(__file__).resolve().parent.parent
POLICY = validate_network_policy({"mode": "direct", "interface": "enp7s0",
    "dns_servers": ["223.5.5.5", "223.6.6.6"],
    "allowed_hosts": ["pypi.org", "files.pythonhosted.org"]})
backend = DirectNetworkBackend(POLICY)


def bound_connection(address, timeout=None, source_address=None, socket_options=None):
    stream = backend.connect_tcp(address[0], address[1], timeout=60)
    return stream.get_extra_info("socket")


if __name__ == "__main__":
    with (HERE / "dependency-policy-b.json").open("x") as stream:
        json.dump(POLICY, stream, indent=2)
    for key in list(os.environ):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            os.environ.pop(key)
    util_connection.create_connection = bound_connection
    urllib_connection.connection.create_connection = bound_connection
    argv = ["install", "--dry-run", "--ignore-installed", "--only-binary=:all:",
            "--disable-pip-version-check", "--no-input", "--no-cache-dir",
            "--index-url", "https://pypi.org/simple", "--report",
            str(HERE / "steps/runtime-b-resolver.json"),
            "torch==2.10.0", "torchvision==0.25.0", "transformers==5.22.2",
            "compressed-tensors==0.20.1", "accelerate==1.3.0", "timm==1.0.14",
            "pydantic==2.13.5", "loguru==0.7.3", "psutil==7.2.2", "einops==0.8.0"]
    with (HERE / "steps/runtime-b-resolver-argv.json").open("x") as stream:
        json.dump(argv, stream, indent=2)
    raise SystemExit(main(argv))
