"""Behavior tests: preserve real pair order; reject missing/identical/mis-sized images."""
import base64
import copy
import io
import json
import sys
import unittest
from pathlib import Path
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))
from cloud_edge_robot_arm.vision.planner import VisualDecision
from adapter_contract import parse_request

class PairContract(unittest.TestCase):
    def setUp(self):
        bank = HERE.parent / "shared/scene-bank/cases/positive-03/initial-offline"
        self.raw = [(bank / n).read_bytes() for n in ("rgb.png", "depth.png")]
        self.schema = VisualDecision.model_json_schema()
        self.body = {"model": "candidate", "temperature": 0, "max_tokens": 512, "response_format": {"type": "json_object"}, "messages": [
            {"role": "system", "content": "Return supplied JSON. Schema: " + json.dumps(self.schema)},
            {"role": "user", "content": [{"type": "text", "text": "Task without oracle."}] + [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}} for b in self.raw]},
        ]}

    def test_native_pair_retains_original_png_order_and_schema(self):
        native, raw, schema = parse_request(self.body, model_name="candidate")
        self.assertEqual(raw, self.raw)
        self.assertEqual(schema, self.schema)
        content = native[1]["content"]
        self.assertEqual([c["type"] for c in content], ["image", "image", "text"])
        self.assertEqual(content[2]["text"], "Task without oracle.")
        for i in range(2):
            self.assertEqual(content[i]["image"].tobytes(), Image.open(io.BytesIO(self.raw[i])).convert("RGB").tobytes())

    def test_duplicate_or_missing_depth_fails_closed(self):
        for duplicate in (False, True):
            body = copy.deepcopy(self.body)
            parts = body["messages"][1]["content"]
            if duplicate:
                parts[-1] = copy.deepcopy(parts[-2])
            else:
                parts.pop()
            with self.assertRaises(ValueError):
                parse_request(body, model_name="candidate")

    def test_external_url_or_wrong_size_fails_closed(self):
        for malformed in ("https://example.org/image.png", "small"):
            body = copy.deepcopy(self.body)
            if malformed == "small":
                stream = io.BytesIO()
                Image.new("RGB", (64, 64)).save(stream, format="PNG")
                malformed = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()
            body["messages"][1]["content"][-1]["image_url"]["url"] = malformed
            with self.assertRaises(ValueError):
                parse_request(body, model_name="candidate")

if __name__ == "__main__":
    unittest.main()
