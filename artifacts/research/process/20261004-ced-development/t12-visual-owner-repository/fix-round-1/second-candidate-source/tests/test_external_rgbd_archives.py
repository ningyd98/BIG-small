"""使用 synthetic_fixture 归档检查完整分卷和原子发布。"""

from __future__ import annotations

import importlib
import io
import json
import tarfile

import pytest


def archives():
    try:
        return importlib.import_module("cloud_edge_robot_arm.datasets.external.archives")
    except ModuleNotFoundError:
        pytest.fail("外部 RGB-D 安全解压尚未实现")


def make_tar(tmp_path, names=("scene_0001/rgb/a.png", "scene_0002/depth/a.png")):
    path = tmp_path / "synthetic_fixture.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 3
            archive.addfile(info, io.BytesIO(b"rgb"))
    return path


def test_tar_selection_is_atomic_and_marker_binds_hashes_and_members(tmp_path):
    mod = archives()
    archive = make_tar(tmp_path)
    destination = tmp_path / "raw"
    result = mod.extract_archive(
        [archive],
        destination,
        selected_members=["scene_0001/"],
        max_expanded_bytes=10,
        minimum_free_bytes=0,
    )
    assert result["status"] == "COMPLETE"
    assert (destination / "scene_0001/rgb/a.png").read_bytes() == b"rgb"
    assert not (destination / "scene_0002").exists()
    marker = json.loads((destination / ".extraction-complete.json").read_text())
    assert marker["archive_hashes"][0]["sha256"]
    assert marker["selected_members"] == ["scene_0001/"]
    second = mod.extract_archive(
        [archive],
        destination,
        selected_members=["scene_0001/"],
        minimum_free_bytes=0,
    )
    assert second["status"] == "REUSED"


@pytest.mark.parametrize(
    "name", ["../escape", "/escape", "C:/escape", "safe/../../escape", "x\\escape"]
)
def test_path_traversal_is_rejected_before_any_public_output(tmp_path, name):
    path = make_tar(tmp_path, names=(name,))
    destination = tmp_path / "raw"
    with pytest.raises(ValueError, match="path"):
        archives().extract_archive([path], destination, minimum_free_bytes=0)
    assert not destination.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE]
)
def test_links_and_special_archive_members_are_rejected(tmp_path, kind):
    path = tmp_path / "synthetic_fixture.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("scene/link")
        info.type = kind
        info.linkname = "../../escape"
        archive.addfile(info)
    with pytest.raises(ValueError, match="link|special"):
        archives().inspect_archive([path])


def test_listing_reports_real_expansion_and_rejects_expansion_cap(tmp_path):
    path = make_tar(tmp_path)
    info = archives().inspect_archive([path])
    assert info["uncompressed_bytes"] == 6
    assert info["integrity_status"] == "TESTED"
    with pytest.raises(RuntimeError, match="EXPANSION"):
        archives().extract_archive(
            [path], tmp_path / "raw", max_expanded_bytes=5, minimum_free_bytes=0
        )


def test_missing_or_unordered_numeric_parts_are_rejected(tmp_path):
    first = tmp_path / "scenes.7z.001"
    third = tmp_path / "scenes.7z.003"
    first.write_bytes(b"part")
    third.write_bytes(b"part")
    for paths in ([first, third], [third, first]):
        with pytest.raises(ValueError, match="part|order"):
            archives().inspect_archive(paths)


def test_missing_split_tar_part_is_not_deployed(tmp_path):
    first = tmp_path / "franka.tar.gz.partaa"
    third = tmp_path / "franka.tar.gz.partac"
    first.write_bytes(b"part")
    third.write_bytes(b"part")
    with pytest.raises(ValueError, match="part"):
        archives().inspect_archive([first, third])


def test_split_tar_stream_is_read_without_joined_archive_copy(tmp_path):
    mod = archives()
    archive = make_tar(tmp_path)
    body = archive.read_bytes()
    archive.unlink()
    first = tmp_path / "franka.tar.gz.partaa"
    second = tmp_path / "franka.tar.gz.partab"
    first.write_bytes(body[: len(body) // 2])
    second.write_bytes(body[len(body) // 2 :])
    destination = tmp_path / "raw"
    result = mod.extract_archive([first, second], destination, minimum_free_bytes=0)
    assert result["status"] == "COMPLETE"
    assert result["expanded_bytes"] == 6
    assert not (tmp_path / "franka.tar.gz").exists()


def test_multivolume_7z_selected_members_are_tested_and_extracted(tmp_path):
    import multivolumefile
    import py7zr

    mod = archives()
    source = tmp_path / "synthetic_fixture.bin"
    source.write_bytes(b"rgbd" * 100)
    base = tmp_path / "scenes.7z"
    with multivolumefile.open(base, "wb", volume=80) as stream:
        with py7zr.SevenZipFile(stream, "w") as archive:
            archive.write(source, "scene_0001/rgb/a.png")
            archive.write(source, "scene_0002/rgb/b.png")
    parts = sorted(tmp_path.glob("scenes.7z.*"))
    assert len(parts) >= 2
    result = mod.extract_archive(
        parts,
        tmp_path / "raw",
        selected_members=["scene_0001/"],
        max_expanded_bytes=500,
        minimum_free_bytes=0,
    )
    assert result["expanded_bytes"] == 400
    assert (tmp_path / "raw/scene_0001/rgb/a.png").read_bytes() == source.read_bytes()
    assert not (tmp_path / "raw/scene_0002").exists()


def test_half_extracted_destination_is_never_reused(tmp_path):
    path = make_tar(tmp_path)
    destination = tmp_path / "raw"
    destination.mkdir()
    (destination / "partial").write_bytes(b"incomplete")
    with pytest.raises(RuntimeError, match="INCOMPLETE"):
        archives().extract_archive([path], destination, minimum_free_bytes=0)
    assert not (destination / ".extraction-complete.json").exists()


def test_corrupted_published_member_cannot_be_reused(tmp_path):
    mod = archives()
    path = make_tar(tmp_path)
    destination = tmp_path / "raw"
    mod.extract_archive([path], destination, minimum_free_bytes=0)
    (destination / "scene_0001/rgb/a.png").write_bytes(b"bad")
    with pytest.raises(RuntimeError, match="INCOMPLETE|HASH"):
        mod.extract_archive([path], destination, minimum_free_bytes=0)


def test_reserve_gate_prevents_partial_public_destination(tmp_path, monkeypatch):
    mod = archives()
    path = make_tar(tmp_path)
    monkeypatch.setattr(mod, "_free_bytes", lambda _: 10)
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        mod.extract_archive([path], tmp_path / "raw", minimum_free_bytes=10)
    assert not (tmp_path / "raw").exists()


def test_unselected_unsafe_entry_cannot_hide_behind_selection(tmp_path):
    path = make_tar(tmp_path, names=("scene_0001/rgb/a.png", "../escape"))
    with pytest.raises(ValueError, match="path"):
        archives().extract_archive(
            [path], tmp_path / "raw", selected_members=["scene_0001/"], minimum_free_bytes=0
        )


def test_empty_completion_file_manifest_is_not_treated_as_success(tmp_path):
    mod = archives()
    path = make_tar(tmp_path)
    destination = tmp_path / "raw"
    mod.extract_archive([path], destination, minimum_free_bytes=0)
    marker_path = destination / ".extraction-complete.json"
    marker = json.loads(marker_path.read_text())
    marker["files"] = []
    marker_path.write_text(json.dumps(marker))
    with pytest.raises(RuntimeError, match="INCOMPLETE"):
        mod.extract_archive([path], destination, minimum_free_bytes=0)


def test_symlinked_published_parent_is_never_reused(tmp_path):
    mod = archives()
    path = make_tar(tmp_path)
    destination = tmp_path / "raw"
    mod.extract_archive([path], destination, minimum_free_bytes=0)
    original = destination / "scene_0001"
    relocated = tmp_path / "relocated"
    original.rename(relocated)
    original.symlink_to(relocated, target_is_directory=True)
    with pytest.raises(RuntimeError, match="INCOMPLETE"):
        mod.extract_archive([path], destination, minimum_free_bytes=0)


def test_interruption_keeps_failed_stage_without_public_success(tmp_path, monkeypatch):
    mod = archives()
    path = make_tar(tmp_path)

    def interrupted(_archive, _chosen, stage, _guard):
        (stage / "partial").write_bytes(b"rgb")
        raise InterruptedError("synthetic_fixture interruption")

    monkeypatch.setattr(mod, "_extract_tar", interrupted)
    with pytest.raises(InterruptedError):
        mod.extract_archive([path], tmp_path / "raw", minimum_free_bytes=0)
    assert not (tmp_path / "raw").exists()
    stages = list(tmp_path.glob(".raw.extracting-*"))
    assert len(stages) == 1
    assert not (stages[0] / ".extraction-complete.json").exists()
    state = json.loads((stages[0] / ".extraction-state.json").read_text())
    assert state["state"] == "FAILED"


def test_disk_reserve_is_checked_after_listing_before_each_write(tmp_path, monkeypatch):
    mod = archives()
    path = make_tar(tmp_path)
    available = iter([100, 100, 2])
    monkeypatch.setattr(mod, "_free_bytes", lambda _: next(available, 2))
    with pytest.raises(RuntimeError, match="BLOCKED_STORAGE"):
        mod.extract_archive([path], tmp_path / "raw", minimum_free_bytes=1)
    assert not (tmp_path / "raw").exists()


def test_declared_tar_expansion_cap_is_checked_before_skipping_payload(tmp_path):
    path = tmp_path / "synthetic_fixture.tar"
    info = tarfile.TarInfo("huge.bin")
    info.size = 1024**3
    path.write_bytes(info.tobuf() + b"\0" * 1024)
    with pytest.raises(RuntimeError, match="EXPANSION"):
        archives().inspect_archive([path], max_expanded_bytes=1024)


def make_zip(tmp_path, names=("task/success_episodes/one/data/trajectory.hdf5", "extra.bin")):
    import zipfile

    path = tmp_path / "synthetic_fixture.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, b"rgbd")
    return path


def test_zip_complete_crc_and_hash_inspection_then_selected_atomic_publish(tmp_path):
    mod = archives()
    path = make_zip(tmp_path)
    inspected = mod.inspect_archive([path])
    assert inspected["format"] == "zip"
    assert inspected["integrity_status"] == "TESTED"
    assert inspected["uncompressed_bytes"] == 8
    destination = tmp_path / "raw"
    result = mod.extract_archive(
        [path], destination, selected_members=["task/"], minimum_free_bytes=0
    )
    assert result["status"] == "COMPLETE"
    assert result["expanded_bytes"] == 4
    assert result["archive_hashes"] == inspected["archive_hashes"]
    assert (destination / "task/success_episodes/one/data/trajectory.hdf5").read_bytes() == b"rgbd"
    assert not (destination / "extra.bin").exists()
    assert mod.extract_archive(
        [path], destination, selected_members=["task/"], minimum_free_bytes=0
    )["status"] == "REUSED"


@pytest.mark.parametrize("name", ["../escape", "/escape", "C:/escape", "x\\escape"])
def test_zip_unsafe_member_is_rejected_even_when_unselected(tmp_path, name):
    path = make_zip(tmp_path, names=("task/real.hdf5", name))
    with pytest.raises(ValueError, match="path"):
        archives().extract_archive(
            [path], tmp_path / "raw", selected_members=["task/"], minimum_free_bytes=0
        )
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize("kind", [0o120000, 0o020000, 0o010000])
def test_zip_unix_symlink_and_special_members_are_rejected(tmp_path, kind):
    import zipfile

    path = tmp_path / "synthetic_fixture.zip"
    info = zipfile.ZipInfo("task/link")
    info.create_system = 3
    info.external_attr = (kind | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, b"../../escape")
    with pytest.raises(ValueError, match="link|special"):
        archives().inspect_archive([path])


def test_zip_expansion_cap_checks_listing_before_reading_payload(tmp_path):
    path = make_zip(tmp_path)
    with pytest.raises(RuntimeError, match="EXPANSION"):
        archives().inspect_archive([path], max_expanded_bytes=7)


def test_zip_bad_crc_in_unselected_member_is_rejected_before_publication(tmp_path):
    import struct
    import zipfile

    path = tmp_path / "synthetic_fixture.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("task/real.hdf5", b"rgbd")
        archive.writestr("extra.bin", b"rgbd")
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("extra.bin")
    body = bytearray(path.read_bytes())
    offset = info.header_offset
    name_size, extra_size = struct.unpack_from("<HH", body, offset + 26)
    content = offset + 30 + name_size + extra_size
    body[content] ^= 0x40
    path.write_bytes(body)
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        archives().extract_archive(
            [path], tmp_path / "raw", selected_members=["task/"], minimum_free_bytes=0
        )
    assert not (tmp_path / "raw").exists()


def test_zip_interrupted_extraction_never_publishes_completion(tmp_path, monkeypatch):
    mod = archives()
    path = make_zip(tmp_path)

    def interrupted(_archive, _chosen, stage, _guard):
        (stage / "partial").write_bytes(b"rgbd")
        raise InterruptedError("synthetic_fixture ZIP interruption")

    monkeypatch.setattr(mod, "_extract_zip", interrupted, raising=False)
    with pytest.raises(InterruptedError):
        mod.extract_archive([path], tmp_path / "raw", minimum_free_bytes=0)
    assert not (tmp_path / "raw").exists()
    stages = list(tmp_path.glob(".raw.extracting-*"))
    assert len(stages) == 1
    assert not (stages[0] / ".extraction-complete.json").exists()
    assert json.loads((stages[0] / ".extraction-state.json").read_text())["state"] == "FAILED"
