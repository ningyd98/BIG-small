"""固定新 seed 的真实模型批次；只调用原 CLI，不修改运行时或重试病例。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path: Path) -> dict | list:
    """读取明确的本地 JSON。"""
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    """按实际文件字节核对来源。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    """原子写本轮进度；新目录及原始用例由原入口独占创建。"""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def profile_sha() -> str:
    """只读绑定既有配置，不读取或输出明文凭据。"""
    preflight = read(HERE / "preflight.json")
    database = Path("/home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT payload_json FROM model_provider_profiles WHERE profile_id = ?",
            (preflight["profile_id"],),
        ).fetchone()
    if row is None:
        raise ValueError("selected cloud profile unavailable")
    profile = json.loads(row[0])
    assert profile["base_url"] == "https://api.openai.com"
    assert profile["chat_completions_path"] == "/v1/chat/completions"
    assert profile["model_name"] == "gpt-6.1-sol" and profile["enabled"] is True
    return hashlib.sha256(row[0].encode()).hexdigest()


def prepare() -> None:
    """在任何新场景或付费请求前冻结来源、顺序和配置。"""
    protocol = read(HERE / "protocol.json")
    matrix = read(HERE / "matrix.json")
    history = read(HERE / "evidence/history-audit.json")
    assert protocol["count"] == protocol["cloud_requests_max"] == 15
    assert protocol["seeds"] == history["candidate_seeds"] == list(range(45001, 45016))
    assert history["matched_files"] == []
    assert matrix == [
        {"seed": seed, "split": "held-out", "cloud_vision_fallback": True}
        for seed in protocol["seeds"]
    ]
    paths = subprocess.check_output(
        ["git", "ls-files", "--", "src", "scripts", "configs", "assets", "pyproject.toml"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    paths += [str(p.relative_to(ROOT)) for p in HERE.glob("*.py")]
    paths += [
        str((HERE / p).relative_to(ROOT))
        for p in (
            "protocol.json",
            "matrix.json",
            "preflight.json",
            "plan.md",
            "evidence/history-audit.json",
        )
    ]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert commit == protocol["source_commit"]
    frozen = {
        "scope": "APPLICATION_SOURCE_AND_EXPERIMENT_PROTOCOL_FREEZE",
        "source_commit": commit,
        "profile_sha256": profile_sha(),
        "created_at": datetime.now(UTC).isoformat(),
        "files": {path: sha(ROOT / path) for path in sorted(set(paths))},
    }
    destination = HERE / "source-freeze.json"
    with destination.open("x") as stream:
        json.dump(frozen, stream, indent=2)
        stream.write("\n")
    check()
    print(json.dumps({"frozen_files": len(frozen["files"]), "paid_requests": 0}))


def check() -> None:
    """任何来源或已选择云配置漂移均在下一次请求前拒绝。"""
    frozen = read(HERE / "source-freeze.json")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert commit == frozen["source_commit"], "application commit drift"
    assert profile_sha() == frozen["profile_sha256"], "selected cloud profile drift"
    for name, expected in frozen["files"].items():
        assert sha(ROOT / name) == expected, "source/protocol drift: " + name


def command(seed: int, output: Path) -> list[str]:
    """使用当前工作树原 CLI、既有原生依赖及原加密凭据通道。"""
    preflight = read(HERE / "preflight.json")
    paths = preflight["local_paths"]
    return [
        paths["python"],
        "-u",
        "-B",
        str(ROOT / "scripts/run_sol_molmo_single_episode.py"),
        "--seed",
        str(seed),
        "--output",
        str(output),
        "--marker-family",
        "side_y_plus_id7_75mm_component_v1",
        "--execute",
        "--component-diagnostic",
        "--cloud-vision-fallback",
        "--scene-split",
        "held-out",
        "--profile-id",
        preflight["profile_id"],
        "--model-control-db",
        "/home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db",
        "--model-directory",
        paths["model"],
        "--asset-manifest",
        paths["asset_manifest"],
        "--gpu-lock",
        paths["gpu_lock"],
        "--application-site-packages",
        paths["application_site_packages"],
        "--allow-paid",
    ]


def stop(child: subprocess.Popen) -> None:
    """只终止本控制器新建的进程组并保留部分证据。"""
    os.killpg(child.pid, signal.SIGINT)
    try:
        child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()


def run() -> None:
    """顺序执行全部预声明病例；预算耗尽或来源漂移时留存未完成分母。"""
    check()
    protocol = read(HERE / "protocol.json")
    output = HERE / "raw-local/run-01"
    output.mkdir(exist_ok=False)
    (output / "logs").mkdir()
    write(
        output / "run-metadata.json",
        {
            "source_commit": protocol["source_commit"],
            "source_freeze_sha256": sha(HERE / "source-freeze.json"),
            "protocol_sha256": sha(HERE / "protocol.json"),
            "started_at": datetime.now(UTC).isoformat(),
            "hardware_dispatch": False,
            "formal_research": "NOT_ACCEPTED",
            "raw_delivery": "LOCAL_ONLY",
        },
    )
    environment = os.environ | {
        "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "MUJOCO_GL": "egl",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    started = time.monotonic()
    rows = []
    child = None
    try:
        for seed in protocol["seeds"]:
            check()
            remaining = protocol["batch_cap_s"] - (time.monotonic() - started)
            if remaining <= 0:
                break
            episode = output / f"held-out-{seed:06d}"
            assert not episode.exists(), "no overwrite/retry"
            print(f"START seed={seed}", flush=True)
            scene_start = time.monotonic()
            timed_out = False
            with (output / "logs" / f"{seed}.log").open("xb") as log:
                child = subprocess.Popen(
                    command(seed, episode),
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                write(
                    output / "progress.json",
                    {
                        "status": "RUNNING",
                        "denominator": 15,
                        "completed": len(rows),
                        "active_seed": seed,
                        "active_pid": child.pid,
                        "episodes": rows,
                    },
                )
                try:
                    code = child.wait(timeout=min(protocol["case_process_cap_s"], remaining))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    stop(child)
                    code = child.returncode
            child = None
            result_path = episode / "result.json"
            result = read(result_path) if result_path.is_file() else {}
            fields = (
                "status",
                "component_success",
                "physical_success",
                "error_type",
                "executed_actions",
                "physics_steps",
                "model_loads",
                "local_generations",
                "local_generations_completed",
                "cloud_requests",
                "cloud_request_reservations",
                "marker_endpoints_observed",
                "changed_source_paths",
            )
            row = {
                "seed": seed,
                **{k: result.get(k) for k in fields},
                "terminal_reason": result.get("outcome", {}).get("terminal_reason")
                or result.get("terminal_reason"),
                "child_returncode": code,
                "timed_out": timed_out,
                "elapsed_s": time.monotonic() - scene_start,
                "result_path": str(result_path.relative_to(output)),
            }
            rows.append(row)
            requests = sum(
                int((output / f"held-out-{r['seed']:06d}/raw/cloud/request.json").is_file())
                for r in rows
            )
            assert requests <= protocol["cloud_requests_max"], "cloud budget violation"
            assert not result.get("changed_source_paths"), "episode source drift"
            check()
            write(
                output / "progress.json",
                {
                    "status": "RUNNING",
                    "denominator": 15,
                    "completed": len(rows),
                    "active_seed": None,
                    "episodes": rows,
                },
            )
            print("DONE " + json.dumps(row), flush=True)
        report = {
            "status": "COMPLETED" if len(rows) == 15 else "CAP_LIMITED",
            "completed": len(rows),
            "denominator": 15,
            "not_run": 15 - len(rows),
            "wall_s": time.monotonic() - started,
            "episodes": rows,
        }
        write(output / "batch-result.json", report)
        write(output / "progress.json", report)
        print(
            "BATCH_FINISHED " + json.dumps({"completed": len(rows), "denominator": 15}), flush=True
        )
    except BaseException:
        if child is not None and child.poll() is None:
            stop(child)
        write(
            output / "interrupted.json",
            {
                "status": "INTERRUPTED",
                "episodes": rows,
                "denominator": 15,
                "not_completed": 15 - len(rows),
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "check": check, "run": run}[args.mode]()
