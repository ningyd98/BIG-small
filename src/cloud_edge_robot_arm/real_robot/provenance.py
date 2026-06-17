from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_from_commit: str
    source_tree_hash: str
    worktree_clean: bool
    diff_hash: str
    verifier_version: str
    command: list[str]
    config_hash: str
    environment_hash: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def current_source_provenance(
    *,
    command: list[str],
    config_hash: str = "",
    verifier_version: str,
    environment: dict[str, Any] | None = None,
) -> EvidenceProvenance:
    diff_text = _source_diff_text()
    return EvidenceProvenance(
        generated_from_commit=_git(["rev-parse", "HEAD"]).strip() or "UNKNOWN",
        source_tree_hash=current_source_tree_hash(),
        worktree_clean=not bool(diff_text.strip()),
        diff_hash=_sha256_text(diff_text),
        verifier_version=verifier_version,
        command=list(command),
        config_hash=config_hash,
        environment_hash=_sha256_json(environment or {}),
    )


def provenance_matches_current_source(provenance: EvidenceProvenance) -> bool:
    return provenance.source_tree_hash == current_source_tree_hash()


def current_source_tree_hash() -> str:
    files = [
        path
        for path in _git(["ls-files", "--cached", "--others", "--exclude-standard"]).splitlines()
        if _is_source_path(path)
    ]
    digest = hashlib.sha256()
    for path_text in sorted(files):
        path = Path(path_text)
        digest.update(path_text.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _source_diff_text() -> str:
    status = _git(["status", "--porcelain", "--untracked-files=all"])
    source_status = "\n".join(
        line for line in status.splitlines() if _is_source_path(line[3:] if len(line) > 3 else "")
    )
    tracked_diff = _git(["diff", "--", ":!artifacts/**"])
    return "\n".join(part for part in (tracked_diff, source_status) if part.strip())


def _is_source_path(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if path_text.startswith("artifacts/"):
        return False
    if path.name.endswith(".pyc"):
        return False
    if "__pycache__" in path.parts:
        return False
    return True
