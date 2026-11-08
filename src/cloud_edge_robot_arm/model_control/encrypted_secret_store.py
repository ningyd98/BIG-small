"""Owner-private Fernet vault with process locking and atomic ciphertext updates.

The generated master key and ciphertext both stay on this machine. This protects
against accidental plaintext storage and other users, not a compromised owner or
root. No key export, automatic reset, cached decrypted map or plaintext fallback.
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet

from cloud_edge_robot_arm.model_control.models import SecretStoreKind
from cloud_edge_robot_arm.model_control.secret_store import SecretStoreError

LOCK_TIMEOUT_SECONDS = 5.0
MAX_CIPHERTEXT_BYTES = 8 * 1024 * 1024
MAX_PLAINTEXT_BYTES = 4 * 1024 * 1024
_KEY = "master.key"
_TOKEN = "vault.fernet"
_LOCK = "vault.lock"
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


class EncryptedFileSecretStore:
    """One versioned encrypted map; every operation opens and validates fresh FDs."""

    kind = SecretStoreKind.ENCRYPTED_FILE

    def __init__(self, directory: Path) -> None:
        # Do not resolve symlinks or open/create anything at construction time.
        self._directory = directory.absolute()

    def set_secret(self, profile_id: str, value: str) -> None:
        self._access(profile_id, action="set", value=value)

    def get_secret(self, profile_id: str) -> str | None:
        return self._access(profile_id, action="get")

    def delete_secret(self, profile_id: str) -> None:
        self._access(profile_id, action="delete")

    def has_secret(self, profile_id: str) -> bool:
        return self.get_secret(profile_id) is not None

    def _access(self, profile_id: str, *, action: str, value: str | None = None) -> str | None:
        try:
            if not isinstance(profile_id, str) or (action == "set" and not isinstance(value, str)):
                raise SecretStoreError()
            with self._locked_directory(create=action == "set") as directory_fd:
                if directory_fd is None:
                    return None
                cipher, secrets = self._load(directory_fd)
                if action == "get":
                    return secrets.get(profile_id)
                if action == "delete":
                    if profile_id not in secrets:
                        return None
                    del secrets[profile_id]
                else:
                    assert value is not None
                    secrets[profile_id] = value
                plaintext = json.dumps(
                    {"version": 1, "secrets": secrets}, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                if len(plaintext) > MAX_PLAINTEXT_BYTES:
                    raise SecretStoreError()
                if cipher is None:
                    master = Fernet.generate_key()
                    self._write_master(directory_fd, master)
                    cipher = Fernet(master)
                self._write_ciphertext(directory_fd, cipher.encrypt(plaintext))
                return None
        except Exception:
            # This boundary also sanitizes permission/crypto/JSON/locking failures.
            raise SecretStoreError() from None

    def _open_directory(self, *, create: bool) -> int | None:
        parts = self._directory.parts[1:]
        if not parts or ".." in parts:
            raise SecretStoreError()
        fd = os.open("/", _DIR_FLAGS)
        try:
            for index, part in enumerate(parts):
                last = index == len(parts) - 1
                parent = os.fstat(fd)
                _check_ancestor(parent)
                # A writable parent could replace the private vault itself.
                if last and stat.S_IMODE(parent.st_mode) & 0o022:
                    raise SecretStoreError()
                try:
                    child = os.open(part, _DIR_FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        return None
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass  # Another initializer created it; validate the opened FD.
                    child = os.open(part, _DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
                if last:
                    value = os.fstat(fd)
                    if value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != 0o700:
                        raise SecretStoreError()
                else:
                    _check_ancestor(os.fstat(fd))
            result = fd
            fd = -1
            return result
        finally:
            if fd >= 0:
                os.close(fd)

    @contextmanager
    def _locked_directory(self, *, create: bool) -> Iterator[int | None]:
        directory_fd = self._open_directory(create=create)
        if directory_fd is None:
            yield None
            return
        lock_fd = None
        try:
            lock_fd = self._open_lock(directory_fd, create=create)
            if lock_fd is None:
                yield None
                return
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SecretStoreError() from None
                    time.sleep(min(0.01, remaining))
            yield directory_fd
        finally:
            # close releases flock even when initialization/encryption/fsync fails.
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(directory_fd)

    def _open_lock(self, directory_fd: int, *, create: bool) -> int | None:
        try:
            fd = os.open(_LOCK, os.O_RDWR | _FILE_FLAGS, dir_fd=directory_fd)
        except FileNotFoundError:
            entries = set(os.listdir(directory_fd))
            if entries:
                # A competing initializer may have created the stable lock since
                # our first open. Never reconstruct a missing lock around data.
                fd = os.open(_LOCK, os.O_RDWR | _FILE_FLAGS, dir_fd=directory_fd)
            elif not create:
                return None
            else:
                try:
                    fd = os.open(
                        _LOCK,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | _FILE_FLAGS,
                        0o600,
                        dir_fd=directory_fd,
                    )
                except FileExistsError:
                    fd = os.open(_LOCK, os.O_RDWR | _FILE_FLAGS, dir_fd=directory_fd)
        try:
            _check_file(fd)
            return fd
        except Exception:
            os.close(fd)
            raise

    @contextmanager
    def _file(self, directory_fd: int, name: str) -> Iterator[int | None]:
        try:
            fd = os.open(name, os.O_RDONLY | _FILE_FLAGS, dir_fd=directory_fd)
        except FileNotFoundError:
            yield None
            return
        try:
            _check_file(fd)
            yield fd
        finally:
            os.close(fd)

    def _load(self, directory_fd: int) -> tuple[Fernet | None, dict[str, str]]:
        with self._file(directory_fd, _KEY) as key_fd, self._file(directory_fd, _TOKEN) as token_fd:
            if key_fd is None and token_fd is None:
                if set(os.listdir(directory_fd)) - {_LOCK}:
                    raise SecretStoreError()
                return None, {}
            if key_fd is None or token_fd is None:
                raise SecretStoreError()
            master = _read_limited(key_fd, 44)
            if len(master) != 44:
                raise SecretStoreError()
            decoded = base64.b64decode(master, altchars=b"-_", validate=True)
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded) != master:
                raise SecretStoreError()
            cipher = Fernet(master)
            plaintext = cipher.decrypt(_read_limited(token_fd, MAX_CIPHERTEXT_BYTES))
            if len(plaintext) > MAX_PLAINTEXT_BYTES:
                raise SecretStoreError()
            payload = json.loads(plaintext, object_pairs_hook=_unique_object)
            if (
                not isinstance(payload, dict)
                or set(payload) != {"version", "secrets"}
                or type(payload["version"]) is not int
                or payload["version"] != 1
                or not isinstance(payload["secrets"], dict)
            ):
                raise SecretStoreError()
            secrets = payload["secrets"]
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in secrets.items()):
                raise SecretStoreError()
            return cipher, secrets

    def _write_master(self, directory_fd: int, master: bytes) -> None:
        fd = os.open(
            _KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_FLAGS, 0o600, dir_fd=directory_fd
        )
        try:
            _check_file(fd)
            _write_all(fd, master)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory_fd)

    def _write_ciphertext(self, directory_fd: int, token: bytes) -> None:
        if len(token) > MAX_CIPHERTEXT_BYTES:
            raise SecretStoreError()
        temporary = ".vault-" + uuid4().hex + ".tmp"
        created = False
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_FLAGS,
                0o600,
                dir_fd=directory_fd,
            )
            created = True
            try:
                _check_file(fd)
                _write_all(fd, token)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, _TOKEN, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            created = False
            os.fsync(directory_fd)
        finally:
            if created:
                os.unlink(temporary, dir_fd=directory_fd)


def _check_ancestor(value: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid not in {0, os.geteuid()}
        or (stat.S_IMODE(value.st_mode) & 0o022 and not value.st_mode & stat.S_ISVTX)
    ):
        raise SecretStoreError()


def _check_file(fd: int) -> None:
    value = os.fstat(fd)
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != 1
    ):
        raise SecretStoreError()


def _read_limited(fd: int, limit: int) -> bytes:
    if os.fstat(fd).st_size > limit:
        raise SecretStoreError()
    data = bytearray()
    while len(data) <= limit:
        chunk = os.read(fd, min(64 * 1024, limit + 1 - len(data)))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
    raise SecretStoreError()


def _write_all(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise SecretStoreError()
        remaining = remaining[written:]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SecretStoreError()
        result[key] = value
    return result
