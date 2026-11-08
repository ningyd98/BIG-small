"""Private model-key persistence; all credentials are fictional temporary fixtures."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.model_control import encrypted_secret_store as vault_module
from cloud_edge_robot_arm.model_control.encrypted_secret_store import EncryptedFileSecretStore
from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.model_control.secret_store import (
    InMemorySecretStore,
    SecretStoreError,
    create_secret_store,
)
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

FIXTURE_VALUE = "r489-fictional-credential-for-private-temporary-tests"
PREFIX = "/api/v1/model-control"


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MODEL_CONTROL_SECRET_DIR", raising=False)
    monkeypatch.delenv("MODEL_CONTROL_SECRET_STORE", raising=False)
    monkeypatch.setenv("MODEL_CONTROL_DB", str(tmp_path / "profiles.db"))
    monkeypatch.setenv("DASHBOARD_AUTH_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("BIGSMALL_VLM_ALLOW_PAID_CALL", "false")
    data_home = tmp_path / "private-user-data"
    data_home.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))


def _app():
    return create_app(PlanningPipeline(planner=MockPlannerAdapter()))


def test_default_vault_persists_when_database_parent_is_shared(tmp_path: Path) -> None:
    shared = tmp_path / "shared-project"
    shared.mkdir(mode=0o775)
    shared.chmod(0o775)
    database = shared / "profiles.db"
    store = create_secret_store(database)
    store.set_secret("existing-profile", FIXTURE_VALUE)
    recovered = create_secret_store(database).get_secret("existing-profile") == FIXTURE_VALUE
    assert recovered
    assert stat.S_IMODE(shared.stat().st_mode) == 0o775
    assert not (shared / ".model-control-secrets").exists()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, sys
from pathlib import Path
from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
store = create_secret_store(Path(sys.argv[1]))
ok = store.get_secret("existing-profile") == "r489-fictional-credential-for-private-temporary-tests"
print(json.dumps({"recovered":ok}))
""",
            str(database),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 0
    assert child.stderr == ""
    assert json.loads(child.stdout) == {"recovered": True}


def test_default_namespace_is_stable_after_chdir_and_dot_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "profiles.db"
    create_secret_store(database).set_secret("same-profile", FIXTURE_VALUE)
    dot = tmp_path / "dot"
    dot.mkdir(mode=0o700)
    monkeypatch.chdir(dot)
    equivalent = dot / ".." / "profiles.db"
    assert create_secret_store(equivalent).get_secret("same-profile") == FIXTURE_VALUE
    assert create_secret_store(database).get_secret("same-profile") == FIXTURE_VALUE


def test_different_databases_have_separate_default_namespaces(tmp_path: Path) -> None:
    first = create_secret_store(tmp_path / "first.db")
    second = create_secret_store(tmp_path / "second.db")
    assert first.get_secret("same-profile") is None
    assert not list(tmp_path.rglob("master.key"))
    first.set_secret("same-profile", "r492-first-fictional-value")
    assert second.get_secret("same-profile") is None
    second.set_secret("same-profile", "r492-second-fictional-value")
    assert first.get_secret("same-profile") == "r492-first-fictional-value"
    assert second.get_secret("same-profile") == "r492-second-fictional-value"
    assert len(list(tmp_path.rglob("master.key"))) == 2


@pytest.mark.parametrize("configured", [None, ""])
def test_unset_or_empty_xdg_uses_mocked_private_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str | None
) -> None:
    home = tmp_path / "fictional-home"
    home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    if configured is None:
        monkeypatch.delenv("XDG_DATA_HOME")
    else:
        monkeypatch.setenv("XDG_DATA_HOME", configured)
    database = tmp_path / "profiles.db"
    store = create_secret_store(database)
    assert store.get_secret("p") is None
    assert not (home / ".local").exists()
    store.set_secret("p", FIXTURE_VALUE)
    assert create_secret_store(database).get_secret("p") == FIXTURE_VALUE
    assert len(list((home / ".local" / "share" / "BIGsmall").rglob("master.key"))) == 1


def test_relative_xdg_rejected_but_explicit_override_and_session_win(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "relative-user-data")
    with pytest.raises(SecretStoreError, match="^model_secret_store_unavailable$"):
        create_secret_store(tmp_path / "profiles.db")
    explicit = tmp_path / "explicit-vault"
    monkeypatch.setenv("MODEL_CONTROL_SECRET_DIR", str(explicit))
    store = create_secret_store(tmp_path / "profiles.db")
    store.set_secret("p", FIXTURE_VALUE)
    assert (explicit / "vault.fernet").exists()
    monkeypatch.delenv("MODEL_CONTROL_SECRET_DIR")
    monkeypatch.setenv("MODEL_CONTROL_SECRET_STORE", "SESSION_ONLY")
    assert isinstance(create_secret_store(tmp_path / "profiles.db"), InMemorySecretStore)


def test_unsafe_xdg_is_rejected_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "unsafe-data"
    shared.mkdir(mode=0o777)
    shared.chmod(0o777)
    monkeypatch.setenv("XDG_DATA_HOME", str(shared / "private-child"))
    store = create_secret_store(tmp_path / "profiles.db")
    with pytest.raises(SecretStoreError):
        store.set_secret("p", FIXTURE_VALUE)
    assert not (shared / "private-child").exists()


def test_existing_active_profile_key_survives_new_api_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = _app()
    with TestClient(app) as client:
        created_response = client.post(
            PREFIX + "/profiles",
            json={
                "display_name": "Existing cloud model",
                "provider_kind": "OPENAI_COMPATIBLE",
                "model_name": "fictional-model",
                "base_url": "https://api.example.test",
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        profile_id = created["profile_id"]
        assert client.post(f"{PREFIX}/profiles/{profile_id}/activate").status_code == 200
        updated_response = client.patch(
            f"{PREFIX}/profiles/{profile_id}", json={"api_key": FIXTURE_VALUE}
        )
        assert updated_response.status_code == 200
        assert updated_response.json()["api_key"] is None
    del app
    new_app = _app()
    with TestClient(new_app) as client:
        recovered = client.get(PREFIX + "/profiles").json()[0]
        internal_key_recovered = (
            new_app.state.model_control_service.secret_store.get_secret(profile_id) == FIXTURE_VALUE
        )
        assert internal_key_recovered
        assert recovered["secret_present"] is True
        assert recovered["secret_store_kind"] == "ENCRYPTED_FILE"
        assert recovered["api_key"] is None
        assert recovered["active"] is True
        for key in ("profile_id", "display_name", "base_url", "model_name"):
            assert recovered[key] == created[key]
        assert FIXTURE_VALUE not in str(recovered)
        received = []

        def fake_provider(request, **kwargs):
            received.append(request.get_header("Authorization") == "Bearer " + FIXTURE_VALUE)
            return io.BytesIO(b'{"choices":[{"message":{"content":"{}"}}]}')

        monkeypatch.setattr("urllib.request.urlopen", fake_provider)
        result = client.post(f"{PREFIX}/profiles/{profile_id}/test")
        assert result.status_code == 200
        assert result.json()["authenticated"] is True
        assert received == [True]
        assert FIXTURE_VALUE not in result.text
    # This independent interpreter cannot inherit an in-memory SecretStore.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, os
from pathlib import Path
from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
store = create_secret_store(Path(os.environ["MODEL_CONTROL_DB"]))
value = store.get_secret(os.environ["R489_TEST_PROFILE"])
print(json.dumps({"recovered": value ==
    "r489-fictional-credential-for-private-temporary-tests"}))
""",
        ],
        env={**os.environ, "R489_TEST_PROFILE": profile_id},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 0
    assert json.loads(child.stdout) == {"recovered": True}
    assert child.stderr == ""
    assert FIXTURE_VALUE not in child.stdout + caplog.text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert FIXTURE_VALUE.encode() not in path.read_bytes()


def test_recreated_session_service_reports_actual_missing_key(tmp_path: Path) -> None:
    repository = SQLiteModelProfileRepository(tmp_path / "session.db")
    service = ModelControlService(repository=repository, secret_store=InMemorySecretStore())
    profile = service.create_profile(
        display_name="Session model",
        provider_kind=PlannerProviderKind.RULE_BASED,
        model_name="rule-based",
        api_key=FIXTURE_VALUE,
    )
    recreated = ModelControlService(repository=repository, secret_store=InMemorySecretStore())
    assert recreated.get_profile(profile.profile_id).secret_present is False
    assert recreated.list_profiles()[0].secret_present is False


def test_lazy_factory_and_explicit_session_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "custom-vault"
    monkeypatch.setenv("MODEL_CONTROL_SECRET_DIR", str(target))
    store = create_secret_store(tmp_path / "profiles.db")
    assert store.kind.value == "ENCRYPTED_FILE"
    assert store.get_secret("missing") is None
    store.delete_secret("missing")
    assert not target.exists()
    monkeypatch.setenv("MODEL_CONTROL_SECRET_STORE", "SESSION_ONLY")
    assert isinstance(create_secret_store(tmp_path / "profiles.db"), InMemorySecretStore)
    for bad in ("", "ENVIRONMENT", "encrypted_file", "unknown"):
        monkeypatch.setenv("MODEL_CONTROL_SECRET_STORE", bad)
        with pytest.raises(SecretStoreError, match="^model_secret_store_unavailable$"):
            create_secret_store(tmp_path / "profiles.db")


def test_rotation_deletion_and_paths_are_encrypted(tmp_path: Path) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    identity = "../../profile/never-a-path"
    store.set_secret(identity, FIXTURE_VALUE)
    master = (directory / "master.key").read_bytes()
    assert master != FIXTURE_VALUE.encode()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert set(p.name for p in directory.iterdir()) == {"master.key", "vault.fernet", "vault.lock"}
    for path in directory.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_nlink == 1
        assert FIXTURE_VALUE.encode() not in path.read_bytes()
    reopened = EncryptedFileSecretStore(directory)
    assert reopened.get_secret(identity) == FIXTURE_VALUE
    reopened.set_secret(identity, "r489-rotated-fixture")
    assert store.get_secret(identity) == "r489-rotated-fixture"
    assert (directory / "master.key").read_bytes() == master
    store.delete_secret(identity)
    assert not reopened.has_secret(identity)
    assert (directory / "master.key").read_bytes() == master


def test_patch_blank_omitted_and_store_kind_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with TestClient(_app()) as client:
        created = client.post(
            PREFIX + "/profiles",
            json={
                "display_name": "rule",
                "provider_kind": "RULE_BASED",
                "model_name": "rule-based",
                "api_key": FIXTURE_VALUE,
            },
        ).json()
        profile_id = created["profile_id"]
        assert created["secret_store_kind"] == "ENCRYPTED_FILE"
        assert (
            client.patch(
                f"{PREFIX}/profiles/{profile_id}", json={"display_name": "renamed"}
            ).json()["secret_present"]
            is True
        )
        cleared = client.patch(f"{PREFIX}/profiles/{profile_id}", json={"api_key": ""}).json()
        assert cleared["secret_present"] is False
        assert cleared["api_key"] is None
        assert (
            client.patch(f"{PREFIX}/profiles/{profile_id}", json={"api_key": FIXTURE_VALUE}).json()[
                "secret_present"
            ]
            is True
        )
        modes = client.get(PREFIX + "/capabilities").json()["secret_store_modes"]
        assert set(modes) == {"ENCRYPTED_FILE", "SESSION_ONLY"}
    monkeypatch.setenv("MODEL_CONTROL_SECRET_STORE", "SESSION_ONLY")
    with TestClient(_app()) as client:
        actual = client.get(PREFIX + "/profiles").json()[0]
        assert actual["secret_present"] is False
        assert actual["secret_store_kind"] == "SESSION_ONLY"
        patched = client.patch(
            f"{PREFIX}/profiles/{profile_id}", json={"display_name": "renamed-again"}
        ).json()
        assert patched["secret_present"] is False
        assert patched["secret_store_kind"] == "SESSION_ONLY"


@pytest.mark.parametrize(
    "damage",
    [
        "missing-master",
        "wrong-master",
        "truncated-master",
        "invalid-master",
        "tampered-token",
        "truncated-token",
        "missing-token",
        "oversize-token",
        "version",
        "bool-version",
        "json",
        "mapping",
        "value",
        "extra-field",
        "duplicate-field",
        "oversize-plaintext",
    ],
)
def test_corruption_fails_closed_without_reset(tmp_path: Path, damage: str) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    master = directory / "master.key"
    token = directory / "vault.fernet"
    cipher = Fernet(master.read_bytes())
    if damage == "missing-master":
        master.unlink()
    elif damage == "wrong-master":
        master.write_bytes(Fernet.generate_key())
    elif damage == "truncated-master":
        master.write_bytes(b"invalid")
    elif damage == "invalid-master":
        master.write_bytes(b"!" * 44)
    elif damage == "tampered-token":
        token.write_bytes(token.read_bytes()[:-20] + b"x" * 20)
    elif damage == "truncated-token":
        token.write_bytes(b"gAAAA")
    elif damage == "missing-token":
        token.unlink()
    elif damage == "oversize-token":
        token.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    else:
        plaintext = {
            "version": b'{"version":2,"secrets":{}}',
            "bool-version": b'{"version":true,"secrets":{}}',
            "json": b"invalid json",
            "mapping": b'{"version":1,"secrets":[]}',
            "value": b'{"version":1,"secrets":{"p":123}}',
            "extra-field": b'{"version":1,"secrets":{},"other":1}',
            "duplicate-field": b'{"version":1,"version":1,"secrets":{}}',
            "oversize-plaintext": b" " * (4 * 1024 * 1024 + 1),
        }[damage]
        token.write_bytes(cipher.encrypt(plaintext))
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    for operation in (
        lambda: store.get_secret("p"),
        lambda: store.has_secret("p"),
        lambda: store.set_secret("new", "r489-new"),
        lambda: store.delete_secret("p"),
    ):
        with pytest.raises(SecretStoreError) as error:
            operation()
        assert str(error.value) == "model_secret_store_unavailable"
        assert error.value.__suppress_context__
    assert {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()} == before


def test_api_corruption_returns_only_fixed_error(tmp_path: Path) -> None:
    with TestClient(_app()) as client:
        assert (
            client.post(
                PREFIX + "/profiles",
                json={
                    "display_name": "rule",
                    "provider_kind": "RULE_BASED",
                    "model_name": "rule-based",
                    "api_key": FIXTURE_VALUE,
                },
            ).status_code
            == 201
        )
    tokens = list(tmp_path.rglob("vault.fernet"))
    assert len(tokens) == 1
    tokens[0].write_bytes(b"r489-sensitive-looking-error-content")
    with TestClient(_app()) as client:
        result = client.get(PREFIX + "/profiles")
        assert result.status_code == 400
        assert result.json() == {
            "error": "bad_request",
            "message": "model_secret_store_unavailable",
        }
        assert FIXTURE_VALUE not in result.text
        assert str(tmp_path) not in result.text


@pytest.mark.parametrize("target", ["vault", "master.key", "vault.fernet", "vault.lock"])
def test_insecure_modes_rejected_without_repair(tmp_path: Path, target: str) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    path = directory if target == "vault" else directory / target
    path.chmod(0o755 if target == "vault" else 0o644)
    before = path.stat().st_mode
    with pytest.raises(SecretStoreError):
        store.get_secret("p")
    assert path.stat().st_mode == before


@pytest.mark.parametrize(
    "target", ["directory", "ancestor", "master.key", "vault.fernet", "vault.lock"]
)
def test_symlinks_never_followed(
    tmp_path: Path, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    if target == "directory":
        moved = tmp_path / "actual-vault"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
    elif target == "ancestor":
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        store = EncryptedFileSecretStore(tmp_path / "alias" / "vault")
        moved = directory
    else:
        child = directory / target
        original = directory / (target + ".original")
        child.rename(original)
        child.symlink_to(original)
        moved = directory
    real_read = os.read
    read_count = []

    def counted_read(fd, size):
        read_count.append(True)
        return real_read(fd, size)

    monkeypatch.setattr(vault_module.os, "read", counted_read)
    with pytest.raises(SecretStoreError):
        store.get_secret("p")
    # A key can be read before encountering a bad ciphertext, but never the unsafe target.
    if target in {"directory", "ancestor", "master.key", "vault.lock"}:
        assert read_count == []
    for name, digest in expected.items():
        path = moved / name
        if path.is_symlink():
            path = moved / (name + ".original")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("kind", ["hardlink", "fifo", "directory"])
@pytest.mark.parametrize("name", ["master.key", "vault.fernet", "vault.lock"])
def test_nonregular_or_multilink_files_rejected_without_blocking(
    tmp_path: Path, name: str, kind: str
) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    path = directory / name
    if kind == "hardlink":
        os.link(path, tmp_path / "linked-file")
    else:
        path.unlink()
        if kind == "fifo":
            os.mkfifo(path, 0o600)
        else:
            path.mkdir(mode=0o700)
    started = time.monotonic()
    with pytest.raises(SecretStoreError):
        store.get_secret("p")
    assert time.monotonic() - started < 1


def test_owner_mismatch_simulated_at_fstat_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit simulation only; this test does not change OS ownership."""
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    inode = (directory / "master.key").stat().st_ino
    real_fstat = os.fstat

    def mismatched(fd):
        value = real_fstat(fd)
        if value.st_ino == inode:
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_uid=os.geteuid() + 1,
                st_nlink=value.st_nlink,
                st_size=value.st_size,
            )
        return value

    monkeypatch.setattr(vault_module.os, "fstat", mismatched)
    with pytest.raises(SecretStoreError):
        store.get_secret("p")


def test_unsafe_parent_and_incomplete_initialization(tmp_path: Path) -> None:
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o777)
    parent.chmod(0o777)
    with pytest.raises(SecretStoreError):
        EncryptedFileSecretStore(parent / "vault").set_secret("p", FIXTURE_VALUE)
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir(mode=0o700)
    key = incomplete / "master.key"
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    original = key.read_bytes()
    with pytest.raises(SecretStoreError):
        EncryptedFileSecretStore(incomplete).set_secret("p", FIXTURE_VALUE)
    assert key.read_bytes() == original
    assert not (incomplete / "vault.fernet").exists()


def test_pre_replace_failure_keeps_old_ciphertext_and_cleans_own_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    original = (directory / "vault.fernet").read_bytes()
    unrelated = directory / ".vault-unrelated.tmp"
    unrelated.write_bytes(b"r489-unrelated-encrypted-placeholder")
    unrelated.chmod(0o600)
    observations = []

    def fail_replace(*args, **kwargs):
        temps = [p for p in directory.glob(".vault-*.tmp") if p != unrelated]
        observations.append(
            (
                len(temps),
                all(
                    b"r489-rotated-fixture" not in p.read_bytes()
                    and stat.S_IMODE(p.stat().st_mode) == 0o600
                    for p in temps
                ),
            )
        )
        raise OSError("r489-error-must-never-escape")

    with monkeypatch.context() as patch:
        patch.setattr(vault_module.os, "replace", fail_replace)
        with pytest.raises(SecretStoreError, match="^model_secret_store_unavailable$"):
            store.set_secret("p", "r489-rotated-fixture")
    assert observations == [(1, True)]
    assert (directory / "vault.fernet").read_bytes() == original
    assert list(directory.glob(".vault-*.tmp")) == [unrelated]
    assert store.get_secret("p") == FIXTURE_VALUE
    store.set_secret("other", "r489-lock-released")


@pytest.mark.parametrize("directory_failure", [False, True])
def test_fsync_failure_reports_uncertain_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory_failure: bool
) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    original = (directory / "vault.fernet").read_bytes()
    real_fsync = os.fsync

    def failing(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) == directory_failure:
            raise OSError("r489-fsync-fault")
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(vault_module.os, "fsync", failing)
        with pytest.raises(SecretStoreError):
            store.set_secret("p", "r489-new-value")
    if directory_failure:
        assert store.get_secret("p") == "r489-new-value"
    else:
        assert (directory / "vault.fernet").read_bytes() == original
        assert store.get_secret("p") == FIXTURE_VALUE
    assert not list(directory.glob(".vault-*.tmp"))


def test_lock_timeout_and_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "vault"
    store = EncryptedFileSecretStore(directory)
    store.set_secret("p", FIXTURE_VALUE)
    monkeypatch.setattr(vault_module, "LOCK_TIMEOUT_SECONDS", 0.05)
    with (directory / "vault.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(SecretStoreError):
            store.get_secret("p")
        fcntl.flock(lock, fcntl.LOCK_UN)
    assert store.get_secret("p") == FIXTURE_VALUE


def test_oversize_mutation_preserves_valid_vault(tmp_path: Path) -> None:
    store = EncryptedFileSecretStore(tmp_path / "vault")
    store.set_secret("p", FIXTURE_VALUE)
    with pytest.raises(SecretStoreError):
        store.set_secret("p", "x" * (4 * 1024 * 1024))
    assert store.get_secret("p") == FIXTURE_VALUE


def test_failed_secret_deletion_preserves_profile_metadata(tmp_path: Path) -> None:
    class FailingDeleteStore(InMemorySecretStore):
        def delete_secret(self, profile_id: str) -> None:
            raise SecretStoreError()

    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "metadata.db"),
        secret_store=FailingDeleteStore(),
    )
    profile = service.create_profile(
        display_name="profile",
        provider_kind=PlannerProviderKind.MOCK,
        model_name="mock",
        api_key=FIXTURE_VALUE,
    )
    with pytest.raises(SecretStoreError):
        service.delete_profile(profile.profile_id)
    assert service.get_profile(profile.profile_id).secret_present


WORKER_SCRIPT = """
import hashlib, json, os, sys
from pathlib import Path
from cloud_edge_robot_arm.model_control.encrypted_secret_store import EncryptedFileSecretStore
directory, worker, mode, barrier = sys.argv[1:]
os.read(int(barrier), 1)
os.close(int(barrier))
store = EncryptedFileSecretStore(Path(directory))
if mode == "write":
    for i in range(10): store.set_secret(f"worker-{worker}-{i}",f"r489-worker-fixture-{worker}-{i}")
elif mode == "rotate": store.set_secret("worker-0-0","r489-rotated-worker-fixture")
elif mode == "delete": store.delete_secret("worker-1-0")
print(json.dumps({"master_digest":hashlib.sha256((Path(directory)/"master.key").read_bytes()).hexdigest()}))
"""


def _workers(directory: Path, jobs: list[tuple[str, str]]) -> list[dict]:
    read_fd, write_fd = os.pipe()
    processes = []
    try:
        for worker, mode in jobs:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        WORKER_SCRIPT,
                        str(directory),
                        worker,
                        mode,
                        str(read_fd),
                    ],
                    pass_fds=(read_fd,),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        os.close(read_fd)
        read_fd = -1
        os.write(write_fd, b"s" * len(processes))
        os.close(write_fd)
        write_fd = -1
        deadline = time.monotonic() + 30
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=max(0.1, deadline - time.monotonic()))
            assert process.returncode == 0
            assert stderr == ""
            results.append(json.loads(stdout))
        return results
    finally:
        for fd in (read_fd, write_fd):
            if fd >= 0:
                os.close(fd)
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


def test_fresh_process_concurrent_initialization_updates_rotation_and_delete(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "vault"
    results = _workers(directory, [(str(i), "write") for i in range(4)])
    assert len({item["master_digest"] for item in results}) == 1
    store = EncryptedFileSecretStore(directory)
    for worker in range(4):
        for i in range(10):
            assert store.get_secret(f"worker-{worker}-{i}") == f"r489-worker-fixture-{worker}-{i}"
    _workers(directory, [("0", "rotate"), ("1", "delete")])
    assert store.get_secret("worker-0-0") == "r489-rotated-worker-fixture"
    assert not store.has_secret("worker-1-0")
    for worker in range(2, 4):
        for i in range(10):
            assert store.has_secret(f"worker-{worker}-{i}")
