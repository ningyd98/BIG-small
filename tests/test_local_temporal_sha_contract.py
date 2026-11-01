"""R367 contract: `_sha` accepts exactly the 64-char lowercase ASCII hex set.

The matrix is fixed and implementation-agnostic: it asserts only the returned
object identity for valid inputs and the exact ValueError message otherwise.
No timing, regex-shape or private-helper assertion is made here.
"""
from __future__ import annotations

import pytest

from cloud_edge_robot_arm.vision.local_temporal import _sha

_ZERO = "0" * 64
_MIXED = "0123456789abcdef" * 4
_F = "f" * 64


class _StrSubclass(str):
    pass


def _replace(index: int, char: str) -> str:
    return _ZERO[:index] + char + _ZERO[index + 1:]


CASES: tuple[tuple[str, object, str], ...] = (
    # valid: same object returned, no trimming
    ("valid_zero", _ZERO, "valid"),
    ("valid_mixed", _MIXED, "valid"),
    ("valid_f", _F, "valid"),
    # length / alphabet
    ("length_63", _ZERO[:63], "sha"),
    ("length_65", _ZERO + "0", "sha"),
    ("uppercase", _replace(63, "A"), "sha"),
    ("nonhex_g", _replace(63, "g"), "sha"),
    # whitespace around / inside
    ("leading_space", " " + _ZERO, "sha"),
    ("trailing_space", _ZERO + " ", "sha"),
    ("embedded_space", _replace(32, " "), "sha"),
    ("trailing_lf", _ZERO + "\n", "sha"),
    ("trailing_crlf", _ZERO + "\r\n", "sha"),
    ("embedded_lf", _replace(32, "\n"), "sha"),
    ("nul", _replace(32, "\x00"), "sha"),
    # non-ASCII lookalikes
    ("fullwidth", _replace(32, "\uff10"), "sha"),
    ("unicode_digit", _replace(32, "\u0661"), "sha"),
    ("lone_surrogate", _replace(32, "\ud800"), "sha"),
    # blank / non-str: rejected by the text guard before the alphabet check
    ("empty", "", "text"),
    ("spaces", " " * 64, "text"),
    ("tabs_newlines", "\t\n" * 32, "text"),
    ("unicode_space", "\u2003" * 64, "text"),
    ("none", None, "text"),
    ("bool", True, "text"),
    ("int", 7, "text"),
    ("float", 1.5, "text"),
    ("bytes", b"0" * 64, "text"),
    ("list", [_ZERO], "text"),
    ("dict", {"sha": _ZERO}, "text"),
    ("str_subclass_valid", _StrSubclass(_ZERO), "text"),
    ("str_subclass_empty", _StrSubclass(""), "text"),
    ("object", object(), "text"),
)

_MESSAGES = {"valid": None, "sha": "SHA256 required", "text": "nonempty text required"}


@pytest.mark.parametrize("value,kind", [(value, kind) for _, value, kind in CASES],
                         ids=[name for name, _, _ in CASES])
def test_sha_contract(value: object, kind: str) -> None:
    if kind == "valid":
        result = _sha(value)  # type: ignore[arg-type]
        assert result is value
        assert result == value
        return
    with pytest.raises(ValueError) as raised:
        _sha(value)  # type: ignore[arg-type]
    assert str(raised.value) == _MESSAGES[kind]
