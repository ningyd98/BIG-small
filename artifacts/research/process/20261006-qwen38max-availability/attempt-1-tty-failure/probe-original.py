"""One catalog request and at most one text completion; credential stays in memory."""
from __future__ import annotations

import argparse
import ast
import getpass
import hashlib
import json
import re
import socket
import sys
import termios
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

PLAN = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/qwen38max-availability-20261006/plan.json"
BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.8-max"
BODY = {"model": MODEL, "messages": [{"role": "user", "content": "Return exactly OK."}],
        "max_tokens": 16, "enable_thinking": False, "temperature": 0, "stream": False}
POLICY = {"mode": "direct", "interface": "enp7s0",
          "allowed_hosts": ["token-plan.cn-beijing.maas.aliyuncs.com"],
          "dns_servers": ["223.5.5.5", "223.6.6.6"], "host_addresses": {}, "dns_timeout_seconds": 3}


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, data):
    with (HERE / name).open("xb") as f:
        f.write(data)


def save_json(name, data):
    save(name, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def check_inputs():
    plan = json.loads(PLAN.read_text())
    manifest = json.loads((HERE / "input-sha256.json").read_text())
    for path, expected in manifest.items():
        if sha((ROOT / path).read_bytes()) != expected:
            raise ValueError("input hash mismatch: " + path)
    for path, expected in plan["inputs_sha256"].items():
        source = Path(path) if Path(path).is_absolute() else ROOT / path
        if sha(source.read_bytes()) != expected:
            raise ValueError("plan input hash mismatch: " + path)
    if plan["requests"][1]["body"] != BODY:
        raise ValueError("request differs from approved plan")
    return {"manifest_entries": len(manifest), "plan_entries": len(plan["inputs_sha256"]),
            "mismatches": [], "plan_sha256": sha(PLAN.read_bytes())}


def read_key():
    with open("/dev/tty", "r+") as terminal:
        settings = termios.tcgetattr(terminal.fileno())
        hidden = settings.copy()
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(terminal.fileno(), termios.TCSADRAIN, hidden)
        try:
            if termios.tcgetattr(terminal.fileno())[3] & termios.ECHO:
                raise RuntimeError("hidden credential input unavailable")
            key = getpass.getpass("API key (echo disabled; memory only): ")
        finally:
            termios.tcsetattr(terminal.fileno(), termios.TCSADRAIN, settings)
    if not key or "\n" in key or "\r" in key:
        raise ValueError("invalid credential input")
    return key


def run():
    reviewed = check_inputs()
    if (HERE / "result.json").exists() or (HERE / "run-start.json").exists():
        raise FileExistsError("one run only; do not overwrite or retry")
    key = read_key()
    secret_pattern = re.compile(r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_.-]{16,}")
    def safe(text):
        return secret_pattern.sub("[REDACTED]", str(text).replace(key, "[REDACTED]"))
    save_json("run-start.json", {"started_at": now(), "input_review": reviewed,
              "credential_source": "user_provided_hidden_tty_input", "credential_persisted": False,
              "credential_input_echo_disabled_verified": True, "network_policy": POLICY,
              "trust_env": False, "follow_redirects": False, "verify_tls": True,
              "provider_concurrency_max": 1, "http_retries": 0, "max_api_calls": 2})
    records = []
    calls = 0
    body_bytes = json.dumps(BODY, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    client = None
    def call(method, path, label, content=None):
        nonlocal calls
        if calls >= 2:
            raise RuntimeError("request budget exceeded")
        calls += 1
        receipt = {"sequence": calls, "method": method, "endpoint": BASE + path,
                   "started_at": now(), "request_body_sha256": sha(content) if content is not None else None}
        started = time.perf_counter()
        try:
            with client.stream(method, BASE + path, content=content,
                               headers={"Content-Type": "application/json"} if content is not None else {}) as response:
                receipt["http_status"] = response.status_code
                stream = response.extensions.get("network_stream")
                sock = stream.get_extra_info("socket") if stream else None
                if sock is None:
                    raise RuntimeError("socket observation unavailable")
                receipt["network"] = {"bound_interface": sock.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256).rstrip(b"\0").decode(),
                                      "peer": sock.getpeername(), "local": sock.getsockname()}
                if receipt["network"]["bound_interface"] != POLICY["interface"]:
                    raise RuntimeError("physical-interface observation mismatch")
                receipt["headers"] = {k: v for k, v in response.headers.items()
                    if k.lower() in {"x-request-id", "request-id", "content-type", "date"}}
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2_000_000:
                        raise RuntimeError("response size limit exceeded")
            raw = bytes(raw)
            decoded_text = raw.decode("utf-8")
            receipt["response_body_sha256"] = sha(raw)
            receipt["response_body_bytes"] = len(raw)
            if key in decoded_text or secret_pattern.search(decoded_text):
                receipt["evidence_withheld_sensitive"] = True
                receipt["ok"] = False
                return receipt, None
            save(label + "-response.body", raw)
            receipt["response_file"] = label + "-response.body"
            decoded = json.loads(decoded_text)
            if not isinstance(decoded, dict):
                raise ValueError("response JSON is not an object")
            receipt["ok"] = response.status_code == 200
            if isinstance(decoded.get("error"), dict):
                receipt["api_error"] = {k: safe(v) for k, v in decoded["error"].items() if k in {"code", "type", "message"}}
            return receipt, decoded
        except Exception as exc:
            receipt["ok"] = False
            receipt["error"] = {"type": type(exc).__name__, "message": safe(str(exc))[:500]}
            return receipt, None
        finally:
            receipt["ended_at"] = now()
            receipt["total_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
            records.append(receipt)
            save_json(label + "-receipt.json", receipt)
            print(json.dumps({"request": label, "http_status": receipt.get("http_status"),
                              "ok": receipt.get("ok"), "total_wall_ms": receipt["total_wall_ms"],
                              "error": receipt.get("api_error", receipt.get("error"))}, ensure_ascii=False), flush=True)
    result = {"model_requested": MODEL, "endpoint": BASE, "created_at": now(),
              "availability_confirmed": False, "formal_research_acceptance": "NOT_TESTED",
              "visual_input_tested": False, "hardware_calls": 0, "automatic_retries": 0}
    try:
        client = httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                  follow_redirects=False, verify=True,
                  timeout=httpx.Timeout(connect=15, read=60, write=15, pool=15),
                  headers={"Authorization": "Bearer " + key})
        catalog_receipt, catalog = call("GET", "/models", "models")
        result["catalog_http_status"] = catalog_receipt.get("http_status")
        if catalog_receipt.get("ok") and catalog is not None:
            result["model_listed"] = any(isinstance(m, dict) and m.get("id") == MODEL for m in catalog.get("data", []))
            save("request.json", body_bytes)
            chat_receipt, chat = call("POST", "/chat/completions", "chat", body_bytes)
            result["chat_http_status"] = chat_receipt.get("http_status")
            result["latency_ms"] = chat_receipt["total_wall_ms"]
            if chat is not None:
                choices = chat.get("choices")
                choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                text = message.get("content")
                result.update({"model_returned": chat.get("model"), "finish_reason": choice.get("finish_reason"),
                               "content": text, "usage": chat.get("usage"), "prompt_following": isinstance(text, str) and text.strip() == "OK"})
                result["availability_confirmed"] = bool(chat_receipt.get("ok") and chat.get("model") == MODEL
                    and isinstance(text, str) and text.strip() and choice.get("finish_reason") == "stop")
            result["status"] = "AVAILABLE_SINGLE_TEXT_PROBE" if result["availability_confirmed"] else "TEXT_INFERENCE_NOT_CONFIRMED"
        else:
            result["status"] = "CATALOG_FAILED_POST_SKIPPED"
            result["post_skipped"] = True
    except Exception as exc:
        result["status"] = "PREFLIGHT_OR_TRANSPORT_FAILED"
        result["error"] = {"type": type(exc).__name__, "message": safe(str(exc))[:500]}
    finally:
        if client is not None:
            client.close()
        result["api_calls"] = calls
        result["receipts"] = records
        result["ended_at"] = now()
        save_json("result.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["availability_confirmed"] else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    if args.offline_check:
        review = check_inputs()
        ast.parse(Path(__file__).read_text())
        transport = create_direct_transport(POLICY)
        transport.close()
        record = {"status": "PASS", "checked_at": now(), "ast_valid": True,
                  "imports_valid": True, "input_review": review, "request": BODY,
                  "network_policy": POLICY, "network_calls": 0,
                  "probe_sha256": sha(Path(__file__).read_bytes())}
        save_json("offline-check.json", record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
