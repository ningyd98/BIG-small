const R="/home/ningyd/文档/ChatGPT/BIGsmall", D=R+"/artifacts/research/process/20261004-ced-development/astra-rounds/round258-p6-t2-parent-green7-continuation-20261017";
const original=load("r258_original_runner_construction_read_actual").actual.output;
if(new TextEncoder().encode(original).length!==31818 || original.includes("Warning: truncated")) throw Error("construction source not exact complete31818");
const begin=original.indexOf("def _t2_pin("), end=original.indexOf("def main()");
if(begin<0||end<=begin) throw Error("frozen text boundaries");
const block=original.slice(begin,end);
store("r258_copied_block",block);store("r258_construction_original_source",original);
const header=`"""R258: one original R158 t2_green allowance; source-only until ROOT release."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D = ROUNDS / "round258-p6-t2-parent-green7-continuation-20261017"
PARENT = ROUNDS / "round158-p6-stage-b-local-temporal-publication-20261013"
PLAN_SHA = "50970ee4e58d28f7732686ff11befd01f1d56a3657a200d97dba9b45ffa764e7"
OBS_SHA = "8213421ccb98f9bdc8370d909cda26a7366cc44c9f4fe12a9d463c5f5e2899d9"
ORIGINAL_PLAN_SHA = "70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b"
COMMAND = "t2_green"
CASE_NAMES = {
    "after-both-lock-denial.json", "true-commit-loss.json",
    "restart-no-authority.json", "same-owner-exact-history.json",
    "one-CAS-no-refund.json", "complete-writer-inventory.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(record):
    require(type(record) is dict, "pin must be an object")
    result = {key: record[key] for key in ("path", "bytes", "sha256")}
    require(type(result["path"]) is str and Path(result["path"]).is_absolute(),
            "absolute identity path required")
    require(type(result["bytes"]) is int and result["bytes"] >= 0,
            "nonnegative exact integer bytes required")
    require(type(result["sha256"]) is str and len(result["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in result["sha256"]),
            "exact SHA256 required")
    return result


def key(record):
    value = identity(record)
    return (value["path"], value["bytes"], value["sha256"])


def raw_pin(path, raw):
    return {"path": str(path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def stable_bytes(path):
    path = Path(path)
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode) and not path.is_symlink(),
            "regular nonsymlink file required: " + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        require((first.st_dev, first.st_ino, first.st_mode, first.st_size)
                == (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size),
                "lstat/open identity changed: " + str(path))
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read()
        closed = os.fstat(descriptor)
        last = path.lstat()
        coordinates = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size,
                                  s.st_mtime_ns, s.st_ctime_ns)
        require(coordinates(opened) == coordinates(closed) == coordinates(last)
                and len(raw) == last.st_size, "file changed while reading: " + str(path))
        return raw
    finally:
        os.close(descriptor)


def sha(path):
    return hashlib.sha256(stable_bytes(path)).hexdigest()


def checked(record):
    pin = identity(record)
    raw = stable_bytes(Path(pin["path"]))
    require(raw_pin(pin["path"], raw) == pin, "exact pin changed: " + pin["path"])
    return raw


def decode_json(raw):
    value = json.loads(raw.decode("utf-8"))
    require(type(value) is dict, "JSON object required")
    return value


def read_json(path):
    return decode_json(stable_bytes(path))


def write_bytes(path, raw, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        require(handle.write(raw) == len(raw), "partial evidence write")
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        os.chmod(path, stat.S_IMODE(mode))
    require(stable_bytes(path) == raw, "exclusive evidence readback differs")
    return raw_pin(path, raw)


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\\n").encode()
    return write_bytes(path, raw)


def absent(path):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(),
            "required absence changed: " + str(path))
    return {"path": str(path), "exists": False, "is_symlink": False,
            "bytes": None, "sha256": None, "hash_match": None}


def json_pointer(value, pointer):
    require(type(pointer) is str and pointer.startswith("/")
            and len(pointer) < 512, "finite explicit JSON pointer required")
    parts = pointer.split("/")[1:]
    require(len(parts) <= 16, "explicit JSON pointer exceeds bound")
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if type(value) is dict:
            require(part in value, "explicit pointer key absent")
            value = value[part]
        else:
            require(type(value) is list and part.isdecimal(), "explicit list pointer required")
            index = int(part)
            require(index < len(value), "explicit pointer index out of range")
            value = value[index]
    return value


`;
store("r258_source_header",header);text({old_bytes:31818,copied_block_lines:block.split("\n").length-1,header_lines:header.split("\n").length-1,source_written:false});
