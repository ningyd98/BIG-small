"""Run the existing paired design with an externally frozen second-version source manifest."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROUND = Path(__file__).resolve().parent
V1 = ROUND.parent / "round-g1-radial-native-timing-20261125"
DRIVER_SHA = "98b5c8dd78eb0e6cae01161c6013206d05ccaee22f491b928fe05868be6f04aa"


def prior():
    driver = V1 / "pixel_timing.py"
    assert hashlib.sha256(driver.read_bytes()).hexdigest() == DRIVER_SHA
    sys.path.insert(0, str(V1))
    spec = importlib.util.spec_from_file_location("frozen_v1_timing", driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = prior()
    release = json.loads((ROUND / "detector-source.public.json").read_bytes())
    assert release["parent_generation"] == module.GENERATION
    module.SOURCES = release["candidate_detector_files_sha256"]
    # The frozen driver starts its five workers via __file__. Re-enter this wrapper in
    # each fresh interpreter so it verifies and loads the same frozen candidate again.
    module.__file__ = __file__
    module.main()


if __name__ == "__main__":
    main()
