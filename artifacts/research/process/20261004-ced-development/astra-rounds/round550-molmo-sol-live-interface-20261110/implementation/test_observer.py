"""CPU stub checks; no project imports, network, GPU or model operations."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from run_live import Probe


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.probe = Probe(Path(self.temp.name) / "probe")

    def test_post_delegates_identical_arguments_once_and_caps_before_second(self):
        calls = []
        body = {"model": "stub"}
        adapter = object()
        returned = {"choices": []}

        def original(*args, **kwargs):
            self.assertTrue((self.probe.output / "post-start-01.json").is_file())
            calls.append((args, kwargs))
            return returned

        wrapped = self.probe.wrap_post(original)
        self.assertIs(wrapped(adapter, "/v1/chat/completions", body), returned)
        self.assertIs(calls[0][0][0], adapter)
        self.assertIs(calls[0][0][2], body)
        self.assertEqual(calls[0][1], {})
        with self.assertRaisesRegex(RuntimeError, "exhausted"):
            wrapped(adapter, "/v1/chat/completions", body)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.probe.paid_starts, 1)

    def test_post_preserves_exception_and_consumes_start(self):
        failure = ValueError("stub failure")

        def original(*args, **kwargs):
            raise failure

        with self.assertRaises(ValueError) as caught:
            self.probe.wrap_post(original)(object(), "/v1/chat/completions", {})
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.probe.paid_starts, 1)

    def test_process_preserves_return_and_observation_without_mutation(self):
        payload = {"outcome": "STUB", "contract": None}
        returned = SimpleNamespace(model_dump=lambda **kwargs: payload)
        observation = SimpleNamespace(captured_at=datetime.now(UTC), checksum_sha256="stub")
        request = SimpleNamespace(observation=observation, request_id="stub-request")
        pipeline = object()
        calls = []

        def original(*args, **kwargs):
            calls.append((args, kwargs))
            return returned

        result = self.probe.wrap_process(original)(pipeline, request, planner="stub-planner")
        self.assertIs(result, returned)
        self.assertIs(calls[0][0][1], request)
        self.assertEqual(calls[0][1], {"planner": "stub-planner"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            json.loads((self.probe.output / "pipeline-return-01.json").read_text()), payload
        )

    def test_process_preserves_original_exception_even_when_capture_fails(self):
        failure = RuntimeError("original failure")
        request = SimpleNamespace(observation=None, request_id="stub-request")
        (self.probe.output / "pipeline-end-01.json").write_text("existing evidence")

        def original(*args, **kwargs):
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            self.probe.wrap_process(original)(object(), request)
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.probe.gaps[0]["error_type"], "FileExistsError")


if __name__ == "__main__":
    unittest.main()
