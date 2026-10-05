from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[1] / "scripts/run_native_clock_prefix_v2.py"
    spec = importlib.util.spec_from_file_location("native_clock_prefix_cli_v2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_only_validates_original_inputs_without_creating_output(
    cli, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "never-created"
    config = tmp_path / "policy.json"
    calls = []

    def validate(path):
        calls.append(path)
        return {"config_path": str(path), "config_sha256": "a" * 64, "source_hashes": {}}

    def forbidden(*args, **kwargs):
        pytest.fail("INPUTS_ONLY must not create an application/job/lease/backend or network")

    monkeypatch.setattr(cli, "validate_startup_inputs_v2", validate)
    monkeypatch.setattr(cli.NativeClockPrefixApplicationV2, "from_startup", forbidden)
    assert cli.main(["--config", str(config), "--output", str(output)]) == 0
    assert calls == [config]
    assert not output.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "INPUTS_ONLY"
    assert result["actual_execution"] == "NOT_RUN"
    assert result["inputs"]["config_sha256"] == "a" * 64


def test_explicit_execute_uses_factory_and_returns_unchanged_receipt(
    cli, tmp_path, monkeypatch, capsys
):
    config, output = tmp_path / "policy.json", tmp_path / "fresh"
    receipt = {"prefix_complete": True, "native_utc": "UNAVAILABLE", "originals": ["raw"]}
    calls = []

    class Application:
        def execute_once(self):
            calls.append("execute_once")
            return receipt

    def factory(path, *, output):
        calls.append((path, output))
        return Application()

    monkeypatch.setattr(cli.NativeClockPrefixApplicationV2, "from_startup", factory)
    assert cli.main(["--config", str(config), "--output", str(output), "--execute-once"]) == 0
    assert calls == [(config, output), "execute_once"]
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "EXCLUDED_SOURCE_ONLY_PREFIX"
    assert result["native_utc"] == "UNAVAILABLE"
    assert result["receipt"] == receipt
    assert not output.exists()  # This integration effect is CPU-only, never an actual app.


@pytest.mark.parametrize("complete", [False, None, "true", 1])
def test_incomplete_or_non_boolean_receipt_keeps_originals_and_exit_one(
    cli, tmp_path, monkeypatch, capsys, complete
):
    receipt = {"prefix_complete": complete, "originals": ["failed A", "reset", "failed B"]}

    class Application:
        def execute_once(self):
            return receipt

    monkeypatch.setattr(
        cli.NativeClockPrefixApplicationV2, "from_startup", lambda *a, **k: Application()
    )
    assert cli.main(["--output", str(tmp_path / "fresh"), "--execute-once"]) == 1
    assert json.loads(capsys.readouterr().out)["receipt"] == receipt


def test_validation_failure_never_calls_factory_or_creates_output(
    cli, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "never-created"

    def invalid(path):
        raise ValueError("original policy pin changed")

    def forbidden(*args, **kwargs):
        pytest.fail("failed inputs-only validation must never execute")

    monkeypatch.setattr(cli, "validate_startup_inputs_v2", invalid)
    monkeypatch.setattr(cli.NativeClockPrefixApplicationV2, "from_startup", forbidden)
    assert cli.main(["--output", str(output)]) == 1
    streams = capsys.readouterr()
    assert not streams.out and not output.exists()
    assert "original policy pin changed" in streams.err


def test_factory_failure_does_not_retry_or_remove_partial_originals(
    cli, tmp_path, monkeypatch, capsys
):
    output = tmp_path / "partial"
    output.mkdir()
    original = output / "original.json"
    original.write_text('{"failure":"retained"}\n')
    before = original.read_bytes()
    calls = []

    def rejected(path, *, output):
        calls.append(output)
        raise ValueError("fresh excluded output required")

    monkeypatch.setattr(cli.NativeClockPrefixApplicationV2, "from_startup", rejected)
    assert cli.main(["--output", str(output), "--execute-once"]) == 1
    assert calls == [output] and original.read_bytes() == before
    assert "fresh excluded output required" in capsys.readouterr().err


def test_output_argument_is_required_before_any_effect(cli, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("missing arguments must be rejected before effects")

    monkeypatch.setattr(cli, "validate_startup_inputs_v2", forbidden)
    monkeypatch.setattr(cli.NativeClockPrefixApplicationV2, "from_startup", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main([])
    assert error.value.code == 2
