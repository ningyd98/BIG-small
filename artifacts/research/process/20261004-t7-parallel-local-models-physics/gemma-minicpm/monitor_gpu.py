"""Read-only exclusive-run monitor; records foreign models and CUDA processes."""
import argparse
import csv
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--ollama-model")
parser.add_argument("--native-pid", type=int)
args = parser.parse_args()
if args.output.exists():
    raise FileExistsError("monitor evidence already exists")
running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
args.output.with_suffix(".pid").write_text(str(os.getpid()) + "\n")
with args.output.open("x") as stream, httpx.Client(trust_env=False, timeout=5) as client:
    while running:
        row = {"timestamp":datetime.now(UTC).isoformat()}
        try:
            models = client.get("http://127.0.0.1:11434/api/ps").json()["models"]
            row["ollama_models"] = models
            row["foreign_model_names"] = [m["name"] for m in models if m["name"] != args.ollama_model]
            gpu = subprocess.check_output(["nvidia-smi","--query-gpu=memory.used,memory.total,utilization.gpu","--format=csv,noheader,nounits"], text=True, timeout=5)
            used,total,util = next(csv.reader(gpu.splitlines()))
            row.update(gpu_memory_used_mib=int(used), gpu_memory_total_mib=int(total), gpu_utilization_percent=int(util))
            apps = subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,process_name,used_memory","--format=csv,noheader,nounits"], text=True, timeout=5)
            row["cuda_processes"] = [{"pid":int(pid),"name":name.strip(),"memory_mib":int(mem)} for pid,name,mem in csv.reader(apps.splitlines())]
            row["foreign_cuda_processes"] = [p for p in row["cuda_processes"] if (args.native_pid is not None and p["pid"] != args.native_pid) or (args.native_pid is None and "llama-server" not in p["name"])]
        except Exception as exc:
            row["monitor_error"] = repr(exc)
        stream.write(json.dumps(row) + "\n")
        stream.flush()
        time.sleep(1)
