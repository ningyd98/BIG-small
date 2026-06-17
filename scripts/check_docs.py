#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "artifacts",
    "ros2_ws/build",
    "ros2_ws/install",
    "ros2_ws/log",
}
MARKDOWN_ROOTS = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "docs", "scripts")
SCRIPT_REF_RE = re.compile(r"(?<![\w/])(scripts/[A-Za-z0-9_./-]+)")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_HOME_RE = re.compile(r"/home/[A-Za-z0-9._-]+/")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SENSITIVE_TOKEN_RE = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._-]+|api[_-]?key\s*[:=]\s*[^`\s]+|password\s*[:=]\s*[^`\s]+)"
)


@dataclass(frozen=True)
class DocCheckFailure:
    check_id: str
    path: str
    detail: str


@dataclass(frozen=True)
class DocCheckResult:
    ok: bool
    failures: list[DocCheckFailure]

    def to_json(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "failures": [failure.__dict__ for failure in self.failures],
        }


def check_repository_docs(root: Path) -> DocCheckResult:
    root = root.resolve()
    failures: list[DocCheckFailure] = []
    markdown_files = list(_iter_markdown_files(root))
    for path in markdown_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        failures.extend(_check_markdown_links(root, path, text))
        failures.extend(_check_script_refs(root, path, text))
        failures.extend(_check_mermaid_fences(path, text))
        failures.extend(_check_sensitive_content(path, text))
    return DocCheckResult(ok=not failures, failures=failures)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository documentation consistency.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check_repository_docs(args.root)
    if args.json:
        print(json.dumps(result.to_json(), sort_keys=True, indent=2))
    else:
        if result.ok:
            print("documentation checks passed")
        else:
            for failure in result.failures:
                print(f"{failure.check_id}: {failure.path}: {failure.detail}")
    return 0 if result.ok else 1


def _iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in MARKDOWN_ROOTS:
        path = root / base
        if path.is_file() and path.suffix == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(child for child in path.rglob("*.md") if not _ignored(child, root)))
    return sorted(set(files))


def _check_markdown_links(root: Path, path: Path, text: str) -> list[DocCheckFailure]:
    failures: list[DocCheckFailure] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or _is_external_link(target):
            continue
        resolved = (root / target[1:]) if target.startswith("/") else (path.parent / target)
        if not resolved.exists():
            failures.append(
                DocCheckFailure(
                    "markdown_link_exists",
                    _relative(path, root),
                    f"missing target {target}",
                )
            )
    return failures


def _check_script_refs(root: Path, path: Path, text: str) -> list[DocCheckFailure]:
    failures: list[DocCheckFailure] = []
    for match in SCRIPT_REF_RE.finditer(text):
        target = match.group(1).rstrip("`.,)")
        if target.endswith("_"):
            continue
        if not (root / target).exists():
            failures.append(
                DocCheckFailure(
                    "script_reference_exists",
                    _relative(path, root),
                    f"missing script {target}",
                )
            )
    return failures


def _check_mermaid_fences(path: Path, text: str) -> list[DocCheckFailure]:
    failures: list[DocCheckFailure] = []
    in_mermaid = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "```mermaid":
            if in_mermaid:
                failures.append(DocCheckFailure("mermaid_fence_closed", str(path), "nested fence"))
            in_mermaid = True
        elif stripped == "```" and in_mermaid:
            in_mermaid = False
    if in_mermaid:
        failures.append(DocCheckFailure("mermaid_fence_closed", str(path), "unclosed fence"))
    return failures


def _check_sensitive_content(path: Path, text: str) -> list[DocCheckFailure]:
    failures: list[DocCheckFailure] = []
    for regex, check_id in (
        (ABSOLUTE_HOME_RE, "sensitive_content"),
        (SENSITIVE_TOKEN_RE, "sensitive_content"),
    ):
        if regex.search(text):
            failures.append(DocCheckFailure(check_id, str(path), "sensitive value pattern"))
    for match in IPV4_RE.finditer(text):
        ip = match.group(0)
        previous = text[match.start() - 1] if match.start() > 0 else ""
        if previous == "-":
            continue
        if ip not in {"0.0.0.0", "127.0.0.1", "127.0.1.1"}:
            failures.append(DocCheckFailure("sensitive_content", str(path), f"literal IP {ip}"))
    return failures


def _is_external_link(target: str) -> bool:
    return "://" in target or target.startswith("mailto:")


def _ignored(path: Path, root: Path) -> bool:
    rel = _relative(path, root)
    return any(rel == ignored or rel.startswith(f"{ignored}/") for ignored in IGNORED_DIRS)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
