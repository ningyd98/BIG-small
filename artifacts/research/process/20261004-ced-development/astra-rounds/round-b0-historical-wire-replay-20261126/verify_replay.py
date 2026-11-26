"""Independently audit replay bytes and fixture slots, without any adapter."""

import json

import probe_scope as scope

OUT = scope.ROOT / scope.PLAN["replay_output"]


def audit():
    history, original = scope.preflight_inputs()
    evidence = json.loads((OUT / "wire-replay-receipt.json").read_bytes())
    scope.require(
        evidence["scope"] == "HISTORICAL_WIRE_REPLAY"
        and evidence["fixture_open_calls"] == evidence["fixture_ledger_rows"] == scope.MAX_SENDS
        and evidence["real_http_sends"] == evidence["new_rgbd_exposures"] == 0
        and not evidence["nominal_paid_batch_started"]
        and not evidence["current_cloud_role_accepted"]
        and not (scope.ROOT / scope.PLAN["current_nominal_real_output"]).exists(),
        "fixture evidence was promoted or evidence counts changed",
    )
    attempts = OUT / "fixture-wire"
    slots = OUT / "fixture-slots"
    all_stored = {}
    for row, old in zip(evidence["verified_wire"], original["attempts"], strict=True):
        index = row["index"]
        scope.require(index == old["index"], "historical attempt order changed")
        directory = f"attempt-{index:02d}"
        fresh, source = attempts / directory, history / directory
        for kind, label in [("request", "sent"), ("response", "received")]:
            filename = kind + ".raw"
            current, archived = fresh / filename, source / filename
            digest = scope.sha(current)
            scope.require(
                digest == scope.sha(archived) == row[f"raw_{kind}_sha256"],
                "different historical raw wire",
            )
            scope.require(
                current.stat().st_size == old[f"serialized_{label}_bytes"],
                "historical byte count changed",
            )
            all_stored[f"{directory}/{filename}"] = digest
        saved_attempt = json.loads((fresh / "attempt.json").read_bytes())
        reserved = json.loads((slots / f"send-{index:02d}.json").read_bytes())
        scope.require(
            reserved["attempt_index"] == index
            and reserved["request_sha256"] == row["raw_request_sha256"]
            and saved_attempt["parsed_json"] == old["parsed_json"]
            and saved_attempt["target_offline_check"] == old["target_offline_check"]
            and saved_attempt["destination_offline_check"] == old["destination_offline_check"]
            and saved_attempt["transport_two_images"] is True,
            "reserved slot to archived bytes, parsed output or grounding linkage differs",
        )
    scope.require(
        len(list(slots.glob("send-*.json"))) == scope.MAX_SENDS, "fixture has unregistered sends"
    )
    scope.write_once(
        OUT / "independent-readback.json",
        {
            "schema": "b0.historical-wire-replay.cold.v1",
            "receipt_sha256": scope.sha(OUT / "wire-replay-receipt.json"),
            "verified_replayed_raw_sha256": all_stored,
            "frozen_current_role_remains_unavailable": True,
            "zero": ["new_http_sends", "paid_role_evidence", "actual_b0", "formal_g2"],
        },
    )


if __name__ == "__main__":
    audit()
