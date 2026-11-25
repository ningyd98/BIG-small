"""The sealed clock fixture imports a private native generation in its own interpreter."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

TIMING_TEST = Path(__file__).with_name("test_recovery_route_v2.py")


class FrozenTimingTest(pytest.Item):
    def runtest(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "--noconftest",
                "-p",
                "no:cacheprovider",
                "-q",
                f"{self.path}::{self.name}",
            ],
            cwd=self.config.rootpath,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode:
            pytest.fail(result.stdout, pytrace=False)


class FrozenTimingFile(pytest.File):
    def collect(self):
        for node in ast.parse(self.path.read_bytes()).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                yield FrozenTimingTest.from_parent(self, name=node.name)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    if module_path == TIMING_TEST:
        return FrozenTimingFile.from_parent(parent, path=module_path)
    return None
