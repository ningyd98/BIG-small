"""原生点解析与本地加载契约；模型对象仅在外部推理边界使用 CPU 夹具。"""

from __future__ import annotations

import hashlib
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tests.test_rgbd_observations import observation_payload


def test_native_point_exact_grammar():
    from cloud_edge_robot_arm.vision.molmo_pointing import parse_native_point

    result = parse_native_point('<points coords="1 1 458 557">yellow block.</points><|im_end|>')
    assert (result.status, result.normalized_1000, result.object_index) == ("POINT", (458, 557), 1)
    assert parse_native_point(" ABSENT\n").status == "ABSENT"
    assert parse_native_point("ABSENT<|endoftext|>").normalized_1000 is None
    assert parse_native_point('<points coords="1 2 0 1000">block</points>').normalized_1000 == (
        0,
        1000,
    )


@pytest.mark.parametrize(
    "raw",
    [
        '<points coords="1 1 2 3">x</points>' * 2,
        '<points coords="1 1 2 3" coords="1 1 2 3">x</points>',
        '<points coords="1 1 2 3 2 4 5">x</points>',
        '<points coords="1 1 2 3;1 2 4 5">x</points>',
        '<points id="x" coords="1 1 2 3">x</points>',
        '<points coords="1 1 2 3"><b>x</b></points>',
        '<points coords="0 1 2 3">x</points>',
        '<points coords="2 1 2 3">x</points>',
        '<points coords="1 0 2 3">x</points>',
        '<points coords="1 1 -1 3">x</points>',
        '<points coords="1 1 +1 3">x</points>',
        '<points coords="1 1 2.0 3">x</points>',
        '<points coords="1 1 1e2 3">x</points>',
        '<points coords="1 1 NaN 3">x</points>',
        '<points coords="1 1 Inf 3">x</points>',
        '<points coords="1 1 1001 3">x</points>',
        '<points coords="1 1 2 1001">x</points>',
        '<points coords="1 1 ２ 3">x</points>',
        '<points coords="1 1 2 3">x</point>',
        '<points coords="1 1 ' + "9" * 10000 + ' 3">x</points>',
        'Here: <points coords="1 1 2 3">x</points>',
        'ABSENT <points coords="1 1 2 3">x</points>',
        '<points coords="1 1 2 3">ABSENT</points>',
        '<points coords="1 1 2 3">not visible</points>',
        '<points coords="1 1 2 3">no points</points>',
        "ABSENT<|im_end|><|im_end|>",
        "ABSENT<|im_end|><|endoftext|>",
        "",
        "x" * 16385,
    ],
)
def test_native_point_rejects_ambiguity(raw):
    from cloud_edge_robot_arm.vision.molmo_pointing import parse_native_point

    result = parse_native_point(raw)
    assert result.status == "INVALID"
    assert result.normalized_1000 is None


class Tensor:
    def __init__(self, data):
        self.data = np.asarray(data, dtype=np.int64)
        self.shape = self.data.shape
        self.dtype = "int64"

    def __getitem__(self, key):
        return Tensor(self.data[key])

    def tolist(self):
        return self.data.tolist()

    def to(self, device):
        assert device == "cuda:0"
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def contiguous(self):
        return self

    def view(self, dtype):
        return self

    def numpy(self):
        return self.data


class Context:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def native_fixture(tmp_path, monkeypatch, *, fail=False, cap=False, limit=2):
    import cloud_edge_robot_arm.vision.molmo_pointing as module

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    rows = []
    for i in range(26):
        p = model_dir / f"file-{i}"
        p.write_bytes(b"fixture")
        rows.append({"Path": p.name, "Size": 7, "Sha256": hashlib.sha256(b"fixture").hexdigest()})
    manifest = tmp_path / "assets.json"
    manifest.write_text(json.dumps({"repo": "allenai/Molmo2-ER", "files": rows}))
    monkeypatch.setattr(
        module, "ASSET_MANIFEST_SHA256", hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    conversations, decodes, loads = [], [], []

    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            conversations.append(messages)
            return {"input_ids": Tensor([[1, 2]])} if kwargs["tokenize"] else "rendered fixture"

        def decode(self, ids, **kwargs):
            decodes.append(kwargs)
            return '<points coords="1 1 458 557">block</points><|im_end|>'

    processor = Processor()
    processor.tokenizer = processor

    class Model:
        def eval(self):
            return self

        def parameters(self):
            return iter([SimpleNamespace(device=SimpleNamespace(type="cuda"), dtype="bf16")])

        def generate(self, **kwargs):
            assert kwargs["do_sample"] is False
            assert kwargs["max_new_tokens"] == 512
            if fail:
                raise RuntimeError("fixture generation failure")
            return Tensor([[1, 2] + [3] * (512 if cap else 1)])

    def load(*args, **kwargs):
        loads.append(kwargs)
        return Model()

    torch = SimpleNamespace(
        __version__="2.6.0+cu124",
        bfloat16="bf16",
        uint8="uint8",
        Tensor=Tensor,
        manual_seed=lambda n: None,
        inference_mode=Context,
        autocast=lambda *a, **k: Context(),
        cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: None),
    )
    transformers = SimpleNamespace(
        __version__="4.57.1",
        AutoProcessor=SimpleNamespace(from_pretrained=lambda *a, **k: processor),
        AutoModelForImageTextToText=SimpleNamespace(from_pretrained=load),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    provider = module.MolmoPointProvider(
        model_directory=model_dir,
        asset_manifest=manifest,
        raw_directory=tmp_path / "raw",
        generation_limit=limit,
    )
    return provider, conversations, decodes, loads


def test_native_single_rgb_binding(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    provider, conversations, decodes, loads = native_fixture(tmp_path, monkeypatch)
    observation = RGBDObservation.model_validate(observation_payload())
    result = provider.point(observation, "red block")
    assert result.result.status == "POINT"
    assert result.observation_checksum == observation.checksum_sha256
    assert result.rgb_sha256 == observation.evidence()["rgb_sha256"]
    assert result.query_sha256 == hashlib.sha256(b"red block").hexdigest()
    assert len(loads) == 1
    for conversation in conversations:
        assert len(conversation) == 1 and conversation[0]["role"] == "user"
        content = conversation[0]["content"]
        assert [p["type"] for p in content] == ["text", "image"]
        assert content[1]["image"].size == (2, 2)
        assert "SECRET_ORACLE" not in content[0]["text"]
    assert decodes[0] == {"skip_special_tokens": False, "clean_up_tokenization_spaces": False}
    assert provider.generation_calls_started == 1
    assert provider.model_loads_started == 1
    assert (tmp_path / "raw/request-0001/raw-response.txt").exists()


def test_native_budget_counts_failed_starts(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    provider, _, _, loads = native_fixture(tmp_path, monkeypatch, fail=True, limit=2)
    observation = RGBDObservation.model_validate(observation_payload())
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fixture generation failure"):
            provider.point(observation, "red block")
    with pytest.raises(RuntimeError, match="budget"):
        provider.point(observation, "red block")
    assert provider.generation_calls_started == 2 and len(loads) == 1
    assert len(list((tmp_path / "raw").glob("request-*/failure.json"))) == 2


def test_native_output_cap_is_not_accepted(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    provider, _, _, _ = native_fixture(tmp_path, monkeypatch, cap=True)
    result = provider.point(RGBDObservation.model_validate(observation_payload()), "red block")
    assert result.result.status == "INVALID"
    assert result.evidence["reached_cap"] is True


def test_decode_failure_retains_generated_tokens(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    provider, _, _, _ = native_fixture(tmp_path, monkeypatch)

    def fail_decode(*args, **kwargs):
        raise RuntimeError("fixture decoder failure")

    monkeypatch.setattr(provider._processor, "decode", fail_decode)
    with pytest.raises(RuntimeError, match="decoder failure"):
        provider.point(RGBDObservation.model_validate(observation_payload()), "red block")
    assert provider.generation_calls_started == provider.generation_calls_completed == 1
    folder = tmp_path / "raw/request-0001"
    assert json.loads((folder / "output-token-ids.json").read_text()) == [3]
    assert (folder / "generation-completed.json").exists()
    assert json.loads((folder / "failure.json").read_text())["generation_calls_completed"] == 1
    assert not (folder / "raw-response.txt").exists()
