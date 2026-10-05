"""Research snapshots for pinned MuJoCo getters; no execution or admission authority.

MuJoCo 3.3.7 structs.cc:763-770 constructs solver/dual/island arrays on
each getter access. structs.h:940-949 forwards positive-size null pointers.
The default pybind11 v3.0.1 numpy.h:963-1010 then allocates owning storage,
without attaching the MjData owner. Such bytes are not live arena state.

Callers supply already verified header bytes/version/binding pins and all
original protected components. This module neither attests the caller nor
imports MuJoCo. It never steps, forwards, resets, copies or renders a model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

VERSION = "3.3.7"
MJXMACRO_SHA256 = "4caf3956c70651c08f9d83bb6ef967c1b4bbfd207ee24e9aef24620622aa497f"
MJDATA_SHA256 = "f05eb63f68c10c67558c99ed703135d886060ee3bf1fecbd4a69d7e6d0e7e015"
BINDING_SHA256 = "8fd6c4e9e92676f4175cde18bebb3d354d3e85aac6971cb194f66be20ff9ecc8"
_FAMILIES = ("SOLVER", "DUAL", "ISLAND")
_PROTECTED_KEYS = frozenset(
    (
        "model_arrays_sha256",
        "model_options_sha256",
        "controller_state_sha256",
        "rng_state_sha256",
        "physics_state_sha256",
        "sensor_cache_object_id",
        "camera_object_id",
        "physical_step",
        "command_count",
        "sensor_noise_std_m",
        "sim_time_s",
    )
)


class StateGuardError(ValueError):
    """Unsupported input or a changed snapshot; callers must stop acquisition."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError) as error:
        raise StateGuardError("finite JSON state required") from error


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _macro(text: str, name: str) -> str:
    match = re.search(r"^#define " + name + r"\s+\\\n(.*?)(?=\n\n)", text, re.M | re.S)
    if match is None:
        raise StateGuardError("frozen header macro unavailable: " + name)
    return match.group(1)


@dataclass(frozen=True, slots=True)
class _Getter:
    name: str
    dtype: str
    source: str
    dimension: str
    width: int


@dataclass(frozen=True, slots=True)
class MujocoStateContract:
    """Exact immutable local header contract, revalidated at every snapshot.

    SHA inputs are compatibility pins, not source authenticity or certification.
    Header-derived known names permit empty arrays from InitPyArray's zero-size
    branch; positive owning arrays qualify only as dynamic null allocations.
    """

    mjxmacro_bytes: bytes = field(repr=False)
    mjdata_bytes: bytes = field(repr=False)
    binding_sha256: str
    version: str
    getters: tuple[_Getter, ...] = field(init=False)
    known_fields: tuple[str, ...] = field(init=False)
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != VERSION:
            raise StateGuardError("unsupported MuJoCo version")
        for raw, expected in (
            (self.mjxmacro_bytes, MJXMACRO_SHA256),
            (self.mjdata_bytes, MJDATA_SHA256),
        ):
            if type(raw) is not bytes or _sha(raw) != expected:
                raise StateGuardError("frozen header pin mismatch")
        if type(self.binding_sha256) is not str or self.binding_sha256 != BINDING_SHA256:
            raise StateGuardError("frozen binding pin mismatch")
        text = self.mjxmacro_bytes.decode("ascii")
        getters = []
        for family in _FAMILIES:
            for line in _macro(text, "MJDATA_ARENA_POINTERS_" + family).splitlines():
                if not line.strip():
                    continue
                match = re.fullmatch(
                    r"\s*X(?:NV)?\s*\(\s*(int|mjtNum),\s*(\w+),\s*"
                    r"MJ_([MD])\((\w+)\),\s*(\d+)\s*\)\s*\\?",
                    line,
                )
                if match is None:
                    raise StateGuardError("unrecognized frozen getter declaration")
                dtype, name, source, dimension, width = match.groups()
                getters.append(
                    _Getter(name, "<i4" if dtype == "int" else "<f8", source, dimension, int(width))
                )
        getters.sort(key=lambda item: item.name)
        known = {item.name for item in getters}
        for macro in ("MJDATA_POINTERS", "MJDATA_VECTOR"):
            known.update(re.findall(r"X(?:NV)?\s*\(\s*\w+\s*,\s*(\w+)\s*,", _macro(text, macro)))
        object.__setattr__(self, "getters", tuple(getters))
        object.__setattr__(self, "known_fields", tuple(sorted(known)))
        object.__setattr__(
            self,
            "digest",
            _sha(_json((VERSION, MJXMACRO_SHA256, MJDATA_SHA256, BINDING_SHA256)).encode()),
        )


@dataclass(frozen=True, slots=True)
class ArrayField:
    name: str
    status: str
    storage: str
    shape: tuple[int, ...]
    dtype: str
    dtype_descr_json: str
    byte_count: int
    byte_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or self.name.startswith("_"):
            raise StateGuardError("invalid array name")
        if type(self.shape) is not tuple or any(type(i) is not int or i < 0 for i in self.shape):
            raise StateGuardError("invalid array shape")
        if type(self.byte_count) is not int or self.byte_count < 0:
            raise StateGuardError("invalid byte count")
        if type(self.storage) is not str or self.storage not in {"OWNING", "VIEW"}:
            raise StateGuardError("invalid array storage")
        if type(self.dtype) is not str or type(self.dtype_descr_json) is not str:
            raise StateGuardError("invalid dtype")
        try:
            dtype = np.dtype(self.dtype)
            description = json.loads(self.dtype_descr_json)
        except (ValueError, TypeError) as error:
            raise StateGuardError("invalid dtype contract") from error
        if dtype.hasobject or self.byte_count != math.prod(self.shape) * dtype.itemsize:
            raise StateGuardError("shape/dtype/byte count inconsistent")
        if _json(description) != self.dtype_descr_json or type(self.status) is not str:
            raise StateGuardError("invalid structural domain")
        if self.status == "DATA_BACKED":
            valid = self.storage == "VIEW" and self.byte_count > 0 and _is_sha(self.byte_sha256)
        elif self.status == "UNSUPPORTED_NULL_ALLOCATION":
            valid = self.storage == "OWNING" and self.byte_count > 0 and self.byte_sha256 is None
        elif self.status == "EMPTY":
            valid = self.byte_count == 0 and self.byte_sha256 is None
        else:
            valid = False
        if not valid:
            raise StateGuardError("invalid array support/byte-hash contract")

    def domain(self) -> tuple[object, ...]:
        return (
            self.name,
            self.status,
            self.storage,
            self.shape,
            self.dtype,
            self.dtype_descr_json,
            self.byte_count,
            self.byte_sha256,
        )


@dataclass(frozen=True, slots=True)
class DataArraySnapshot:
    """Hashes and immutable structural records only; retained arrays cannot alias."""

    contract_digest: str
    fields: tuple[ArrayField, ...]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_sha(self.contract_digest) or type(self.fields) is not tuple:
            raise StateGuardError("invalid data snapshot")
        records = []
        for member in self.fields:
            if type(member) is not ArrayField:
                raise StateGuardError("exact immutable array record required")
            records.append(replace(member))
        names = [item.name for item in records]
        if names != sorted(set(names)):
            raise StateGuardError("array inventory must be unique and sorted")
        object.__setattr__(self, "fields", tuple(records))
        object.__setattr__(
            self,
            "digest",
            _sha(_json((self.contract_digest, [r.domain() for r in records])).encode()),
        )


def _dimensions(contract: MujocoStateContract, data: object, model: object) -> dict[str, int]:
    result = {}
    for source, dimension in sorted({(g.source, g.dimension) for g in contract.getters}):
        value = getattr(model if source == "M" else data, dimension, None)
        if type(value) is not int or value < 0:
            raise StateGuardError("exact nonnegative dimension required: " + dimension)
        result[source + ":" + dimension] = value
    return result


def snapshot_data_arrays(
    data: object, model: object, *, contract: MujocoStateContract, runtime_version: str
) -> DataArraySnapshot:
    """Read each public array once; fail closed on unsupported owning storage.

    Empty known fields record structure and storage. Unknown owning fields,
    including empty fields, cannot become silently stable. Pointer addresses
    are diagnostics rather than numerical state; active view bytes are hashed.
    """
    if type(contract) is not MujocoStateContract:
        raise StateGuardError("exact immutable MuJoCo contract required")
    contract = replace(contract)
    if type(runtime_version) is not str or runtime_version != contract.version:
        raise StateGuardError("runtime MuJoCo version mismatch")
    dimensions = _dimensions(contract, data, model)
    dynamic = {getter.name: getter for getter in contract.getters}
    records = []
    found_dynamic = set()
    for name in sorted(dir(data)):
        if name.startswith("_"):
            continue
        member = getattr(data, name)
        if not isinstance(member, np.ndarray):
            if name in dynamic:
                raise StateGuardError("dynamic getter is not an ndarray: " + name)
            continue
        if type(member) is not np.ndarray or member.dtype.hasobject:
            raise StateGuardError("plain numeric ndarray required: " + name)
        copied = np.array(member, copy=True, order="C", subok=False)
        shape = tuple(copied.shape)
        owning, base = bool(member.flags.owndata), member.base
        if name in dynamic:
            found_dynamic.add(name)
            getter = dynamic[name]
            size = dimensions[getter.source + ":" + getter.dimension]
            expected = (size,) if getter.width == 1 else (size, getter.width)
            if shape != expected or copied.dtype != np.dtype(getter.dtype):
                raise StateGuardError("dynamic getter shape/dtype mismatch: " + name)
        if owning:
            if base is not None or name not in contract.known_fields:
                raise StateGuardError("unknown owning storage: " + name)
            if copied.nbytes and name not in dynamic:
                raise StateGuardError("unknown positive owning storage: " + name)
            status = "UNSUPPORTED_NULL_ALLOCATION" if copied.nbytes else "EMPTY"
            byte_hash = None
        else:
            if base is None:
                raise StateGuardError("unbacked nonowning array: " + name)
            status = "DATA_BACKED" if copied.nbytes else "EMPTY"
            byte_hash = _sha(copied.tobytes(order="C")) if copied.nbytes else None
        records.append(
            ArrayField(
                name,
                status,
                "OWNING" if owning else "VIEW",
                shape,
                copied.dtype.str,
                _json(copied.dtype.descr),
                copied.nbytes,
                byte_hash,
            )
        )
    if found_dynamic != dynamic.keys():
        raise StateGuardError("dynamic getter inventory incomplete")
    if _dimensions(contract, data, model) != dimensions:
        raise StateGuardError("dimensions changed during snapshot")
    return DataArraySnapshot(contract.digest, tuple(records))


@dataclass(frozen=True, slots=True)
class GuardedStateSnapshot:
    arrays: DataArraySnapshot
    protected_json: str
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.arrays) is not DataArraySnapshot or type(self.protected_json) is not str:
            raise StateGuardError("exact immutable guarded snapshot required")
        arrays = replace(self.arrays)
        try:
            protected = json.loads(self.protected_json)
        except (ValueError, TypeError) as error:
            raise StateGuardError("invalid protected JSON") from error
        if type(protected) is not dict or not _PROTECTED_KEYS <= protected.keys():
            raise StateGuardError("original protected components incomplete")
        if "data_arrays_sha256" in protected:
            raise StateGuardError("legacy data aggregate cannot replace support-aware guard")
        canonical = _json(protected)
        object.__setattr__(self, "arrays", arrays)
        object.__setattr__(self, "protected_json", canonical)
        object.__setattr__(self, "digest", _sha(_json((arrays.digest, canonical)).encode()))


def attach_protected_state(
    arrays: DataArraySnapshot, protected_state: Mapping[str, Any]
) -> GuardedStateSnapshot:
    """Preserve every supplied protection and detach nested mutable input.

    The caller obtains these components from the existing controller, model,
    RNG/cache and clock interfaces. Additional JSON components are also hashed.
    This composition does not verify source authenticity or grant authority.
    """
    if any(type(key) is not str for key in protected_state):
        raise StateGuardError("protected keys must be exact strings")
    return GuardedStateSnapshot(arrays, _json(dict(protected_state)))


def assert_unchanged(
    before: DataArraySnapshot | GuardedStateSnapshot,
    after: DataArraySnapshot | GuardedStateSnapshot,
) -> None:
    """Reject byte, support, type, shape, inventory or protected-state changes."""
    if type(before) not in {DataArraySnapshot, GuardedStateSnapshot} or type(after) is not type(
        before
    ):
        raise StateGuardError("matching exact immutable snapshots required")
    if replace(before).digest != replace(after).digest:
        raise StateGuardError("guarded state changed")
