"""Shared, artifact-only controls for the preregistered R486 comparison."""

import functools
import hashlib
import importlib.metadata
import inspect
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
BASELINE = HERE.parent / "round473-taichu-quantized-dual-image-20261108"
sys.path.insert(0, str(BASELINE / "implementation"))
from process_pair import CACHE, process

RAW = CACHE / "actual/round486"


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_sources():
    for item in read(HERE / "plan.json")["input_sha256"]:
        path = ROOT / item["path"]
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
            raise ValueError("R486 fixed input drift: " + item["path"])
    for item in read(BASELINE / "source-manifest.json")["files"]:
        if sha(CACHE / item["name"]) != item["sha256"]:
            raise ValueError("official model source drift: " + item["name"])


def base_versions():
    prior = read(HERE.parent / "round481-taichu-processor-required-imports-20261108/dependency-verification.json")
    expected = dict(prior["original_versions"])
    expected.update({row["name"]: row["version"] for row in prior["added_packages"]})
    records = []
    base_site = ROOT / ".venv-taichu-round473/runtime-b/lib/python3.12/site-packages"
    for name, version in sorted(expected.items()):
        dist = importlib.metadata.distribution(name)
        location = Path(dist.locate_file("")).resolve()
        if dist.version != version or location != base_site:
            raise ValueError("base distribution changed or shadowed: " + name)
        records.append({"name": name, "version": dist.version, "location": str(location)})
    if len(records) != 68:
        raise ValueError("unexpected base distribution count")
    return records


def mode_features(processor, thinking):
    tokenizer = processor.tokenizer
    name = "apply_chat_template"
    had_override = name in tokenizer.__dict__
    previous_override = tokenizer.__dict__.get(name)
    original = tokenizer.apply_chat_template
    traces = []

    @functools.wraps(original)
    def render(*args, **kwargs):
        if "enable_thinking" in kwargs:
            raise ValueError("unexpected prior thinking override")
        kwargs["enable_thinking"] = thinking
        prompt = original(*args, **kwargs)
        traces.append({"enable_thinking": thinking,
                       "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                       "assistant_suffix": prompt.rsplit("<|im_start|>assistant\n", 1)[1]})
        return prompt

    tokenizer.apply_chat_template = render
    try:
        features, evidence = process(processor)
    finally:
        if had_override:
            tokenizer.apply_chat_template = previous_override
        else:
            del tokenizer.apply_chat_template
        restored = (name in tokenizer.__dict__) == had_override and tokenizer.apply_chat_template == original
        if not restored:
            raise RuntimeError("tokenizer instance method was not precisely restored")
    expected_suffix = "<think>\n" if thinking else "<think>\n\n</think>\n\n"
    if len(traces) != 1 or traces[0]["assistant_suffix"] != expected_suffix:
        raise ValueError("thinking policy did not reach the actual template")
    decoded = tokenizer.decode(features["input_ids"][0].tolist(), skip_special_tokens=False)
    if not decoded.endswith(expected_suffix):
        raise ValueError("decoded model input has unexpected assistant suffix")
    evidence.update(thinking=thinking, template_calls=traces,
                    tokenizer_override_restored=restored,
                    effective_assistant_suffix=expected_suffix)
    return features, evidence, decoded


def kernel_bindings():
    from transformers.models.qwen3_5 import modeling_qwen3_5 as module

    names = ["torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule",
             "causal_conv1d_fn", "causal_conv1d_update"]
    records = {}
    for name in names:
        pending = [getattr(module, name)]
        visited = set()
        selected = []
        while pending:
            function = pending.pop()
            if id(function) in visited or not inspect.isfunction(function):
                continue
            visited.add(id(function))
            wrapped = getattr(function, "__wrapped__", None)
            if wrapped is not None:
                pending.append(wrapped)
            for key, cell in zip(function.__code__.co_freevars, function.__closure__ or ()):
                value = cell.cell_contents
                if key == "implementation" and callable(value):
                    selected.append({"module": value.__module__, "qualname": value.__qualname__,
                                     "source_file": inspect.getsourcefile(value)})
                if inspect.isfunction(value):
                    pending.append(value)
        records[name] = {"selected_implementations": selected}
    return module, records


def preflight(profile):
    from transformers import AutoProcessor

    check_sources()
    directory = RAW / ("processor-" + profile)
    directory.mkdir(parents=True, exist_ok=False)
    processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
                                             local_files_only=True, use_fast=False)
    modes = {}
    decoded_inputs = {}
    for label, thinking in [("ON", True), ("OFF", False)]:
        features, evidence, decoded = mode_features(processor, thinking)
        ids = features["input_ids"][0].tolist()
        save(directory / (label + "-input-ids.json"), ids)
        (directory / (label + "-decoded-input.txt")).write_text(decoded)
        save(directory / (label + "-processor.json"), evidence)
        modes[label] = evidence
        decoded_inputs[label] = decoded
        if label == "ON":
            prior = read(CACHE / "actual/model-run-b-r481/request-1/input-token-ids.json")[0]
            if ids != prior:
                raise ValueError("ON input tokens differ from the original successful run")
    historical = read(BASELINE / "steps/processor-b-r481.json")
    for key in ["pixel_values", "num_patches", "image_grid_thw"]:
        if not modes["ON"]["features"][key] == modes["OFF"]["features"][key] == historical["features"][key]:
            raise ValueError("visual tensor changed between modes: " + key)
    if decoded_inputs["ON"][:-len(modes["ON"]["effective_assistant_suffix"])] != decoded_inputs["OFF"][:-len(modes["OFF"]["effective_assistant_suffix"])]:
        raise ValueError("input text changed beyond the assistant thinking suffix")
    if profile == "fla":
        base = read(HERE / "processor-base.json")
        for label in modes:
            if modes[label]["features"] != base["modes"][label]["features"]:
                raise ValueError("FLA profile input differs from base profile")
    _, bindings = kernel_bindings()
    fla_selected = all(any(row["module"].startswith("fla.")
                           for row in bindings[name]["selected_implementations"])
                       for name in ["torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule"])
    if fla_selected != (profile == "fla"):
        raise ValueError("unexpected effective FLA dispatch")
    result = {"status": "PASS", "profile": profile, "modes": modes,
              "raw_directory": str(directory), "base_68": base_versions(),
              "kernel_bindings": bindings, "effective_fla_selected": fla_selected,
              "source_bytes_unchanged": True, "scope": "COMPLETE_PROCESSOR_NO_MODEL_LOAD"}
    save(HERE / ("processor-" + profile + ".json"), result)
    print(json.dumps({"status": "PASS", "profile": profile,
                      "tokens": {key: value["input_tokens"] for key, value in modes.items()},
                      "effective_fla_selected": fla_selected}), flush=True)


if __name__ == "__main__":
    preflight(sys.argv[1])
