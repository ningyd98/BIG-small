"""Replay current nominal-role transport from historical originals, with no real opener."""

import argparse
import io
import json
import os
import shutil
import socket
import urllib.request
from pathlib import Path
from unittest.mock import patch

import probe_scope as scope
from run_paid_probe import guarded_attempt
from scripts import probe_rgbd_roles as roles

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.research.freeze_evidence import (
    _offline_reader_adapter_kwargs,
    _read_frame,
    verify_role_probe_evidence,
)
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, _NoSolRedirect
from cloud_edge_robot_arm.vision.role_models import RoleProviderSnapshot, cloud_request_settings

OUT = scope.ROOT / scope.PLAN["replay_output"]


def deny(*args, **kwargs):
    raise AssertionError("network access is forbidden during historical replay")


class HistoricalOpener:
    def __init__(self, url, request, response):
        self.url = url
        self.request = request
        self.response = response
        self.calls = 0

    def build(self, *handlers):
        scope.require(
            any(isinstance(x, _NoSolRedirect) for x in handlers)
            and any(isinstance(x, urllib.request.ProxyHandler) and not x.proxies for x in handlers),
            "original sealed adapter lost the no-redirect/no-proxy boundary",
        )
        return self

    def open(self, sent, *, timeout):
        self.calls += 1
        scope.require(self.calls == 1, "fixture received a retry")
        scope.require(sent.full_url == self.url and sent.method == "POST", "fixture route differs")
        scope.require(
            sent.data == self.request, "current serialized bytes differ from historical wire"
        )
        scope.require(not sent.get_header("Authorization"), "credentials unexpectedly present")
        return io.BytesIO(self.response)


def expect_rejection(action, expected):
    try:
        action()
    except ValueError as error:
        scope.require(expected in str(error), "negative control failed for an unregistered reason")
    else:
        raise ValueError("negative control did not reject")


def replay():
    interfaces = {
        row.split(":", 1)[0].strip() for row in Path("/proc/net/dev").read_text().splitlines()[2:]
    }
    scope.require(
        os.environ["B0_OUTER_NET_NS"] != os.readlink("/proc/self/ns/net") and interfaces == {"lo"},
        "a fresh isolated network namespace is required",
    )
    history, original = scope.preflight_inputs()
    old_audit = verify_role_probe_evidence(history)
    scope.require(
        not old_audit["available"]
        and any(
            "reconstructed nominal role probe gate rejected source/settings/wire" in x
            for x in old_audit["errors"]
        ),
        "expected independence check on historical role source changed",
    )
    settings = original["request_settings"]
    kwargs = _offline_reader_adapter_kwargs(settings)
    base_url = kwargs["base_url"]
    snapshot = ModelConfigSnapshot(
        provider=settings["provider"],
        model=settings["model"],
        endpoint=base_url,
        weight_digest=settings["weight_digest"],
        quantization=settings["quantization"],
        image_size=tuple(settings["image_size"]),
        generation_parameters=settings["generation_parameters"],
        timeout_s=settings["timeout_s"],
        coordinate_system=settings["coordinate_system"],
        grasp_profile=settings["grasp_profile"],
    )
    planner = RGBDPlannerAdapter(
        **(
            kwargs
            | {
                "model_snapshot": snapshot,
                "allow_paid": True,
                "timeout_s": settings["timeout_s"],
            }
        )
    )
    planner.role_config_version = settings["config_version"]
    scope.require(
        cloud_request_settings(planner) == settings, "sealed request settings did not reconstruct"
    )
    role = RoleProviderSnapshot(**original["bundle"]["cloud_snapshot"])
    OUT.mkdir(parents=True, exist_ok=False)
    fixture_output = OUT / "fixture-wire"
    fixture_output.mkdir()
    fence = scope.SendFence(
        OUT / "fixture-slots",
        {
            "scope": "HISTORICAL_WIRE_REPLAY",
            "real_http_sends": 0,
        },
    )
    dispatch = guarded_attempt(fence, roles._attempt, settings)
    url = base_url + settings["chat_path"]
    calls = []
    for index, previous in enumerate(original["attempts"]):
        case = history / f"attempt-{index:02d}"
        frame = _read_frame(case)
        archived_request = (case / "request.raw").read_bytes()
        archived_response = (case / "response.raw").read_bytes()
        fake = HistoricalOpener(url, archived_request, archived_response)
        request = InitialPlanningRequest(
            request_id=f"cloud-role-probe-{index:02d}",
            user_instruction=original["probe_config"]["instruction"],
            scene=SceneSummary(scene_version=1, updated_at=frame.observation.captured_at),
            observation=frame.observation,
        )
        with patch.object(urllib.request, "build_opener", fake.build):
            attempt = dispatch(
                planner, request, frame, fixture_output, index, role, request_settings=settings
            )
        stored = fixture_output / case.name
        scope.require(
            fake.calls == 1
            and attempt["status"] == "COMPLETE"
            and (stored / "request.raw").read_bytes() == archived_request
            and (stored / "response.raw").read_bytes() == archived_response,
            f"history replay failed for slot {index}",
        )
        reserved = json.loads((fence.root / f"send-{index:02d}.json").read_bytes())
        scope.require(
            reserved["request_sha256"] == previous["request_sha256"]
            and reserved["payload_length"] == len(archived_request),
            "reserved fixture slot does not bind actual serialized bytes",
        )
        for name in (
            "parsed",
            "grounded",
            "target_hit",
            "destination_hit",
            "transport_two_images",
            "request_sha256",
            "response_sha256",
            "serialized_sent_bytes",
            "serialized_received_bytes",
            "parsed_json",
            "target_offline_check",
            "destination_offline_check",
        ):
            scope.require(attempt[name] == previous[name], f"archive comparison changed {name}")
        cost = attempt["cost_ledger"]["requests"]
        scope.require(
            len(cost) == 1
            and cost[0]["status"] == "SUCCESS"
            and cost[0]["sent_at"] is not None
            and cost[0]["monetary_cost"] is None,
            "unexpected fixture ledger result",
        )
        calls.append(
            {
                "index": index,
                "fixture_open_calls": fake.calls,
                "raw_request_sha256": attempt["request_sha256"],
                "raw_response_sha256": attempt["response_sha256"],
                "parsed": attempt["parsed"],
                "target_hit": attempt["target_hit"],
                "destination_hit": attempt["destination_hit"],
            }
        )
    scope.require(fence.cursor == 4, "not all expected fixture attempts reached the opener")
    expect_rejection(lambda: fence.reserve(4, settings["chat_path"], b""), "excess")
    expect_rejection(lambda: fence.reserve(0, settings["chat_path"], b""), "duplicate")
    expect_rejection(lambda: scope.SendFence(fence.root, {}), "previously started")
    crashed = scope.SendFence(OUT / "fixture-interrupted", {"scope": "FIXTURE"})
    crashed.reserve(0, settings["chat_path"], b"test reservation before interruption")
    expect_rejection(lambda: scope.SendFence(crashed.root, {}), "previously started")
    bad_url = urllib.request.Request(url + "/different", data=archived_request, method="POST")
    expect_rejection(
        lambda: HistoricalOpener(url, archived_request, archived_response).open(bad_url, timeout=1),
        "route differs",
    )
    bad_body = urllib.request.Request(url, data=b"{}", method="POST")
    expect_rejection(
        lambda: HistoricalOpener(url, archived_request, archived_response).open(
            bad_body, timeout=1
        ),
        "serialized bytes differ",
    )
    corrupt = OUT / "historical-copy-bad-response"
    shutil.copytree(history, corrupt)
    bad_file = corrupt / "attempt-00/response.raw"
    payload = bad_file.read_bytes()
    bad_file.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    corrupted = verify_role_probe_evidence(corrupt)
    scope.require(
        not corrupted["available"]
        and any("wire payload hash drift" in e for e in corrupted["errors"]),
        "corrupted archive was not rejected by independent consumption",
    )
    scope.require(
        not (scope.ROOT / scope.PLAN["current_nominal_real_output"]).exists(),
        "registered paid probe is outside this offline execution",
    )
    scope.write_once(
        OUT / "wire-replay-receipt.json",
        {
            "scope": "HISTORICAL_WIRE_REPLAY",
            "plan_sha256": scope.sha(scope.PLAN_PATH),
            "execution_program_sha256": scope.sha(Path(__file__)),
            "send_fence_sha256": scope.sha(Path(scope.__file__)),
            "historical_role_gate": "REJECTED_CURRENT_SOURCE",
            "negative_controls": [
                "fifth_send",
                "duplicate_index",
                "restart_after_completion",
                "restart_after_reservation",
                "wrong_route",
                "wrong_payload",
                "archive_response_mutation",
            ],
            "fixture_ledger_rows": len(calls),
            "fixture_open_calls": sum(x["fixture_open_calls"] for x in calls),
            "verified_wire": calls,
            "real_http_sends": 0,
            "new_rgbd_exposures": 0,
            "nominal_paid_batch_started": False,
            "current_cloud_role_accepted": False,
            "actual_b0": 0,
            "formal_g2": 0,
            "formal_independent": 0,
            "hardware": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    os.umask(0o077)
    with patch.multiple(socket.socket, connect=deny, connect_ex=deny):
        replay()
