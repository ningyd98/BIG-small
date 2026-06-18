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


@dataclass(frozen=True)
class CommentAuditResult:
    path: Path
    has_chinese: bool


def main() -> int:
    parser = argparse.ArgumentParser(description="检查重点代码文件是否包含中文说明。")
    parser.add_argument(
        "paths",
        nargs="*",
        default=[
            "src/cloud_edge_robot_arm",
            "dashboard/src",
            "dashboard/tests",
            "dashboard/playwright.config.ts",
            "dashboard/vite.config.ts",
            "scripts/verify_phase11_1_simulation_runtime.py",
            "tests/test_phase11_1_simulation_runtime.py",
        ],
        help="需要审计的文件或目录。",
    )
    args = parser.parse_args()

    files = _collect_files([Path(value) for value in args.paths])
    results = [_audit_file(path) for path in files]
    missing = [result.path for result in results if not result.has_chinese]

    for result in results:
        status = "OK" if result.has_chinese else "MISSING"
        print(f"{status} {result.path}")

    if missing:
        print("\n缺少中文说明的文件：")
        for path in missing:
            print(f"- {path}")
        return 1
    return 0


def _collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.suffix in {".py", ".ts", ".tsx"} and not child.name.endswith(".d.ts")
            )
        elif path.suffix in {".py", ".ts", ".tsx"}:
            files.append(path)
    return sorted(files)


def _audit_file(path: Path) -> CommentAuditResult:
    text = path.read_text(encoding="utf-8")
    comment_text = _extract_explanation_text(path, text)
    return CommentAuditResult(path=path, has_chinese=_has_chinese(comment_text))


def _extract_explanation_text(path: Path, text: str) -> str:
    if path.suffix == ".py":
        return _extract_python_explanation_text(text)
    if path.suffix in {".ts", ".tsx"}:
        return _extract_typescript_comment_text(text)
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


def _extract_typescript_comment_text(text: str) -> str:
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
    return any(HAN_RANGE[0] <= char <= HAN_RANGE[1] for char in text)


if __name__ == "__main__":
    raise SystemExit(main())
