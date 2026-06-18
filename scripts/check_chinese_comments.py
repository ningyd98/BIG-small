"""中文注释覆盖审计工具。

该脚本只做底线检查：重点代码文件必须至少包含中文说明。是否“合适”仍需要人工
结合业务、安全和并发语义判断。
"""

from __future__ import annotations

import argparse
import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

HAN_RANGE = ("\u4e00", "\u9fff")
CODE_SUFFIXES = {
    ".action",
    ".bash",
    ".css",
    ".html",
    ".js",
    ".msg",
    ".py",
    ".sh",
    ".srv",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}
HASH_COMMENT_SUFFIXES = {".action", ".bash", ".msg", ".sh", ".srv", ".toml", ".yaml", ".yml"}
SLASH_COMMENT_SUFFIXES = {".css", ".js", ".ts", ".tsx"}
XML_COMMENT_SUFFIXES = {".html", ".xml"}
HASH_COMMENT_FILENAMES = {".gitignore", ".env.example", ".env.phase9.example"}
PLACEHOLDER_EXPLANATION_MARKERS = (
    "补充该层业务逻辑的中文说明",
    "文件说明：补充中文说明",
    "测试说明：覆盖该阶段关键业务约束",
)


@dataclass(frozen=True)
class CommentAuditResult:
    path: Path
    has_chinese: bool
    explanation_comment_count: int


def main() -> int:
    parser = argparse.ArgumentParser(description="检查重点代码文件是否包含中文说明。")
    parser.add_argument(
        "paths",
        nargs="*",
        default=[
            "src",
            "dashboard/src",
            "dashboard/tests",
            "dashboard/playwright.config.ts",
            "dashboard/vite.config.ts",
            ".env.example",
            ".env.phase9.example",
            ".github/workflows",
            ".gitignore",
            "pyproject.toml",
            "scripts",
            "tests",
            "ros2_ws/src",
        ],
        help="需要审计的文件或目录。",
    )
    args = parser.parse_args()

    files = _collect_files([Path(value) for value in args.paths])
    results = [_audit_file(path) for path in files]
    missing = [result.path for result in results if not result.has_chinese]
    english_only = [
        result.path
        for result in results
        if not result.has_chinese and result.explanation_comment_count > 0
    ]

    for result in results:
        status = "OK" if result.has_chinese else "MISSING"
        print(f"{status} {result.path}")

    if missing:
        print("\n缺少中文说明的文件：")
        for path in missing:
            print(f"- {path}")
        if english_only:
            print("\n只有非中文说明的文件：")
            for path in english_only:
                print(f"- {path}")
        return 1
    print(f"\n中文说明审计通过：files={len(results)} english_only=0 missing=0")
    return 0


def _collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(child for child in path.rglob("*") if _is_audited_file(child))
        elif _is_audited_file(path):
            files.append(path)
    return sorted(files)


def _audit_file(path: Path) -> CommentAuditResult:
    text = path.read_text(encoding="utf-8")
    explanation_fragments = _extract_explanation_fragments(path, text)
    comment_text = "\n".join(explanation_fragments)
    return CommentAuditResult(
        path=path,
        has_chinese=_has_chinese(comment_text),
        explanation_comment_count=len(explanation_fragments),
    )


def _extract_explanation_fragments(path: Path, text: str) -> list[str]:
    comment_text = _extract_explanation_text(path, text)
    return [fragment for fragment in comment_text.splitlines() if fragment.strip()]


def _extract_explanation_text(path: Path, text: str) -> str:
    if path.suffix == ".py" or _has_python_shebang(path):
        return _extract_python_explanation_text(text)
    if path.suffix in SLASH_COMMENT_SUFFIXES:
        return _extract_leading_slash_comment_text(text)
    if path.suffix in HASH_COMMENT_SUFFIXES or path.name in HASH_COMMENT_FILENAMES:
        return _extract_hash_comment_text(text)
    if path.suffix in XML_COMMENT_SUFFIXES:
        return _extract_xml_comment_text(text)
    return ""


def _extract_python_explanation_text(text: str) -> str:
    fragments: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None

    if tree is not None:
        # Python 文件里的模块、类和函数 docstring 承担正式说明职责，普通字符串不计入。
        module_docstring = ast.get_docstring(tree, clean=False)
        if module_docstring:
            fragments.append(module_docstring)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                docstring = ast.get_docstring(node, clean=False)
                if docstring:
                    fragments.append(docstring)

    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        fragments.extend(token.string for token in tokens if token.type == tokenize.COMMENT)
    except tokenize.TokenError:
        pass

    return "\n".join(fragments)


def _extract_leading_slash_comment_text(text: str) -> str:
    # 前端文件必须在文件入口说明职责，避免只靠组件内部中文文案通过审计。
    comments: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in {" ", "\t", "\r", "\n"}:
            index += 1
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end == -1:
                comments.append(text[index:])
                break
            comments.append(text[index:end])
            index = end + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                comments.append(text[index:])
                break
            comments.append(text[index : end + 2])
            index = end + 2
            continue
        break
    return "\n".join(comments)


def _extract_slash_comment_text(text: str) -> str:
    comments: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""
        if char in {"'", '"', "`"}:
            index = _skip_javascript_string(text, index, char)
            continue
        if char == "/" and next_char == "/":
            end = text.find("\n", index + 2)
            if end == -1:
                end = length
            comments.append(text[index:end])
            index = end
            continue
        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            if end == -1:
                comments.append(text[index:])
                break
            comments.append(text[index : end + 2])
            index = end + 2
            continue
        index += 1
    return "\n".join(comments)


def _extract_hash_comment_text(text: str) -> str:
    comments: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            comments.append(stripped)
    return "\n".join(comments)


def _extract_xml_comment_text(text: str) -> str:
    comments: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("<!--", index)
        if start == -1:
            break
        end = text.find("-->", start + 4)
        if end == -1:
            comments.append(text[start:])
            break
        comments.append(text[start : end + 3])
        index = end + 3
    return "\n".join(comments)


def _skip_javascript_string(text: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return len(text)


def _has_chinese(text: str) -> bool:
    # 占位式中文不解释模块边界或安全语义，不能作为“合适说明”的证据。
    if any(marker in text for marker in PLACEHOLDER_EXPLANATION_MARKERS):
        return False
    return any(HAN_RANGE[0] <= char <= HAN_RANGE[1] for char in text)


def _is_audited_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return (
        path.suffix in CODE_SUFFIXES
        or path.name in HASH_COMMENT_FILENAMES
        or _has_python_shebang(path)
    ) and not path.name.endswith(".d.ts")


def _has_python_shebang(path: Path) -> bool:
    if path.suffix:
        return False
    try:
        with path.open("r", encoding="utf-8") as file:
            first_line = file.readline(128)
    except (OSError, UnicodeDecodeError):
        return False
    return first_line.startswith("#!") and "python" in first_line.lower()


if __name__ == "__main__":
    raise SystemExit(main())
