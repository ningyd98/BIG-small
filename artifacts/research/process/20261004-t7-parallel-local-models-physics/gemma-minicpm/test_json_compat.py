"""CPU-only real tokenizer grammar checks; synthetic syntax fixtures are not quality."""
import importlib
import json
import os
import sys
import unittest
from pathlib import Path
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))

class JsonIntegration(unittest.TestCase):
    def test_native_tokenizer_blocks_prose_and_accepts_complete_schema(self):
        try:
            module = importlib.import_module("lmfe_transformers_compat")
        except ImportError as exc:
            self.fail("native Transformers5 integration unavailable: " + str(exc))
        from transformers import AutoProcessor
        from lmformatenforcer import JsonSchemaParser
        from cloud_edge_robot_arm.vision.planner import VisualDecision
        from minicpm_bridge import array_schema
        import torch
        tokenizer = AutoProcessor.from_pretrained(HERE / "minicpm-model", local_files_only=True, trust_remote_code=False).tokenizer
        data = module.build_token_enforcer_tokenizer_data(tokenizer)
        prefix = module.build_transformers_prefix_allowed_tokens_fn(data, JsonSchemaParser(array_schema(VisualDecision.model_json_schema())))
        sentence = [tokenizer.eos_token_id]
        first_allowed = prefix(0, torch.tensor(sentence))
        self.assertNotIn(tokenizer.eos_token_id, first_allowed)
        self.assertNotIn(tokenizer.encode("not_json", add_special_tokens=False)[0], first_allowed)
        sample = '{"target_pixel":null,"destination_pixel":null,"target_label":"syntax_fixture","reported_confidence":0.5,"skills":[],"reason":"syntax_only"}'
        for token in tokenizer.encode(sample, add_special_tokens=False):
            self.assertIn(token, prefix(0, torch.tensor(sentence)))
            sentence.append(token)
        self.assertIn(tokenizer.eos_token_id, prefix(0, torch.tensor(sentence)))

if __name__ == "__main__":
    unittest.main()
