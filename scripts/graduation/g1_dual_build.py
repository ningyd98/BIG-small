"""Build and byte-verify the isolated two-arm G1 development runtime."""

from __future__ import annotations

import argparse
import io
import subprocess
import tarfile
from pathlib import Path

from scripts.graduation import g1_mount_runtime_build as previous
from scripts.graduation.perception_io import read, sha, write

BASE = "3cc65630133bba0315907965b224e086c97950a4"
PLAN_SHA = "85666eed1724a2c2280690de8ec55d35fe79b3d636982e35dd366d48e6534885"
OLD_RUNNER = "scripts/graduation/g1_mount_trials.py"
OLD_RUNNER_SHA = "45fd1ffc567c546a8bfe909acf0f4679886b9ca9601dc95c018c12346224addf"
EXPORT = (
    *previous.EXPORT,
    *previous.ADDITIONS,
    "scripts/graduation/g1_mount_score.py",
    "scripts/graduation/g1_mount_score_blind.py",
)
ADDITIONS = tuple(
    f"scripts/graduation/g1_dual_{suffix}.py"
    for suffix in ("asset", "observer", "runtime_adapter", "build", "probe", "trials")
)
LOCK = "runtime-build.json"


def adapt_readback_and_launcher(source):
    """Bind the G1 launcher and its SQL source check to the current development allocation."""
    if previous.sha_bytes(source) != OLD_RUNNER_SHA:
        raise ValueError("unexpected historical G1 launcher SHA256")
    before = b"def capture(plan_file, raw, h, case_id):\n"
    after = (
        b"def capture(plan_file, raw, h, case_id, *, context=check_batch, "
        b"case_reader=load_case, episode_factory=TranslatedEpisode):\n"
    )
    split = source.index(before)
    end = source.index(b"\ndef audit_all(", split)
    capture = source[split:end]
    for old, new in (
        (before, after),
        (b"= check_batch(plan_file, raw, h)", b"= context(plan_file, raw, h)"),
        (b"= load_case(raw, batch, row)", b"= case_reader(raw, batch, row)"),
        (
            b'= TranslatedEpisode(directory, alloc, row["allocation_sha256"], catalog)',
            b'= episode_factory(directory, alloc, row["allocation_sha256"], catalog)',
        ),
    ):
        if capture.count(old) != 1:
            raise ValueError("ambiguous G1 trial launcher binding")
        capture = capture.replace(old, new)
    data = source[:split] + capture + source[end:]
    old = b'!= (builder.BASE, alloc["component_catalog_sha256"])'
    if data.count(old) != 1:
        raise ValueError("ambiguous worker SQL evidence binding")
    return data.replace(old, b'!= (alloc["baseline"], alloc["component_catalog_sha256"])')


def export_base(repository, destination):
    """Export tracked bytes only, retaining the previously approved per-family servo binding."""
    destination.mkdir()
    data = subprocess.check_output(
        ["git", "archive", "--format=tar", BASE, *EXPORT], cwd=repository
    )
    original, effective = {}, {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for entry in archive:
            if entry.isdir():
                continue
            name = entry.name
            if not entry.isfile() or Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unexpected Git archive path")
            content = archive.extractfile(entry).read()
            original[name] = previous.sha_bytes(content)
            if name == previous.VISION:
                content = previous.configure_vision(content)
            if name == OLD_RUNNER:
                content = adapt_readback_and_launcher(content)
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            effective[name] = previous.sha_bytes(content)
    return original, effective


def build(repository, destination, *, assembly="v1"):
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_dual_runtime_adapter as adapter

    if assembly not in {"v1", "v2"}:
        raise ValueError("unknown physical development assembly")
    additions = list(ADDITIONS)
    if assembly == "v2":
        from scripts.graduation import g1_dual_asset_v2 as bracket

        additions.append("scripts/graduation/g1_dual_asset_v2.py")
    original, effective = export_base(repository, destination)
    for name, digest in adapter.SOURCE_SHA256.items():
        path = destination / name
        if original.get(name) != digest or sha(path) != digest:
            raise ValueError("unregistered development overlay input: " + name)
        path.write_bytes(adapter.adapt_source(name, path.read_bytes()))
        effective[name] = sha(path)
    for name in additions:
        if name in original:
            raise ValueError("development entry collides with Git baseline")
        path = destination / name
        with path.open("xb") as stream:
            stream.write((repository / name).read_bytes())
        effective[name] = sha(path)
    scene = destination / asset.ASSET_PATH
    with scene.open("xb") as stream:
        stream.write(asset.build_xml((destination / asset.BASE_ASSET_PATH).read_bytes()))
    effective[asset.ASSET_PATH] = sha(scene)
    additions.append(asset.ASSET_PATH)
    provider_name = "scripts/graduation/g1_dual_asset.py"
    provider_original = effective[provider_name]
    if assembly == "v2":
        path = destination / provider_name
        path.write_bytes(bracket.provider_source(path.read_bytes()))
        effective[provider_name] = sha(path)
        with (destination / bracket.ASSET_PATH).open("xb") as stream:
            stream.write(bracket.replace_v1_xml(scene.read_bytes()))
        effective[bracket.ASSET_PATH] = sha(destination / bracket.ASSET_PATH)
        additions.append(bracket.ASSET_PATH)
    changed = sorted(k for k, h in original.items() if effective[k] != h)
    if set(changed) != {previous.VISION, OLD_RUNNER, *adapter.SOURCE_SHA256}:
        raise ValueError("unexpected runtime differences against exact Git base")
    write(
        destination / LOCK,
        dict(
            schema="g1.development.dual-marker.runtime.v1",
            baseline=BASE,
            plan_sha256=PLAN_SHA,
            baseline_files_sha256=original,
            runtime_files_sha256=effective,
            source_changes=changed,
            original_servo_binding_sha256=previous.sha_bytes(
                previous.configure_vision((repository / previous.VISION).read_bytes())
            ),
            additions=additions,
            development_assembly=assembly,
            asset_provider_source={
                "path": provider_name,
                "original_sha256": provider_original,
                "effective_sha256": effective[provider_name],
            },
            development_only=True,
            exported_pathspecs=list(EXPORT),
        ),
    )
    return load_lock(destination)


def load_lock(root, expected=None):
    if expected is not None and sha(root / LOCK) != expected:
        raise ValueError("runtime build SHA256 mismatch")
    lock = read(root / LOCK)
    paths = [p for p in root.rglob("*") if "__pycache__" not in p.parts]
    if any(p.is_symlink() for p in paths):
        raise ValueError("symlink in development build")
    computed = {
        p.relative_to(root).as_posix(): sha(p) for p in paths if p.is_file() and p != root / LOCK
    }
    if (
        lock["baseline"] != BASE
        or lock["plan_sha256"] != PLAN_SHA
        or lock["baseline_files_sha256"].get(previous.VISION) != previous.ORIGINAL_VISION
        or computed != lock["runtime_files_sha256"]
    ):
        raise ValueError("isolated runtime source or protected binding mismatch")
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("public", type=Path)
    parser.add_argument("--assembly", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[2], args.runtime, assembly=args.assembly)
    with args.public.open("xb") as stream:
        stream.write((args.runtime / LOCK).read_bytes())


if __name__ == "__main__":
    main()
