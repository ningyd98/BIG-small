"""Molmo 原生单 RGB 定位；严格解析与有界本地推理，不生成控制动作。"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import signal
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol

from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation

MODEL_ID = "allenai/Molmo2-ER"
ASSET_MANIFEST_SHA256 = "ff0563c87a9bd42a90df49db81dc14ee00d88894ad662f2b43c1942475076464"
_POINT = re.compile(
    r'<points coords="1[ \t]+([0-9]{1,6})[ \t]+([0-9]{1,4})[ \t]+([0-9]{1,4})">'
    r"([^<>\x00-\x1f]{1,500})</points>"
)
_ABSENCE_ALIASES = frozenset({"There are none."})
_CONTRADICTION = re.compile(
    r"\b(absent|not\s+visible|no\s+points|there\s+are\s+none)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class NativePointResult:
    """模型原始结果；不把检出状态包装成概率或置信度。"""

    status: Literal["POINT", "ABSENT", "INVALID"]
    normalized_1000: tuple[int, int] | None
    object_index: int | None
    raw_text: str
    error: str | None = None


@dataclass(frozen=True)
class BoundPointResult:
    """将定位结果绑定到唯一观测、RGB 字节和查询短语。"""

    result: NativePointResult
    observation_checksum: str
    rgb_sha256: str
    query_sha256: str
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


class PointProvider(Protocol):
    """识别定位接口；实现不得从评测标签选择目标点。"""

    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult:
        """使用给定 RGB 及明确任务短语返回绑定结果。"""
        ...


def parse_native_point(raw: str) -> NativePointResult:
    """只接受单个规范点、ABSENT或已验证完整缺失句；歧义和截断均拒绝。"""
    invalid = NativePointResult("INVALID", None, None, raw, "invalid native point grammar")
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 16384:
        return invalid
    text = raw.strip()
    for terminal in ("<|im_end|>", "<|endoftext|>"):
        if text.endswith(terminal):
            text = text[: -len(terminal)].strip()
            break
    if text == "ABSENT" or text in _ABSENCE_ALIASES:
        return NativePointResult("ABSENT", None, None, raw)
    match = _POINT.fullmatch(text)
    if match is None or _CONTRADICTION.search(match[4]):
        return invalid
    object_index, x, y = map(int, match.group(1, 2, 3))
    if object_index < 1 or x > 1000 or y > 1000:
        return invalid
    return NativePointResult("POINT", (x, y), object_index, raw)


def native_prompt(phrase: str) -> str:
    """保持已验证的原生定位提示，任务短语与模型输出分开记录。"""
    if not isinstance(phrase, str) or not phrase.strip() or len(phrase) > 240:
        raise ValueError("invalid native query phrase")
    if any(ord(c) < 32 or c in "<>" for c in phrase):
        raise ValueError("invalid native query phrase")
    return (
        f"Point to the {phrase}. If the requested item is not visible, "
        "return exactly ABSENT and no points."
    )


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def _verify_assets(directory: Path, manifest_path: Path) -> None:
    if _sha(manifest_path) != ASSET_MANIFEST_SHA256:
        raise ValueError("unregistered Molmo asset manifest")
    manifest = json.loads(manifest_path.read_text())
    rows = manifest.get("files", [])
    if manifest.get("repo") != MODEL_ID or len(rows) != 26:
        raise ValueError("invalid Molmo asset inventory")
    root = directory.resolve(strict=True)
    seen: set[str] = set()
    for row in rows:
        relative = row["Path"]
        path = (root / relative).resolve(strict=True)
        if relative in seen or not path.is_relative_to(root) or not path.is_file():
            raise ValueError("invalid Molmo asset path")
        seen.add(relative)
        if path.stat().st_size != row["Size"] or _sha(path) != row["Sha256"]:
            raise ValueError("Molmo local asset hash mismatch")


@contextmanager
def _deadline(seconds: int) -> Iterator[None]:
    # CUDA 调用不能在任意 HTTP 线程内安全中止；原生生命周期由专用进程主线程持有。
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("native inference requires a dedicated process main thread")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer != (0.0, 0.0):
        raise RuntimeError("native inference cannot replace an existing deadline")

    def expired(signum: int, frame: object) -> None:
        raise TimeoutError("Molmo native operation deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


class MolmoPointProvider:
    """一次加载的 BF16 provider；专用进程主线程执行，原始证据仅写本地。"""

    def __init__(
        self,
        *,
        model_directory: Path,
        asset_manifest: Path,
        raw_directory: Path,
        generation_limit: int = 8,
    ) -> None:
        if type(generation_limit) is not int or not 1 <= generation_limit <= 8:
            raise ValueError("generation budget must be 1..8")
        _verify_assets(Path(model_directory), Path(asset_manifest))
        self.raw_directory = Path(raw_directory)
        self.raw_directory.mkdir(parents=True, exist_ok=False)
        self.generation_limit = generation_limit
        self.model_loads_started = 0
        self.generation_calls_started = 0
        self.generation_calls_completed = 0
        self._attempts = 0
        self._lock = threading.Lock()
        _write(
            self.raw_directory / "initial.json",
            {
                "model": MODEL_ID,
                "precision": "BF16",
                "generation_limit": generation_limit,
                "asset_manifest_sha256": _sha(Path(asset_manifest)),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        try:
            import torch
            import transformers
            from transformers import AutoModelForImageTextToText, AutoProcessor

            if torch.__version__ != "2.6.0+cu124" or transformers.__version__ != "4.57.1":
                raise RuntimeError("native runtime differs from validated Molmo versions")
            if not torch.cuda.is_available():
                raise RuntimeError("native Molmo requires CUDA")
            self._torch = torch
            torch.manual_seed(0)
            with _deadline(1800):
                self._processor = AutoProcessor.from_pretrained(
                    str(model_directory),
                    trust_remote_code=True,
                    local_files_only=True,
                    use_fast=False,
                    padding_side="left",
                )
                self.model_loads_started += 1
                _write(self.raw_directory / "load-started.json", {"model_loads_started": 1})
                started = time.perf_counter()
                self._model = AutoModelForImageTextToText.from_pretrained(
                    str(model_directory),
                    trust_remote_code=True,
                    local_files_only=True,
                    dtype=torch.bfloat16,
                    attn_implementation="sdpa",
                    device_map={"": 0},
                ).eval()
                torch.cuda.synchronize()
                if not all(
                    p.device.type == "cuda" and p.dtype == torch.bfloat16
                    for p in self._model.parameters()
                ):
                    raise RuntimeError("native model must be entirely CUDA BF16")
            self.runtime = {"torch": torch.__version__, "transformers": transformers.__version__}
            _write(
                self.raw_directory / "loaded.json",
                {
                    "model_loads_started": self.model_loads_started,
                    "load_s": time.perf_counter() - started,
                    "runtime": self.runtime,
                },
            )
        except BaseException as exc:
            _write(
                self.raw_directory / "load-failure.json",
                {
                    "error_type": type(exc).__name__,
                    "model_loads_started": self.model_loads_started,
                },
            )
            raise

    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult:
        """一次单 RGB 查询；失败生成占用预算，达到上限后不再调用模型。"""
        prompt = native_prompt(phrase)
        with self._lock:
            if self.generation_calls_started >= self.generation_limit:
                raise RuntimeError("native generation budget exhausted")
            self._attempts += 1
            folder = self.raw_directory / f"request-{self._attempts:04}"
            folder.mkdir(exist_ok=False)
            started = time.perf_counter()
            query_sha = hashlib.sha256(phrase.encode()).hexdigest()
            rgb = base64.b64decode(observation.rgb_png_base64, validate=True)
            rgb_sha = hashlib.sha256(rgb).hexdigest()
            binding = {
                "observation_checksum": observation.checksum_sha256,
                "rgb_sha256": rgb_sha,
                "query_sha256": query_sha,
            }
            _write(
                folder / "started.json",
                binding | {"phrase": phrase, "started_at": datetime.now(UTC).isoformat()},
            )
            try:
                with _deadline(900), Image.open(io.BytesIO(rgb)) as source:
                    image = source.convert("RGB")
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image", "image": image},
                            ],
                        }
                    ]
                    processor, torch = self._processor, self._torch
                    rendered = processor.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                    features = processor.apply_chat_template(
                        messages,
                        tokenize=True,
                        add_generation_prompt=True,
                        return_tensors="pt",
                        return_dict=True,
                        padding=True,
                    )
                    with (folder / "prompt.txt").open("x") as stream:
                        stream.write(rendered)
                    tensors = {}
                    for key, value in features.items():
                        if isinstance(value, torch.Tensor):
                            tensor = value.detach().cpu().contiguous()
                            tensors[key] = {
                                "shape": list(tensor.shape),
                                "dtype": str(tensor.dtype),
                                "sha256": hashlib.sha256(
                                    tensor.view(torch.uint8).numpy().tobytes()
                                ).hexdigest(),
                            }
                    _write(folder / "processor.json", tensors)
                    input_tokens = features["input_ids"].shape[1]
                    _write(folder / "input-token-ids.json", features["input_ids"][0].tolist())
                    features = {k: v.to("cuda:0") for k, v in features.items()}
                    self.generation_calls_started += 1
                    _write(
                        folder / "generation-started.json",
                        {"generation_calls_started": self.generation_calls_started},
                    )
                    torch.cuda.synchronize()
                    generation_started = time.perf_counter()
                    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                        output = self._model.generate(
                            **features,
                            max_new_tokens=512,
                            do_sample=False,
                            num_beams=1,
                            use_cache=True,
                        )
                    torch.cuda.synchronize()
                    generation_s = time.perf_counter() - generation_started
                    self.generation_calls_completed += 1
                    ids = output[0, input_tokens:].tolist()
                    _write(folder / "output-token-ids.json", ids)
                    _write(
                        folder / "generation-completed.json",
                        {
                            "generation_calls_completed": self.generation_calls_completed,
                            "generation_s": generation_s,
                            "output_tokens": len(ids),
                        },
                    )
                    raw = processor.tokenizer.decode(
                        ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
                    )
                    with (folder / "raw-response.txt").open("x") as stream:
                        stream.write(raw)
                    result = parse_native_point(raw)
                    reached_cap = len(ids) >= 512
                    if reached_cap:
                        result = NativePointResult("INVALID", None, None, raw, "output token cap")
                    evidence: dict[str, object] = {
                        "model": MODEL_ID,
                        "precision": "BF16",
                        "model_image_count": 1,
                        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "raw_directory": str(folder),
                        "input_tokens": input_tokens,
                        "output_tokens": len(ids),
                        "reached_cap": reached_cap,
                        "generation_s": generation_s,
                        "end_to_end_s": time.perf_counter() - started,
                        "generation_calls_started": self.generation_calls_started,
                        "generation_calls_completed": self.generation_calls_completed,
                    }
                    _write(folder / "result.json", binding | evidence | {"native": asdict(result)})
                    return BoundPointResult(
                        result, observation.checksum_sha256, rgb_sha, query_sha, evidence
                    )
            except BaseException as exc:
                _write(
                    folder / "failure.json",
                    binding
                    | {
                        "error_type": type(exc).__name__,
                        "end_to_end_s": time.perf_counter() - started,
                        "generation_calls_started": self.generation_calls_started,
                        "generation_calls_completed": self.generation_calls_completed,
                    },
                )
                raise
