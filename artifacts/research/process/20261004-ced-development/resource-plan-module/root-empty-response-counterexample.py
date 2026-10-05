"""Software parser counterexample; no source/physical acceptance or cloud calls."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cloud_edge_robot_arm.research.resource_plan import _read_request_costs
from tests.test_research_resource_plan import request_fixture

with TemporaryDirectory(prefix="bigsmall-empty-response-review-") as folder:
    root = Path(folder)
    rows, wire = request_fixture(root)
    # Preserve the original SHA of a nonempty response while supplying a different,
    # empty raw response, and change the numeric ledger to match the empty length.
    (root / wire[1]["response_path"]).write_bytes(b"")
    rows[1]["serialized_received_bytes"] = 0
    (root / "requests.json").write_text(json.dumps(rows))
    (root / "wire.json").write_text(json.dumps(wire))
    try:
        result = _read_request_costs(root, "requests.json", "wire.json")
    except ValueError as error:
        print(json.dumps({"software_only": True, "rejected": True, "reason": str(error)}))
    else:
        print(json.dumps({"software_only": True, "rejected": False, "costs": result}))
