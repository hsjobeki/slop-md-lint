#!/usr/bin/env python3
"""Tests for slop-md-lint scoring."""

import sys
from pathlib import Path

# Add parent dir so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slop_md_lint import (
    DEFAULT_THRESHOLD,
    Config,
    scan_file,
)

TESTS_DIR = Path(__file__).resolve().parent


# ============================================================================
# Core detection tests (existing fixtures)
# ============================================================================

def test_sloppy_file_is_flagged() -> None:
    result = scan_file(TESTS_DIR / "sloppy.md")
    assert result.normalized_score > DEFAULT_THRESHOLD, (
        f"sloppy.md should be flagged (score={result.normalized_score:.2f}, "
        f"threshold={DEFAULT_THRESHOLD})"
    )
    # Should score well above threshold, not just barely
    assert result.normalized_score > DEFAULT_THRESHOLD * 2, (
        f"sloppy.md should score well above threshold "
        f"(score={result.normalized_score:.2f})"
    )


def test_clean_file_passes() -> None:
    result = scan_file(TESTS_DIR / "clean.md")
    assert result.normalized_score <= DEFAULT_THRESHOLD, (
        f"clean.md should pass (score={result.normalized_score:.2f}, "
        f"threshold={DEFAULT_THRESHOLD})"
    )


def test_small_file_not_scored() -> None:
    result = scan_file(TESTS_DIR / "small.md")
    assert result.normalized_score == 0, (
        f"small.md should not be scored (score={result.normalized_score:.2f}, "
        f"word_count={result.word_count})"
    )


def test_sloppy_has_vocabulary_matches() -> None:
    result = scan_file(TESTS_DIR / "sloppy.md")
    categories = {m.category for m in result.matches}
    assert "vocabulary" in categories, "sloppy.md should have vocabulary matches"
    assert "phrase" in categories, "sloppy.md should have phrase matches"
    assert "formatting" in categories, "sloppy.md should have formatting matches"


def test_clean_has_no_vocabulary_matches() -> None:
    result = scan_file(TESTS_DIR / "clean.md")
    vocab_matches = [m for m in result.matches if m.category == "vocabulary"]
    assert len(vocab_matches) == 0, (
        f"clean.md should have no vocabulary matches, got: "
        f"{[m.pattern for m in vocab_matches]}"
    )


def test_bold_colon_detection() -> None:
    result = scan_file(TESTS_DIR / "sloppy.md")
    bold_matches = [m for m in result.matches if "Bold" in m.pattern]
    assert len(bold_matches) > 0, "sloppy.md should detect bold-colon lists"


def test_em_dash_detection() -> None:
    result = scan_file(TESTS_DIR / "sloppy.md")
    em_dash_matches = [m for m in result.matches if "em dash" in m.pattern]
    assert len(em_dash_matches) > 0, "sloppy.md should detect em dashes"


def test_numbered_heading_detection() -> None:
    result = scan_file(TESTS_DIR / "sloppy.md")
    numbered = [m for m in result.matches if "numbered sub-heading" in m.pattern]
    assert len(numbered) > 0, "sloppy.md should detect numbered sub-headings"


def test_single_em_dash_hard_fails() -> None:
    """A single em dash should flag the file even if the score is below threshold."""
    result = scan_file(TESTS_DIR / "one_em_dash.md")
    assert result.has_hard_fail, "one_em_dash.md should be a hard fail"
    hard_matches = [m for m in result.matches if m.hard_fail]
    assert len(hard_matches) >= 1, "should have at least one hard-fail match"
    assert any("em dash" in m.pattern for m in hard_matches)


def test_single_bold_colon_is_fine() -> None:
    """A single bold-colon list item should not flag the file."""
    result = scan_file(TESTS_DIR / "one_bold_colon.md")
    bold_matches = [m for m in result.matches if "Bold" in m.pattern]
    assert len(bold_matches) == 0, (
        f"one_bold_colon.md has only 1 bold-colon item, should not be flagged"
    )
    assert not result.has_hard_fail


def test_code_blocks_not_scanned() -> None:
    """Words inside code blocks should not be flagged."""
    result = scan_file(TESTS_DIR / "clean.md")
    # clean.md has code blocks but no slop in prose
    assert result.raw_score == 0, (
        f"clean.md has score {result.raw_score} -- code block content may be leaking"
    )


# ============================================================================
# New vocabulary tests
# ============================================================================

def test_new_ai_classic_words() -> None:
    """New AI-classic words should be detected."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    vocab_patterns = {m.pattern for m in result.matches if m.category == "vocabulary"}
    # Check a sample of new words
    for stem in ["unlock", "navigat", "realm", "landscape"]:
        assert stem in vocab_patterns, f"'{stem}' should be detected as vocabulary slop"


def test_self_congratulatory_words() -> None:
    """Self-congratulatory vocabulary should be detected."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    vocab_patterns = {m.pattern for m in result.matches if m.category == "vocabulary"}
    assert "meticulou" in vocab_patterns, "meticulou* should be flagged"
    assert "elegantly" in vocab_patterns, "elegantly should be flagged"


# ============================================================================
# New phrase tests
# ============================================================================

def test_rhetorical_questions_detected() -> None:
    """Rhetorical questions used as transitions should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    phrase_patterns = {m.pattern for m in result.matches if m.category == "phrase"}
    assert any("but what" in p or "so,? how" in p for p in phrase_patterns), (
        f"Rhetorical questions should be detected. Got: {phrase_patterns}"
    )


def test_conclusion_filler_detected() -> None:
    """Conclusion/summary filler phrases should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    phrase_patterns = {m.pattern for m in result.matches if m.category == "phrase"}
    assert any("in conclusion" in p or "to summarize" in p or "as we'?ve seen" in p
               for p in phrase_patterns), (
        f"Conclusion filler should be detected. Got: {phrase_patterns}"
    )


def test_todays_world_detected() -> None:
    """'In today's...' cold opens should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    phrase_patterns = {m.pattern for m in result.matches if m.category == "phrase"}
    assert any("today" in p for p in phrase_patterns), (
        f"'In today's' should be detected. Got: {phrase_patterns}"
    )


def test_role_language_detected() -> None:
    """Role language ('plays a crucial role') should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    phrase_patterns = {m.pattern for m in result.matches if m.category == "phrase"}
    assert any("role" in p for p in phrase_patterns), (
        f"Role language should be detected. Got: {phrase_patterns}"
    )


# ============================================================================
# Structural tests
# ============================================================================

def test_conclusion_section_detected() -> None:
    """A conclusion/summary section should be flagged structurally."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    structural_patterns = {m.pattern for m in result.matches if m.category == "structural"}
    assert any("conclusion" in p.lower() or "summary" in p.lower()
               for p in structural_patterns), (
        f"Conclusion section should be detected. Got: {structural_patterns}"
    )


def test_tricolon_detection() -> None:
    """Repeated tricolon patterns (X, Y, and Z) should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    structural_patterns = {m.pattern for m in result.matches if m.category == "structural"}
    assert any("tricolon" in p for p in structural_patterns), (
        f"Tricolon repetition should be detected. Got: {structural_patterns}"
    )


# ============================================================================
# Information density tests
# ============================================================================

def test_vague_phrases_detected() -> None:
    """Documents full of vague quantifiers should be flagged."""
    result = scan_file(TESTS_DIR / "sloppy_extended.md")
    density_matches = [m for m in result.matches if m.category == "density"]
    assert len(density_matches) > 0, (
        f"Vague phrases should be detected in density category"
    )


def test_clean_no_density_flags() -> None:
    """Clean docs should not trigger density flags."""
    result = scan_file(TESTS_DIR / "clean.md")
    density_matches = [m for m in result.matches if m.category == "density"]
    assert len(density_matches) == 0, (
        f"clean.md should have no density flags, got: "
        f"{[m.pattern for m in density_matches]}"
    )


# ============================================================================
# Configuration tests
# ============================================================================

def test_config_disable_vocabulary_group() -> None:
    """Disabling a vocabulary group should suppress those matches."""
    config = Config()
    config.vocabulary_enabled["corporate_marketing"] = False
    result = scan_file(TESTS_DIR / "sloppy.md", config)
    vocab_words = {m.pattern for m in result.matches if m.category == "vocabulary"}
    # "seamless", "leverag", etc. are corporate_marketing -- should be gone
    assert "seamless" not in vocab_words, "seamless should not be flagged when corporate_marketing is disabled"
    assert "leverag" not in vocab_words, "leverage should not be flagged when corporate_marketing is disabled"


def test_config_ignore_vocabulary() -> None:
    """Ignored vocabulary words should not be flagged."""
    config = Config()
    config.ignore_vocabulary = ["robust", "comprehensive"]
    result = scan_file(TESTS_DIR / "sloppy.md", config)
    vocab_words = {m.pattern for m in result.matches if m.category == "vocabulary"}
    assert "robust" not in vocab_words, "robust should be ignored"
    assert "comprehensive" not in vocab_words, "comprehensive should be ignored"


def test_config_extra_vocabulary() -> None:
    """Extra vocabulary words from config should be flagged."""
    config = Config()
    config.extra_vocabulary = ["tunnels"]
    result = scan_file(TESTS_DIR / "clean.md", config)
    vocab_words = {m.pattern for m in result.matches if m.category == "vocabulary"}
    assert "tunnels" in vocab_words, "custom word 'tunnels' should be flagged"


def test_config_disable_structural() -> None:
    """Disabling structural checks should suppress them."""
    config = Config()
    config.structural_enabled = False
    result = scan_file(TESTS_DIR / "sloppy.md", config)
    structural = [m for m in result.matches if m.category == "structural"]
    assert len(structural) == 0, "No structural matches when structural is disabled"


def test_config_disable_density() -> None:
    """Disabling density checks should suppress them."""
    config = Config()
    config.density_enabled = False
    result = scan_file(TESTS_DIR / "sloppy_extended.md", config)
    density = [m for m in result.matches if m.category == "density"]
    assert len(density) == 0, "No density matches when density is disabled"


def test_config_remove_hard_fail() -> None:
    """Removing a hard-fail rule should make it score-only."""
    config = Config()
    config.no_hard_fail_rules = ["em_dash", "bold_colon_list"]
    result = scan_file(TESTS_DIR / "one_em_dash.md", config)
    assert not result.has_hard_fail, "em_dash should not hard-fail when removed from hard_fail"


def test_config_weight_override() -> None:
    """Overriding weights should change the score."""
    config_default = Config()
    config_heavy = Config()
    config_heavy.vocabulary_weight = 5.0

    result_default = scan_file(TESTS_DIR / "sloppy.md", config_default)
    result_heavy = scan_file(TESTS_DIR / "sloppy.md", config_heavy)

    assert result_heavy.raw_score > result_default.raw_score, (
        f"Heavy vocab weight should increase score: "
        f"{result_heavy.raw_score} vs {result_default.raw_score}"
    )


# ============================================================================
# Extended test fixture
# ============================================================================

def _create_extended_fixture() -> None:
    """Create the sloppy_extended.md fixture if it doesn't exist."""
    path = TESTS_DIR / "sloppy_extended.md"
    if path.exists():
        return
    path.write_text("""\
# Understanding the Modern Development Landscape

In today's rapidly changing technology landscape, developers need to navigate
the complex realm of infrastructure management. This guide will help you unlock
the full potential of your deployment pipeline.

## Why This Matters

Configuration management plays a crucial role in modern software delivery.
It serves as a foundation for reliable, scalable, and efficient operations.

But what about teams that are just getting started? You might be wondering
how to begin your journey toward better infrastructure.

## Key Features

The system offers various types of functionality across multiple different
approaches. It provides several options for configuration, and more.

The platform meticulously handles deployment orchestration. Each component
is elegantly designed to work in harmony with the others, creating a
tapestry of interconnected services.

In certain cases, you may need to adjust settings. In some situations,
the defaults work well. Among others, the networking module stands out.

The architecture is robust, scalable, and secure. The interface is clean,
simple, and fast. The deployment process is reliable, efficient, and flexible.

## Getting Started

First, ensure your environment meets the requirements. The system is
powerful, flexible, and comprehensive. It offers a wide range of tools
and features for various use cases.

As we've seen in the previous section, the fundamentals are straightforward.
Building on this, let's explore the advanced configuration options.

Depending on your requirements, you can customize the behavior extensively.
Whether you're running a small cluster or a large deployment, the system
adapts to your needs.

## Conclusion

In conclusion, this platform provides a robust and scalable solution for
infrastructure management. As we've seen, it offers numerous features
that streamline the deployment process. The end result is a system that
is both powerful and intuitive.
""", encoding="utf-8")


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    _create_extended_fixture()

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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failures += 1
    print()
    print(f"{len(tests)} tests, {failures} failed")
    sys.exit(1 if failures else 0)
