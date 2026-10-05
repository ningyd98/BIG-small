"""完整分卷检查、安全流式解压和带摘要的原子发布。"""

from __future__ import annotations

import bisect
import io
import json
import os
import re
import shutil
import stat
import tarfile
import threading
import uuid
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import IO, Any, cast

from .transfer import GiB, _atomic_json, hash_file

_DEFAULT_RESERVE = 50 * GiB
_INSPECTION_LIMIT = 1024 * GiB
_COMPLETE_MARKER = ".extraction-complete.json"
_STAGING_MARKER = ".extraction-state.json"
_PART = re.compile(r"(.+\.(?:7z|tar\.gz|tgz))\.(part)?([0-9]{3,}|[a-z]{2,})\Z")


def _free_bytes(path: Path) -> int:
    while not path.exists():
        path = path.parent
    return int(shutil.disk_usage(path).free)


def _member_path(value: str, *, directory: bool = False) -> str:
    """拒绝绝对路径、上跳、平台路径和完成标记覆盖。"""
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or value.startswith("/")
        or ".." in value.split("/")
    ):
        raise ValueError("unsafe archive member path")
    while value.startswith("./"):
        value = value[2:]
    normalized = PurePosixPath(value).as_posix()
    if normalized in (".", ""):
        if directory:
            return ""
        raise ValueError("unsafe empty archive member path")
    if PurePosixPath(normalized).parts[0] in (_COMPLETE_MARKER, _STAGING_MARKER):
        raise ValueError("reserved archive member path")
    return normalized


def _number(part: str) -> int:
    if part.isdecimal():
        return int(part)
    value = 0
    for letter in part:
        value = value * 26 + ord(letter) - ord("a")
    return value + 1


def _parts(paths: Sequence[str | Path]) -> tuple[list[Path], str, Path]:
    if not paths:
        raise ValueError("archive parts are required")
    parts = [Path(path).absolute() for path in paths]
    if len(set(parts)) != len(parts):
        raise ValueError("duplicate archive part")
    for path in parts:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError("missing, empty or unsafe archive part")
    match = _PART.fullmatch(parts[0].name)
    if not match:
        if len(parts) != 1:
            raise ValueError("unrecognized archive part names")
        base = parts[0]
    else:
        base = parts[0].with_name(match[1])
        suffix = match[2] or ""
        numbers = []
        for path in parts:
            current = _PART.fullmatch(path.name)
            if (
                path.parent != base.parent
                or current is None
                or current[1] != base.name
                or (current[2] or "") != suffix
                or len(current[3]) != len(match[3])
                or current[3].isdecimal() != match[3].isdecimal()
            ):
                raise ValueError("archive parts must belong to one source group")
            numbers.append(_number(current[3]))
        if numbers != list(range(1, len(parts) + 1)):
            raise ValueError("archive parts are missing or not in complete order")
        present = {
            path
            for path in base.parent.glob(base.name + "." + suffix + "*")
            if _PART.fullmatch(path.name)
        }
        if present != set(parts):
            raise ValueError("archive part list omits an available required volume")
    if base.name.endswith(".7z"):
        kind = "7z"
    elif base.name.endswith((".tar.gz", ".tgz")):
        kind = "tar.gz"
    elif base.name.endswith(".tar"):
        kind = "tar"
    elif base.name.endswith(".zip"):
        kind = "zip"
    else:
        raise ValueError("unsupported archive format")
    return parts, kind, base


class _PartsReader(io.RawIOBase):
    """把分卷作为一个可定位流读取，不产生拼接归档副本。"""

    def __init__(self, parts: Sequence[Path]) -> None:
        super().__init__()
        self.handles = [path.open("rb") for path in parts]
        self.offsets = [0]
        for path in parts:
            self.offsets.append(self.offsets[-1] + path.stat().st_size)
        self.position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_CUR:
            offset += self.position
        elif whence == os.SEEK_END:
            offset += self.offsets[-1]
        elif whence != os.SEEK_SET:
            raise ValueError("invalid seek mode")
        if offset < 0:
            raise ValueError("negative archive seek")
        self.position = offset
        return offset

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.offsets[-1] - self.position
        chunks = []
        remaining = min(size, max(0, self.offsets[-1] - self.position))
        while remaining:
            index = bisect.bisect_right(self.offsets, self.position) - 1
            handle = self.handles[index]
            handle.seek(self.position - self.offsets[index])
            take = min(remaining, self.offsets[index + 1] - self.position)
            chunk = handle.read(take)
            if len(chunk) != take:
                raise ValueError("archive part changed during read")
            chunks.append(chunk)
            self.position += take
            remaining -= take
        return b"".join(chunks)

    def readinto(self, buffer: Any) -> int:
        value = self.read(len(buffer))
        buffer[: len(value)] = value
        return len(value)

    def close(self) -> None:
        for handle in self.handles:
            handle.close()
        super().close()


@contextmanager
def _open_archive(parts: list[Path], kind: str, base: Path) -> Iterator[Any]:
    if kind == "zip":
        with zipfile.ZipFile(base, "r") as archive:
            yield archive
    elif kind == "7z":
        import multivolumefile
        import py7zr

        if len(parts) == 1 and parts[0] == base:
            with py7zr.SevenZipFile(base, "r", max_extract_size=_INSPECTION_LIMIT) as archive:
                yield archive
        else:
            with multivolumefile.open(base, "rb") as stream:
                with py7zr.SevenZipFile(
                    cast(IO[bytes], stream), "r", max_extract_size=_INSPECTION_LIMIT
                ) as archive:
                    yield archive
    else:
        with _PartsReader(parts) as stream:
            with tarfile.open(fileobj=stream, mode="r:gz" if kind == "tar.gz" else "r:") as archive:
                yield archive


def _check_members(members: list[dict[str, Any]], limit: int | None) -> int:
    seen = set()
    total = 0
    for member in members:
        path = member["path"]
        if path in seen:
            raise ValueError("duplicate normalized archive member path")
        seen.add(path)
        if member["size"] < 0:
            raise ValueError("negative archive member size")
        total += member["size"]
        if total > _INSPECTION_LIMIT or (limit is not None and total > limit):
            raise RuntimeError("EXPANSION: archive listing exceeds expanded byte cap")
    file_paths = {member["path"] for member in members if member["type"] == "file"}
    for member in members:
        if any(parent.as_posix() in file_paths for parent in PurePosixPath(member["path"]).parents):
            raise ValueError("archive member path collides with a file ancestor")
    return total


def inspect_archive(
    parts: Sequence[str | Path],
    *,
    max_expanded_bytes: int | None = None,
) -> dict[str, Any]:
    """列举并测试完整归档，先拒绝所有不安全条目，包括未选条目。"""
    if max_expanded_bytes is not None and max_expanded_bytes < 0:
        raise ValueError("max_expanded_bytes must be nonnegative")
    ordered, kind, base = _parts(parts)
    members = []
    listing_bytes = 0
    with _open_archive(ordered, kind, base) as archive:
        if kind == "7z":
            for info in archive.list():
                if info.is_symlink or not (info.is_file or info.is_directory):
                    raise ValueError("archive link or special member rejected")
                name = _member_path(info.filename, directory=info.is_directory)
                if name:
                    members.append(
                        {
                            "path": name,
                            "source_name": info.filename,
                            "type": "directory" if info.is_directory else "file",
                            "size": 0 if info.is_directory else info.uncompressed,
                        }
                    )
            expanded = _check_members(members, max_expanded_bytes)
            packed_test = archive.test()
            if packed_test is False:
                raise ValueError("archive packed CRC integrity failed")
            archive.reset()
            if archive.testzip() is not None:
                raise ValueError("archive expanded CRC integrity failed")
        elif kind == "zip":
            for info in archive.infolist():
                mode = stat.S_IFMT(info.external_attr >> 16)
                directory = info.is_dir()
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or (
                    mode == stat.S_IFDIR and not directory
                ):
                    raise ValueError("archive link or special member rejected")
                if info.flag_bits & 1:
                    raise ValueError("encrypted archive members are unsupported")
                name = _member_path(info.orig_filename, directory=directory)
                if name:
                    members.append(
                        {
                            "path": name,
                            "source_name": info.filename,
                            "type": "directory" if directory else "file",
                            "size": 0 if directory else info.file_size,
                        }
                    )
            expanded = _check_members(members, max_expanded_bytes)
            # 验证所有成员的 CRC，包括未选成员；仅在目录展开量通过后读取。
            for member in members:
                if member["type"] == "directory":
                    continue
                size = 0
                with archive.open(member["source_name"]) as stream:
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        if size > member["size"]:
                            raise RuntimeError("EXPANSION: ZIP member exceeded listed size")
                if size != member["size"]:
                    raise ValueError("ZIP member content was truncated")
        else:
            for info in archive:
                if not (info.isfile() or info.isdir()) or info.issparse():
                    raise ValueError("archive link or special member rejected")
                name = _member_path(info.name, directory=info.isdir())
                if name:
                    listing_bytes += 0 if info.isdir() else info.size
                    if listing_bytes > _INSPECTION_LIMIT or (
                        max_expanded_bytes is not None and listing_bytes > max_expanded_bytes
                    ):
                        raise RuntimeError("EXPANSION: archive header exceeds expanded byte cap")
                    members.append(
                        {
                            "path": name,
                            "source_name": info.name,
                            "type": "directory" if info.isdir() else "file",
                            "size": 0 if info.isdir() else info.size,
                        }
                    )
            expanded = _check_members(members, max_expanded_bytes)
            # 读取尾部以验证 gzip 结束标记和 CRC，不能只信 tar 目录。
            while archive.fileobj.read(1024 * 1024):
                pass
    hashes = [
        {"path": str(path), "size": path.stat().st_size, "sha256": hash_file(path)}
        for path in ordered
    ]
    return {
        "format": kind,
        "parts": [str(path) for path in ordered],
        "members": members,
        "uncompressed_bytes": expanded,
        "compressed_bytes": sum(item["size"] for item in hashes),
        "archive_hashes": hashes,
        "integrity_status": "TESTED",
    }


def _selection(
    members: list[dict[str, Any]],
    selected_members: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], list[str] | None]:
    if selected_members is None:
        return members, None
    if not selected_members or isinstance(selected_members, str):
        raise ValueError("selected_members requires a nonempty list")
    selected = []
    for name in selected_members:
        normalized = _member_path(name, directory=name.endswith("/"))
        if not normalized:
            raise ValueError("empty selected member path")
        selected.append(normalized + ("/" if name.endswith("/") else ""))
    selected = sorted(set(selected))
    chosen = []
    found = set()
    for member in members:
        for selector in selected:
            if member["path"] == selector.rstrip("/") or (
                selector.endswith("/") and member["path"].startswith(selector)
            ):
                chosen.append(member)
                found.add(selector)
                break
    if set(selected) != found:
        raise ValueError("selected member does not exist in archive listing")
    return chosen, selected


class _Expansion:
    """每次写入前检查展开量和实时剩余磁盘。"""

    def __init__(self, root: Path, limit: int, reserve: int) -> None:
        self.root, self.limit, self.reserve = root, limit, reserve
        self.written = 0
        self.lock = threading.Lock()

    def check(self, size: int) -> None:
        with self.lock:
            if self.written + size > self.limit:
                raise RuntimeError("EXPANSION: actual writes exceed expanded byte cap")
            if _free_bytes(self.root) < self.reserve + size:
                raise RuntimeError("BLOCKED_STORAGE: extraction reached disk reserve")
            self.written += size


def _extract_tar(
    archive: Any, chosen: list[dict[str, Any]], stage: Path, guard: _Expansion
) -> None:
    for member in chosen:
        path = stage / member["path"]
        if member["type"] == "directory":
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = archive.extractfile(member["source_name"])
        if stream is None:
            raise ValueError("regular archive member has no readable content")
        with stream, path.open("xb") as output:
            written = 0
            while chunk := stream.read(1024 * 1024):
                guard.check(len(chunk))
                written += len(chunk)
                if written > member["size"]:
                    raise RuntimeError("EXPANSION: member exceeded listed size")
                output.write(chunk)
            if written != member["size"]:
                raise ValueError("member content was truncated")


def _extract_7z(archive: Any, chosen: list[dict[str, Any]], stage: Path, guard: _Expansion) -> None:
    from py7zr.io import Py7zIO, WriterFactory

    allowed = {member["path"]: member["size"] for member in chosen if member["type"] == "file"}
    handles = []

    class LimitedWriter(Py7zIO):
        """受展开上限和磁盘门禁控制的单成员文件写入器。"""

        def __init__(self, path: Path, size: int) -> None:
            self.handle = path.open("xb+")
            self.limit = size
            self.length = 0

        def write(self, data: bytes | bytearray) -> int:
            if self.handle.tell() + len(data) > self.limit:
                raise RuntimeError("EXPANSION: member exceeded listed size")
            guard.check(len(data))
            count = self.handle.write(data)
            self.length = max(self.length, self.handle.tell())
            return count

        def read(self, size: int | None = None) -> bytes:
            return self.handle.read(-1 if size is None else size)

        def seek(self, offset: int, whence: int = 0) -> int:
            return self.handle.seek(offset, whence)

        def flush(self) -> None:
            self.handle.flush()

        def size(self) -> int:
            return self.length

        def close(self) -> None:
            self.handle.close()

    class LimitedFactory(WriterFactory):
        """只为经过筛选和验证的普通文件创建输出。"""

        def create(self, filename: str) -> LimitedWriter:
            path = Path(filename)
            relative = path.relative_to(stage).as_posix()
            if relative not in allowed:
                raise ValueError("unexpected archive writer path")
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = LimitedWriter(path, allowed[relative])
            handles.append(writer)
            return writer

    try:
        for member in chosen:
            if member["type"] == "directory":
                (stage / member["path"]).mkdir(parents=True, exist_ok=True)
        archive.extract(
            path=stage,
            targets=[member["source_name"] for member in chosen],
            recursive=False,
            factory=LimitedFactory(),
        )
    finally:
        for handle in handles:
            handle.close()


def _extract_zip(
    archive: Any, chosen: list[dict[str, Any]], stage: Path, guard: _Expansion
) -> None:
    """只流式创建已核验的普通 ZIP 成员，沿用展开与磁盘门禁。"""
    for member in chosen:
        path = stage / member["path"]
        if member["type"] == "directory":
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member["source_name"]) as stream, path.open("xb") as output:
            written = 0
            while chunk := stream.read(1024 * 1024):
                guard.check(len(chunk))
                written += len(chunk)
                if written > member["size"]:
                    raise RuntimeError("EXPANSION: ZIP member exceeded listed size")
                output.write(chunk)
            if written != member["size"]:
                raise ValueError("ZIP member content was truncated")


def _reused(
    destination: Path,
    binding: dict[str, Any],
    chosen: list[dict[str, Any]],
) -> dict[str, Any]:
    marker = destination / _COMPLETE_MARKER
    if destination.is_symlink() or marker.is_symlink() or not marker.is_file():
        raise RuntimeError("INCOMPLETE: existing destination has no trusted completion marker")
    try:
        record = json.loads(marker.read_text())
        if any(record.get(key) != value for key, value in binding.items()):
            raise ValueError("archive or selection mismatch")
        expected = {member["path"]: member["size"] for member in chosen if member["type"] == "file"}
        recorded = {file["path"]: file["size"] for file in record["files"]}
        if recorded != expected or len(recorded) != len(record["files"]):
            raise ValueError("published file manifest does not match selected archive members")
        for file in record["files"]:
            relative = _member_path(file["path"])
            path = destination / relative
            if any(parent.is_symlink() for parent in path.parents if parent != destination.parent):
                raise ValueError("published symlink parent")
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size != file["size"]
                or hash_file(path) != file["sha256"]
            ):
                raise ValueError("published HASH mismatch")
        return {**record, "status": "REUSED", "destination": str(destination)}
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("INCOMPLETE: completion marker or published HASH mismatch") from exc


def extract_archive(
    parts: Sequence[str | Path],
    destination: str | Path,
    *,
    selected_members: Sequence[str] | None = None,
    max_expanded_bytes: int | None = None,
    minimum_free_bytes: int = _DEFAULT_RESERVE,
) -> dict[str, Any]:
    """先完整测试再限量解压；仅成功的临时目录可原子发布。"""
    if minimum_free_bytes < 0 or (max_expanded_bytes is not None and max_expanded_bytes < 0):
        raise ValueError("extraction limits must be nonnegative")
    info = inspect_archive(parts)
    chosen, selection = _selection(info["members"], selected_members)
    expanded = sum(member["size"] for member in chosen)
    limit = expanded if max_expanded_bytes is None else max_expanded_bytes
    if expanded > limit:
        raise RuntimeError("EXPANSION: selected members exceed expanded byte cap")
    destination = Path(destination).absolute()
    binding = {"archive_hashes": info["archive_hashes"], "selected_members": selection}
    if destination.exists() or destination.is_symlink():
        return _reused(destination, binding, chosen)
    if _free_bytes(destination.parent) < expanded + minimum_free_bytes:
        raise RuntimeError("BLOCKED_STORAGE: listing and disk reserve gate rejected extraction")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name("." + destination.name + ".extracting-" + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    _atomic_json(stage / _STAGING_MARKER, {**binding, "state": "EXTRACTING"})
    guard = _Expansion(stage, limit, minimum_free_bytes)
    ordered, kind, base = _parts(parts)
    try:
        with _open_archive(ordered, kind, base) as archive:
            if kind == "7z":
                _extract_7z(archive, chosen, stage, guard)
            elif kind == "zip":
                _extract_zip(archive, chosen, stage, guard)
            else:
                _extract_tar(archive, chosen, stage, guard)
        files = []
        for member in chosen:
            if member["type"] != "file":
                continue
            path = stage / member["path"]
            if path.is_symlink() or not path.is_file() or path.stat().st_size != member["size"]:
                raise ValueError("extracted file differs from tested listing")
            files.append(
                {"path": member["path"], "size": member["size"], "sha256": hash_file(path)}
            )
        record = {
            **binding,
            "format_version": 1,
            "status": "COMPLETE",
            "expanded_bytes": expanded,
            "files": files,
            "integrity_status": "TESTED",
        }
        (stage / _STAGING_MARKER).unlink()
        _atomic_json(stage / _COMPLETE_MARKER, record)
        if destination.exists() or destination.is_symlink():
            raise RuntimeError("INCOMPLETE: destination appeared during extraction")
        stage.rename(destination)
        return {**record, "destination": str(destination)}
    except BaseException as exc:
        # 保留中断目录及状态，失败目录永远不拥有可复用完成标记。
        (stage / _COMPLETE_MARKER).unlink(missing_ok=True)
        _atomic_json(
            stage / _STAGING_MARKER,
            {**binding, "state": "FAILED", "error_type": type(exc).__name__},
        )
        raise
