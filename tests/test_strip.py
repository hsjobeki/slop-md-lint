#!/usr/bin/env python3
"""Tests for markdown stripping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slop_md_lint import strip_non_prose


def test_backtick_fence() -> None:
    text = "Before\n```python\nrobust = True\n```\nAfter"
    result = strip_non_prose(text)
    assert "robust" not in result


def test_tilde_fence() -> None:
    text = "Before\n~~~python\nrobust = True\n~~~\nAfter"
    result = strip_non_prose(text)
    assert "robust" not in result


def test_inline_code() -> None:
    text = "Use `robust` in your config."
    result = strip_non_prose(text)
    assert "robust" not in result


def test_frontmatter() -> None:
    text = "---\ntitle: Robust Guide\n---\nActual content"
    result = strip_non_prose(text)
    assert "Robust" not in result
    assert "Actual content" in result


def test_prose_kept() -> None:
    text = "This is robust and seamless prose."
    result = strip_non_prose(text)
    assert "robust" in result
    assert "seamless" in result


if __name__ == "__main__":
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"  PASS  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failures += 1
    print()
    print(f"{len(tests)} tests, {failures} failed")
    sys.exit(1 if failures else 0)
