#!/usr/bin/env python3
"""slop-md-lint: detect probable AI-generated slop in markdown documentation.

Scores files based on weighted pattern matches normalized by document length.
No single pattern fails a file - it's the accumulation that triggers a warning.

Supports configuration via TOML files for customizing rules, thresholds,
severity levels, and adding project-specific patterns.
"""

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Use tomllib (3.11+) or fall back to tomli
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


# ============================================================================
# Rule definitions -- organized by detection level
# ============================================================================

# Level 1: VOCABULARY
# Words that are individually fine but accumulate in AI slop.
# Grouped by flavor so users can disable specific groups.

VOCABULARY_RULES: dict[str, list[str]] = {
    # Classic AI-favorite verbs/adjectives that real humans rarely chain together.
    # Each entry matches the stem + any suffix (e.g. "delve" catches delves, delved,
    # delving).
    "ai_classics": [
        "delve",
        "elevat",  # elevate, elevates, elevated, elevating, elevation
        "empower",
        "foster",
        "harness",
        "pivotal",
        "game-changer",
        "paradigm",
        "synerg",  # synergy, synergies, synergistic
        "holistic",
        "proactiv",  # proactive, proactively
        "actionable",
        "unlock",
        "navigat",  # navigate, navigates, navigating, navigation
        "realm",
        "landscape",
        "tapestry",
        "myriad",
        "plethora",
        "paramount",
        "beacon",
        "cornerstone",
    ],
    # Corporate/marketing tone that doesn't belong in technical docs
    "corporate_marketing": [
        "streamlin",  # streamline, streamlines, streamlined, streamlining
        "leverag",  # leverage, leverages, leveraged, leveraging
        "utiliz",  # utilize, utilizes, utilized, utilizing, utilization
        "facilitat",  # facilitate, facilitates, facilitating, facilitation
        "comprehensive",
        "robust",
        "seamless",
        "cutting-edge",
        "state-of-the-art",
        "best-in-class",
        "world-class",
        "intuitiv",  # intuitive, intuitively
        "effortless",
        "sophisticat",  # sophisticated, sophistication
        "versatil",  # versatile, versatility
        "performant",
    ],
    # Words that are legitimate in moderation but become an AI signal when
    # repeated heavily.  Unlike the groups above, the fix is to *reduce*
    # repetition rather than eliminate the word.
    "overuse": [
        "ecosystem",
        "robust",
        "optimal",
        "comprehensive",
    ],
    # Filler adverbs/transitions that pad without adding meaning
    "filler_transitions": [
        "furthermore",
        "moreover",
        "notably",
        "crucially",
        "essentially",
        "additionally",
        "importantly",
        "interestingly",
        "ultimately",
        "fundamentally",
        "inherently",
        "undeniably",
        "arguably",
    ],
    # Meticulous/thorough family -- AI's self-congratulatory vocabulary
    "self_congratulatory": [
        "meticulou",  # meticulous, meticulously
        "thoughtful",
        "elegantly",
        "graceful",
        "beautiful",
        "intelligent",
    ],
    # Overqualifiers -- vague intensifiers that weaken rather than strengthen
    "overqualifiers": [
        "overarching",
        "aforementioned",
        "above-mentioned",
        "underscore",
    ],
}

# Per-vocabulary-group fix hints for the writing guide.
VOCABULARY_HINTS: dict[str, str] = {
    "ai_classics": "drop entirely or say what actually happens",
    "corporate_marketing": "use plain English: 'use', 'help', 'simplify'; or be specific about what",
    "filler_transitions": "remove — restructure if the sentence needs a transition",
    "self_congratulatory": "drop the adjective; if the sentence works without it, it wasn't needed",
    "overqualifiers": "drop entirely",
    "overuse": "legitimate word — reduce repetition, keep where most precise, replace or drop the rest",
}

# Default weight for vocabulary matches
VOCABULARY_WEIGHT = 1.0

# Level 2: SPECIFIC PHRASES
# Multi-word patterns that are strong AI indicators.

PHRASE_RULES: dict[str, list[str]] = {
    # Classic filler -- adds zero information
    "filler_phrases": [
        r"it'?s worth noting",
        r"it'?s worth mentioning",
        r"it'?s important to note",
        r"it should be noted",
        r"it bears mentioning",
        r"let'?s dive in",
        r"here'?s the thing",
        r"without further ado",
        r"take it to the next level",
        r"at the end of the day",
        r"rest assured",
        r"look no further",
        r"in a nutshell",
        r"at its core",
        r"everything you need to know",
        r"more important than ever",
        r"don'?t hesitate to",
        r"at all times",
        r"taking into account",
        r"to that end",
        r"with that said",
        r"that being said",
        r"having said that",
    ],
    # "This ensures/allows/provides" -- AI's favorite sentence starters
    "this_verb_openers": [
        r"this ensures\b",
        r"this allows you to",
        r"this provides\b",
        r"this enables\b",
        r"this makes it (easy|possible|simple)",
        r"this means that\b",
        r"this gives you\b",
    ],
    # Filler intros -- sentences that describe the doc instead of teaching
    "meta_intros": [
        r"this guide (explains|covers|walks you through|will help)",
        r"this document (covers|explains|describes|outlines)",
        r"this section (covers|explains|describes|outlines)",
        r"in this (guide|tutorial|document|section),? (we|you) will",
        r"by the end of this",
        r"in this article",
        r"in the following section",
        r"as we will see",
        r"as we'll see",
    ],
    # AI hedging -- vague qualifications instead of specifics
    "hedging": [
        r"depending on your (needs|requirements|use case|setup|environment)",
        r"tailored to your",
        r"whether you'?re .+? or .+?,",
        r"may vary (depending|based) on",
        r"your mileage may vary",
    ],
    # Marketing/sales tone in technical docs
    "marketing_tone": [
        r"powerful and \w+",
        r"designed for .+ and .+\b(backups|workflows|systems|security)",
        r"it offers features such as",
        r"offers? a \w+ (solution|approach|way) (for|to)",
        r"a wide (range|variety) of",
        r"not only \w+ but also",
        r"the power of\b",
        r"the beauty of\b",
        r"stands? out from",
        r"boasts?\b",
        r"best practice:",
    ],
    # "ensuring/enabling" filler gerunds -- padding that adds no information
    "filler_gerunds": [
        r"ensuring .{3,30} and \w+",
        r"enabling .{3,30} and \w+",
        r"providing .{3,30} and \w+",
        r"allowing .{3,30} and \w+",
        r"making it (easy|possible|simple) to",
    ],
    # Heading-level slop
    "slop_headings": [
        r"key (benefit|advantage|takeaway|feature|concept|consideration)s?",
        r"getting started with\b",
        r"understanding\b.{0,30}$",
        r"conclusion\s*$",
        r"final thoughts\s*$",
        r"wrapping up\s*$",
        r"putting it all together\s*$",
    ],
    # Filler transitions between sections
    "filler_transitions": [
        r"with that in mind",
        r"building on this",
        r"as (mentioned|noted|discussed) (earlier|above|previously)",
        r"now that we'?ve",
        r"let'?s (explore|look at|examine|take a look|take a closer look)",
        r"now let'?s",
        r"first,? let'?s",
        r"before we (begin|start|dive|proceed)",
        r"first and foremost",
        r"by following these",
    ],
    # Conclusion/summary filler -- restating what was said
    "conclusion_filler": [
        r"in conclusion",
        r"to summarize",
        r"in summary",
        r"to sum up",
        r"to recap",
        r"as we'?ve seen",
        r"as (shown|demonstrated|illustrated) above",
        r"we hope (this|you)",
        r"on your journey",
        r"happy (coding|deploying|hacking|building)",
    ],
    # "In today's..." -- the AI cold open
    "todays_world": [
        r"in today'?s\b",
        r"in the (modern|current|ever-evolving|rapidly changing)",
        r"the (ever-evolving|rapidly changing|fast-paced)\b",
    ],
    # Role language -- AI describing importance
    "role_language": [
        r"plays? a (crucial|vital|key|important|critical|essential|significant) role",
        r"paves? the way",
        r"serves? as a? ?(foundation|cornerstone|backbone|pillar)",
    ],
    # Rhetorical questions -- AI loves these as transitions
    "rhetorical_questions": [
        r"but what (about|if|happens)",
        r"so,? how (do|can|does|should) (we|you)",
        r"but why (should|would|do|is)",
        r"ever wondered",
        r"what does this mean for",
        r"you might (be wondering|ask|wonder)",
        r"curious about",
    ],
    # Tautologies and redundancies
    "tautologies": [
        r"completely eliminate",
        r"fully complete",
        r"very unique",
        r"absolutely essential",
        r"basic fundamentals",
        r"end result",
        r"future plans",
        r"past history",
        r"free gift",
        r"advance planning",
        r"final outcome",
        r"general consensus",
    ],
}

# Per-phrase-group fix hints for the writing guide.
PHRASE_HINTS: dict[str, str] = {
    "filler_phrases": "delete the phrase; say the thing directly",
    "this_verb_openers": "rewrite to say what actually happens, e.g. 'Deploys finish in 30s' instead of 'This enables faster deploys'",
    "meta_intros": "delete — start with the content",
    "hedging": "be specific or drop the hedge",
    "marketing_tone": "state the fact without selling it",
    "filler_gerunds": "state the result directly",
    "slop_headings": "use a heading that says what the section contains",
    "filler_transitions": "remove the transition; the next sentence should stand on its own",
    "conclusion_filler": "delete the section or replace with content that adds new information",
    "todays_world": "delete — start with the actual content",
    "role_language": "say what the thing does, not that it's important",
    "rhetorical_questions": "make a statement instead",
    "tautologies": "drop the redundant word",
}

# Default weight for phrase matches
PHRASE_WEIGHT = 2.0

# Level 3: FORMATTING PATTERNS
# Punctuation and markdown formatting that betrays AI authorship.

FORMATTING_RULES: dict[str, dict] = {
    "em_dash": {
        "pattern": r" \u2014 ",
        "weight": 1.5,
        "hard_fail": True,
        "description": "em dash ( \u2014 )",
        "multiline": False,
        "hint": "replace with comma, period, or parentheses",
    },
    "bold_colon_list": {
        # "- **Word:** rest" or "- **Word**: rest" -- colon inside or outside bold
        # But not CLI flags like **--flag**: or links like **[foo]**:
        # One is fine (e.g. a single definition). Two or more is the AI pattern.
        "pattern": r"^[-*]\s+\*\*(?![-\[])([^*:]+):?\*\*:?\s",
        "weight": 1.5,
        "hard_fail": False,
        "description": "**Bold:** list pattern",
        "multiline": True,
        "min_count": 2,
        "hint": "Do not remove bold from terms that serve as definitions or labels.",
    },
    "numbered_subheading": {
        # #### 1. Foo -- AI loves this textbook structure
        # Only #### or deeper. Top-level numbered headings are often legitimate.
        "pattern": r"^#{4,6}\s+\d+\.\s+",
        "weight": 1.5,
        "hard_fail": False,
        "description": "numbered sub-heading",
        "multiline": True,
        "hint": "drop the number, just use the heading text",
    },
    "exclamation_in_prose": {
        # Exclamation marks in prose (not in code, not in URLs, not in headings)
        # AI uses these for fake enthusiasm: "This is great!" "You're all set!"
        "pattern": r"(?<![#`])[A-Za-z]+!(?:\s|$)",
        "weight": 1.0,
        "hard_fail": False,
        "description": "exclamation mark in prose",
        "multiline": False,
        "min_count": 3,  # One or two are fine; many signal AI cheerfulness
        "hint": "state facts; drop the exclamation mark",
    },
    "emoji_in_docs": {
        # Emoji in documentation -- often AI-added decoration
        "pattern": r"[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]",
        "weight": 1.0,
        "hard_fail": False,
        "description": "emoji in documentation",
        "multiline": False,
        "min_count": 3,
        "hint": "remove emoji unless it's a UI element reference",
    },
}

# Level 4: STRUCTURAL/RHETORICAL PATTERNS
# Document-level patterns that indicate AI generation.

# Thresholds for structural checks
STRUCTURAL_THRESHOLDS = {
    "min_words_for_structural": 150,
    "min_words_for_bold_check": 100,
    "min_sentences_for_monotony": 6,
    "monotony_ratio": 0.3,
    "bold_ratio": 2.0,  # bold phrases per 50 words
    "min_headings_for_ratio": 5,
    "words_per_heading_min": 25,
    "adj_pair_min_count": 2,
    "tricolon_min_count": 3,
}

# Adjective pairs: "robust and scalable", etc.
MARKETING_ADJECTIVES = [
    "powerful",
    "robust",
    "secure",
    "efficient",
    "flexible",
    "scalable",
    "comprehensive",
    "seamless",
    "intuitive",
    "modular",
    "reliable",
    "performant",
    "lightweight",
    "versatile",
    "elegant",
    "clean",
    "simple",
    "fast",
]

# Level 5: INFORMATION DENSITY
# Vague quantifiers that avoid committing to specifics.

VAGUE_PHRASES = [
    r"\b(various|multiple|numerous|several|many) (different )?(types?|kinds?|forms?|ways?|methods?|approaches?|options?|tools?|features?|aspects?|factors?)\b",
    r"\b(some|certain) (cases?|situations?|scenarios?|circumstances?|instances?)\b",
    r"\band (much )?more\b",
    r"\betc\.?\b",
    r"\band so on\b",
    r"\bamong others?\b",
]

VAGUE_WEIGHT = 1.0
MIN_VAGUE_FOR_FLAG = 3  # A few are fine; many means the doc avoids specifics

# Per-category fix hints for structural and density matches.
STRUCTURAL_HINTS: dict[str, str] = {
    "excessive bold": "reduce bold usage; only bold terms that need visual emphasis",
    "monotonous sentence starts": "vary sentence openings; rewrite at least one",
    "too many headings": "merge sections; prefer fewer headings with more content each",
    "tricolon repetition": "Do not drop conjunctions or delete list items.",
    "summary/conclusion section": "delete the section or replace with content that adds new information",
    "marketing adjective pairs": "drop the adjective pair; be specific about what the thing does",
}

DENSITY_HINTS: dict[str, str] = {
    "vague quantifier": "name the things instead of saying 'various', 'multiple', 'and more'",
    "low-information paragraph": "add specifics (numbers, code refs, paths, names) or delete the paragraph",
}

# Default guide thresholds: minimum category score to include fix advice.
# Hard fails always show regardless of threshold.
DEFAULT_GUIDE_THRESHOLDS: dict[str, float] = {
    "vocabulary": 3.0,
    "phrase": 2.0,
    "formatting": 0.0,
    "structural": 2.0,
    "density": 2.0,
}

DEFAULT_THRESHOLD = 3.0
MIN_WORDS_TO_SCORE = 50

# Weights for structural/density matches (not per-rule configurable yet,
# but pulled into constants so they aren't magic numbers in scan_file).
STRUCTURAL_WEIGHT = 3.0
DENSITY_PARAGRAPH_WEIGHT = 2.0
TRICOLON_WEIGHT = 2.0
ADJ_PAIR_WEIGHT = 2.0


# ============================================================================
# Default configuration as TOML
# ============================================================================


def _generate_default_toml() -> str:
    """Build the default TOML config string from the actual rule constants.

    This is the single source of truth: --dump-config prints it, and
    Config() parses it so the defaults are never out of sync.
    """
    lines = [
        "# sloplint configuration",
        "# Place as .sloplint.toml in your project root.",
        "",
        f"threshold = {DEFAULT_THRESHOLD}",
        f"min_words_to_score = {MIN_WORDS_TO_SCORE}",
        "",
        "[weights]",
        f"vocabulary = {VOCABULARY_WEIGHT}",
        f"phrase = {PHRASE_WEIGHT}",
        f"vague = {VAGUE_WEIGHT}",
        f"structural = {STRUCTURAL_WEIGHT}",
        f"tricolon = {TRICOLON_WEIGHT}",
        f"adj_pair = {ADJ_PAIR_WEIGHT}",
        f"density_paragraph = {DENSITY_PARAGRAPH_WEIGHT}",
        "",
        "# Enable/disable vocabulary groups",
        "[vocabulary.enabled]",
    ]
    for group in VOCABULARY_RULES:
        lines.append(f"{group} = true")
    lines += [
        "",
        "# Extra words to flag (project-specific)",
        '# vocabulary.extra = ["synergize"]',
        "",
        "# Words to ignore (false positives for your project)",
        '# vocabulary.ignore = ["robust"]',
        "",
        "# Enable/disable phrase groups",
        "[phrases.enabled]",
    ]
    for group in PHRASE_RULES:
        lines.append(f"{group} = true")
    lines += [
        "",
        "# Enable/disable formatting rules",
        "[formatting.enabled]",
    ]
    for rule in FORMATTING_RULES:
        lines.append(f"{rule} = true")
    lines += [
        "",
        "[structural]",
        "enabled = true",
        "",
        "[structural.thresholds]",
    ]
    for key, val in STRUCTURAL_THRESHOLDS.items():
        lines.append(f"{key} = {val}")
    lines += [
        "",
        "[density]",
        "enabled = true",
        "",
        "# Override hard-fail rules",
        "# [hard_fail]",
        '# add = ["numbered_subheading"]    # make these hard-fail too',
        '# remove = ["em_dash"]             # don\'t hard-fail on these',
        "",
        "# Writing guide thresholds: minimum category score to include",
        "# fix advice in --writing-guide output. Hard fails always show.",
        "[guide]",
    ]
    for cat, val in DEFAULT_GUIDE_THRESHOLDS.items():
        lines.append(f"{cat} = {val}")
    lines += [
    ]
    return "\n".join(lines) + "\n"


DEFAULT_TOML = _generate_default_toml()

# Parse once at module level -- this is the single source of truth for defaults.
_DEFAULT_DATA: dict = tomllib.loads(DEFAULT_TOML)

# Known top-level TOML keys (for unknown-key warnings)
_KNOWN_KEYS = {
    "threshold",
    "min_words_to_score",
    "weights",
    "vocabulary",
    "phrases",
    "formatting",
    "structural",
    "density",
    "hard_fail",
    "guide",
}


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class Config:
    """Runtime configuration, loaded from defaults + optional TOML file.

    All default values come from DEFAULT_TOML (the single source of truth).
    Config() with no arguments parses that string.  Config.from_toml() and
    Config.from_toml_string() layer user overrides on top.

    Field defaults are placeholders -- __post_init__ immediately overwrites
    them from _DEFAULT_DATA.
    """

    threshold: float = 0.0
    min_words_to_score: int = 0

    # Which rule groups are enabled
    vocabulary_enabled: dict[str, bool] = field(default_factory=dict)
    phrase_enabled: dict[str, bool] = field(default_factory=dict)
    formatting_enabled: dict[str, bool] = field(default_factory=dict)
    structural_enabled: bool = False
    density_enabled: bool = False

    # Weight overrides
    vocabulary_weight: float = 0.0
    phrase_weight: float = 0.0
    vague_weight: float = 0.0
    structural_weight: float = 0.0
    tricolon_weight: float = 0.0
    adj_pair_weight: float = 0.0
    density_paragraph_weight: float = 0.0

    # Extra patterns (added from config file)
    extra_vocabulary: list[str] = field(default_factory=list)
    extra_phrases: list[str] = field(default_factory=list)

    # Patterns to ignore (e.g., project-specific terms that are fine)
    ignore_vocabulary: list[str] = field(default_factory=list)
    ignore_phrases: list[str] = field(default_factory=list)

    # Hard fail overrides
    hard_fail_rules: list[str] = field(default_factory=list)
    no_hard_fail_rules: list[str] = field(default_factory=list)

    # Structural thresholds
    structural: dict[str, float] = field(default_factory=dict)

    # Guide thresholds: minimum category score to include fix advice
    guide_thresholds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Apply parsed DEFAULT_TOML so every field gets the right value.
        self._apply_dict(_DEFAULT_DATA)

    def _apply_dict(self, data: dict, warn_unknown: bool = False) -> None:
        """Layer a parsed TOML dict onto this Config instance."""
        if warn_unknown:
            unknown = set(data.keys()) - _KNOWN_KEYS
            for key in sorted(unknown):
                print(f"Warning: unknown config key '{key}'", file=sys.stderr)

        self.threshold = data.get("threshold", self.threshold)
        self.min_words_to_score = data.get(
            "min_words_to_score", self.min_words_to_score
        )

        if "weights" in data:
            w = data["weights"]
            self.vocabulary_weight = w.get("vocabulary", self.vocabulary_weight)
            self.phrase_weight = w.get("phrase", self.phrase_weight)
            self.vague_weight = w.get("vague", self.vague_weight)
            self.structural_weight = w.get("structural", self.structural_weight)
            self.tricolon_weight = w.get("tricolon", self.tricolon_weight)
            self.adj_pair_weight = w.get("adj_pair", self.adj_pair_weight)
            self.density_paragraph_weight = w.get(
                "density_paragraph", self.density_paragraph_weight
            )

        if "vocabulary" in data:
            for group, enabled in data["vocabulary"].get("enabled", {}).items():
                self.vocabulary_enabled[group] = enabled
            self.extra_vocabulary = list(
                data["vocabulary"].get("extra", self.extra_vocabulary)
            )
            self.ignore_vocabulary = list(
                data["vocabulary"].get("ignore", self.ignore_vocabulary)
            )

        if "phrases" in data:
            for group, enabled in data["phrases"].get("enabled", {}).items():
                self.phrase_enabled[group] = enabled
            self.extra_phrases = list(data["phrases"].get("extra", self.extra_phrases))
            self.ignore_phrases = list(
                data["phrases"].get("ignore", self.ignore_phrases)
            )

        if "formatting" in data:
            for rule, enabled in data["formatting"].get("enabled", {}).items():
                self.formatting_enabled[rule] = enabled

        if "structural" in data:
            self.structural_enabled = data["structural"].get(
                "enabled", self.structural_enabled
            )
            for key, val in data["structural"].get("thresholds", {}).items():
                self.structural[key] = val

        if "density" in data:
            self.density_enabled = data["density"].get("enabled", self.density_enabled)

        if "hard_fail" in data:
            self.hard_fail_rules = list(
                data["hard_fail"].get("add", self.hard_fail_rules)
            )
            self.no_hard_fail_rules = list(
                data["hard_fail"].get("remove", self.no_hard_fail_rules)
            )

        if "guide" in data:
            for cat, val in data["guide"].items():
                self.guide_thresholds[cat] = float(val)

    @classmethod
    def from_toml_string(cls, text: str) -> "Config":
        """Parse a TOML string into a Config (defaults + overrides)."""
        cfg = cls()  # applies DEFAULT_TOML via __post_init__
        cfg._apply_dict(tomllib.loads(text), warn_unknown=True)
        return cfg

    @classmethod
    def from_toml(cls, path: Path) -> "Config":
        """Load a TOML file as config (defaults + overrides)."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        cfg = cls()  # applies DEFAULT_TOML via __post_init__
        cfg._apply_dict(data, warn_unknown=True)
        return cfg


# ============================================================================
# Compiled patterns cache
# ============================================================================


@dataclass
class CompiledPatterns:
    """Pre-compiled regex patterns for a given Config. Built once, reused across files."""

    vocabulary: list[tuple[str, str, re.Pattern]]
    phrases: list[tuple[str, str, re.Pattern]]
    formatting: list[tuple[str, re.Pattern, dict]]
    vague: list[tuple[str, re.Pattern]]


def _build_vocabulary_patterns(
    config: Config,
) -> list[tuple[str, str, re.Pattern]]:
    """Build compiled word patterns from enabled groups + extras - ignores.

    Returns list of (stem, group_name, compiled_pattern).
    """
    ignored = set(w.lower() for w in config.ignore_vocabulary)
    words: list[tuple[str, str]] = []  # (stem, group)
    for group, word_list in VOCABULARY_RULES.items():
        if config.vocabulary_enabled.get(group, True):
            for w in word_list:
                words.append((w, group))
    for w in config.extra_vocabulary:
        words.append((w, "extra"))
    words = [(w, g) for w, g in words if w.lower() not in ignored]
    return [
        (word, group, re.compile(rf"\b{re.escape(word)}\w*\b", re.IGNORECASE))
        for word, group in words
    ]


def _build_phrase_patterns(
    config: Config,
) -> list[tuple[str, str, re.Pattern]]:
    """Build compiled phrase patterns from enabled groups + extras - ignores.

    Returns list of (regex_string, group_name, compiled_pattern).
    """
    ignored = set(config.ignore_phrases)
    phrases: list[tuple[str, str]] = []  # (pattern, group)
    for group, phrase_list in PHRASE_RULES.items():
        if config.phrase_enabled.get(group, True):
            for p in phrase_list:
                phrases.append((p, group))
    for p in config.extra_phrases:
        phrases.append((p, "extra"))
    phrases = [(p, g) for p, g in phrases if p not in ignored]
    return [(phrase, group, re.compile(phrase, re.IGNORECASE)) for phrase, group in phrases]


def _build_formatting_patterns(
    config: Config,
) -> list[tuple[str, re.Pattern, dict]]:
    """Build compiled formatting patterns from enabled rules."""
    result = []
    for name, rule in FORMATTING_RULES.items():
        if not config.formatting_enabled.get(name, True):
            continue
        # Apply hard_fail overrides
        hard_fail = rule["hard_fail"]
        if name in config.hard_fail_rules:
            hard_fail = True
        if name in config.no_hard_fail_rules:
            hard_fail = False
        flags = re.MULTILINE if rule.get("multiline") else 0
        compiled = re.compile(rule["pattern"], flags)
        meta = {
            "name": name,
            "weight": rule["weight"],
            "hard_fail": hard_fail,
            "description": rule["description"],
            "min_count": rule.get("min_count", 1),
        }
        result.append((name, compiled, meta))
    return result


def _build_vague_patterns() -> list[tuple[str, re.Pattern]]:
    """Build compiled vague-quantifier patterns."""
    return [(pat, re.compile(pat, re.IGNORECASE)) for pat in VAGUE_PHRASES]


def build_patterns(config: Config) -> CompiledPatterns:
    """Build all compiled patterns for a config. Call once, pass to scan_file."""
    return CompiledPatterns(
        vocabulary=_build_vocabulary_patterns(config),
        phrases=_build_phrase_patterns(config),
        formatting=_build_formatting_patterns(config),
        vague=_build_vague_patterns(),
    )


# Pre-compiled constant patterns used in scan_file / extract_prose_sentences
_ADJ_ESCAPED = "|".join(re.escape(a) for a in MARKETING_ADJECTIVES)
ADJ_PAIR_PATTERN = re.compile(
    rf"\b({_ADJ_ESCAPED})\b and \b({_ADJ_ESCAPED})\b",
    re.IGNORECASE,
)
TRICOLON_PATTERN = re.compile(r"\b\w+,\s+\w+,?\s+and\s+\w+\b", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s")
_HEADING_RE = re.compile(r"^#{1,6}\s")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]\s+")
_LOWERCASE_TOKEN_RE = re.compile(r"[a-z]+")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SPECIFICS_RE = re.compile(
    r"\d|`[^`]+`|[A-Z][a-z]+[A-Z]|\.(?:py|js|nix|sh|yaml|toml|json|go|rs)\b|/[\w/]+"
)

# Code block removal: fenced (``` and ~~~) and inline code
CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`")

# Frontmatter removal
FRONTMATTER_PATTERN = re.compile(r"^---[\s\S]*?---\n", re.MULTILINE)


def strip_non_prose(text: str) -> str:
    """Remove code blocks, inline code, and frontmatter so we don't scan them."""
    return CODE_BLOCK_PATTERN.sub("", FRONTMATTER_PATTERN.sub("", text))


# ============================================================================
# Data types
# ============================================================================


@dataclass
class Match:
    line_num: int
    category: str
    pattern: str
    text: str
    weight: float
    hard_fail: bool = False
    matched_word: str = ""
    group: str = ""


@dataclass
class FileResult:
    path: Path
    word_count: int
    raw_score: float
    normalized_score: float
    matches: list[Match] = field(default_factory=list)
    has_hard_fail: bool = False


PREVIEW_LENGTH = 100


# ============================================================================
# Text processing
# ============================================================================

# Backward-compatible alias
strip_code_blocks = strip_non_prose


class LineIndex:
    """Index for fast substring lookup in original file lines.

    Builds a mapping from lowercased words to line numbers so that
    find_line doesn't need to scan all lines for every match.
    Falls back to a proximity scan for substrings not in the index.
    """

    def __init__(self, original_lines: list[str]) -> None:
        self._lines = original_lines
        self._lower_lines = [line.lower() for line in original_lines]
        # Map lowercased token -> set of line indices (0-based)
        self._word_index: dict[str, set[int]] = {}
        for i, line in enumerate(self._lower_lines):
            for token in _LOWERCASE_TOKEN_RE.findall(line):
                if token not in self._word_index:
                    self._word_index[token] = set()
                self._word_index[token].add(i)

    def find_line(
        self,
        search: str,
        clean_line_idx: int,
        case_sensitive: bool = True,
    ) -> int:
        """Find the 1-based line number in the original file for a match.

        Tries the word index first for O(1) candidate lookup, then falls
        back to a bounded proximity scan.
        """
        search_lower = search.lower()
        lines = self._lines if case_sensitive else self._lower_lines
        search_text = search if case_sensitive else search_lower

        # Try index: get candidate lines from the first word token
        first_token_match = _LOWERCASE_TOKEN_RE.search(search_lower)
        if first_token_match:
            token = first_token_match.group(0)
            candidates = self._word_index.get(token)
            if candidates:
                # Check candidates nearest to clean_line_idx first
                for idx in sorted(candidates, key=lambda i: abs(i - clean_line_idx)):
                    if search_text in lines[idx]:
                        return idx + 1

        # Fallback: bounded proximity scan (max 50 lines each direction)
        max_scan = min(len(self._lines), 50)
        for offset in range(max_scan):
            for idx in [clean_line_idx + offset, clean_line_idx - offset]:
                if 0 <= idx < len(self._lines):
                    if search_text in lines[idx]:
                        return idx + 1
        return 0


def extract_prose_sentences(clean_lines: list[str]) -> list[str]:
    """Extract prose sentences, skipping list items and headings."""
    prose_lines = "\n".join(
        line
        for line in clean_lines
        if line.strip()
        and not _LIST_ITEM_RE.match(line)
        and not _NUMBERED_ITEM_RE.match(line)
        and not _HEADING_RE.match(line)
    )
    sentences = _SENTENCE_SPLIT_RE.split(prose_lines)
    return [s.strip() for s in sentences if s.strip()]


# ============================================================================
# Scanner
# ============================================================================


def scan_file(
    path: Path,
    config: Config | None = None,
    patterns: CompiledPatterns | None = None,
) -> FileResult:
    if config is None:
        config = Config()

    # Build patterns once if not provided (for single-file use)
    if patterns is None:
        patterns = build_patterns(config)

    vocab_patterns = patterns.vocabulary
    phrase_patterns = patterns.phrases
    formatting_patterns = patterns.formatting

    original_text = path.read_text(encoding="utf-8")
    original_lines = original_text.splitlines()
    line_index = LineIndex(original_lines)
    clean_text = strip_code_blocks(original_text)
    clean_lines = clean_text.splitlines()

    words = clean_text.split()
    word_count = len(words)
    if word_count < config.min_words_to_score:
        return FileResult(
            path=path, word_count=word_count, raw_score=0, normalized_score=0
        )

    matches: list[Match] = []

    # --- Level 1: Vocabulary ---
    for word, group, pattern in vocab_patterns:
        for i, line in enumerate(clean_lines):
            for m in pattern.finditer(line):
                line_num = line_index.find_line(word, i, case_sensitive=False)
                matches.append(
                    Match(
                        line_num=line_num,
                        category="vocabulary",
                        pattern=word,
                        text=line.strip(),
                        weight=config.vocabulary_weight,
                        matched_word=m.group(0),
                        group=group,
                    )
                )

    # --- Level 2: Phrases ---
    for phrase_pat, group, pattern in phrase_patterns:
        for i, line in enumerate(clean_lines):
            m = pattern.search(line)
            if m:
                line_num = line_index.find_line(m.group(0), i, case_sensitive=False)
                matches.append(
                    Match(
                        line_num=line_num,
                        category="phrase",
                        pattern=phrase_pat,
                        text=line.strip(),
                        weight=config.phrase_weight,
                        matched_word=m.group(0),
                        group=group,
                    )
                )

    # --- Level 3: Formatting ---
    for name, compiled, meta in formatting_patterns:
        found: list[tuple[str, int]] = []
        if meta.get("min_count", 1) > 1:
            # Count-based rules: collect all, only flag if threshold met
            for i, line in enumerate(clean_lines):
                for fm in compiled.finditer(line):
                    found.append((line.strip(), i))
            # Also check multiline patterns against full text
            if not found:
                for fm in compiled.finditer(clean_text):
                    line_start = clean_text.count("\n", 0, fm.start())
                    found.append((fm.group(0).strip(), line_start))
            if len(found) >= meta["min_count"]:
                for text, idx in found:
                    line_num = line_index.find_line(text[:40] if text else "", idx)
                    matches.append(
                        Match(
                            line_num=line_num,
                            category="formatting",
                            pattern=f"{meta['description']} ({len(found)}x)",
                            text=text,
                            weight=meta["weight"],
                            hard_fail=meta["hard_fail"],
                            group=name,
                        )
                    )
        else:
            # Per-occurrence rules (em dash, bold-colon, etc.)
            # For multiline patterns, search the full clean text
            is_multiline = FORMATTING_RULES.get(name, {}).get("multiline", False)
            if is_multiline:
                for fm in compiled.finditer(clean_text):
                    matched_text = fm.group(0).strip()
                    line_start = clean_text.count("\n", 0, fm.start())
                    line_num = line_index.find_line(matched_text, line_start)
                    matches.append(
                        Match(
                            line_num=line_num,
                            category="formatting",
                            pattern=f"{meta['description']}{' [hard fail]' if meta['hard_fail'] else ''}",
                            text=matched_text,
                            weight=meta["weight"],
                            hard_fail=meta["hard_fail"],
                            group=name,
                        )
                    )
            else:
                for i, line in enumerate(clean_lines):
                    for _ in compiled.finditer(line):
                        search_text = (
                            " \u2014 " if "em_dash" in name else line.strip()[:40]
                        )
                        line_num = line_index.find_line(search_text, i)
                        matches.append(
                            Match(
                                line_num=line_num,
                                category="formatting",
                                pattern=f"{meta['description']}{' [hard fail]' if meta['hard_fail'] else ''}",
                                text=line.strip(),
                                weight=meta["weight"],
                                hard_fail=meta["hard_fail"],
                                group=name,
                            )
                        )

    # --- Level 4: Structural/rhetorical patterns ---
    if config.structural_enabled:
        thresholds = config.structural

        # Excessive bolding
        all_bolds = _BOLD_RE.findall(clean_text)
        bold_count = sum(
            1
            for b in all_bolds
            if not b.startswith("-")
            and not b.startswith("[")
            and not b.startswith("Attribute:")
        )
        if word_count > thresholds["min_words_for_bold_check"]:
            bold_ratio = bold_count / (word_count / 50)
            if bold_ratio > thresholds["bold_ratio"]:
                matches.append(
                    Match(
                        line_num=0,
                        category="structural",
                        pattern=f"excessive bold ({bold_count} bold phrases in {word_count} words)",
                        text="",
                        weight=config.structural_weight,
                        group="excessive_bold",
                    )
                )

        sentences = extract_prose_sentences(clean_lines)

        # Only run prose-dependent checks on docs with enough content
        if word_count >= thresholds["min_words_for_structural"]:
            # Sentence opening monotony
            if len(sentences) > thresholds["min_sentences_for_monotony"]:
                opening_words = [s.split()[0] for s in sentences if s.split()]
                if opening_words:
                    most_common = max(set(opening_words), key=opening_words.count)
                    count = opening_words.count(most_common)
                    ratio = count / len(opening_words)
                    if ratio > thresholds["monotony_ratio"]:
                        matches.append(
                            Match(
                                line_num=0,
                                category="structural",
                                pattern=f'monotonous sentence starts: "{most_common}" ({count}/{len(sentences)} = {ratio:.0%})',
                                text="",
                                weight=config.structural_weight,
                                group="monotonous_starts",
                            )
                        )

            # Heading-to-content ratio
            headings = [line for line in clean_lines if _HEADING_RE.match(line)]
            if len(headings) >= thresholds["min_headings_for_ratio"]:
                words_per_heading = word_count / len(headings)
                if words_per_heading < thresholds["words_per_heading_min"]:
                    matches.append(
                        Match(
                            line_num=0,
                            category="structural",
                            pattern=f"too many headings ({len(headings)} headings for {word_count} words = {words_per_heading:.0f} words/heading)",
                            text="",
                            weight=config.structural_weight,
                            group="too_many_headings",
                        )
                    )

            # Tricolon abuse: "X, Y, and Z" patterns appearing repeatedly
            # AI loves listing three things: "fast, reliable, and secure"
            tricolons = TRICOLON_PATTERN.findall(clean_text)
            if len(tricolons) >= thresholds.get("tricolon_min_count", 3):
                matches.append(
                    Match(
                        line_num=0,
                        category="structural",
                        pattern=f"tricolon repetition ({len(tricolons)}x 'X, Y, and Z' pattern)",
                        text="",
                        weight=config.tricolon_weight,
                        group="tricolon",
                    )
                )

            # Conclusion-restates-intro detection
            if len(headings) >= 2:
                last_heading_idx = None
                for i, line in enumerate(clean_lines):
                    if _HEADING_RE.match(line):
                        last_heading_idx = i
                if last_heading_idx is not None:
                    last_heading = clean_lines[last_heading_idx].strip().lower()
                    conclusion_words = {
                        "conclusion",
                        "summary",
                        "recap",
                        "takeaway",
                        "wrapping",
                        "final thoughts",
                        "putting it all together",
                    }
                    if any(w in last_heading for w in conclusion_words):
                        matches.append(
                            Match(
                                line_num=last_heading_idx + 1,
                                category="structural",
                                pattern=f'summary/conclusion section: "{clean_lines[last_heading_idx].strip()}"',
                                text="",
                                weight=config.structural_weight,
                                group="conclusion_section",
                            )
                        )

        # Marketing adjective pairs: "robust and scalable"
        adj_pairs = ADJ_PAIR_PATTERN.findall(clean_text)
        if len(adj_pairs) >= thresholds["adj_pair_min_count"]:
            matches.append(
                Match(
                    line_num=0,
                    category="vocabulary",
                    pattern=f"marketing adjective pairs ({len(adj_pairs)}x)",
                    text="",
                    weight=config.adj_pair_weight * len(adj_pairs),
                    group="marketing_adj_pairs",
                )
            )

    # --- Level 5: Information density ---
    if config.density_enabled:
        vague_matches: list[tuple[str, int]] = []
        for pat, compiled in patterns.vague:
            for i, line in enumerate(clean_lines):
                m = compiled.search(line)
                if m:
                    vague_matches.append((m.group(0), i))

        if len(vague_matches) >= MIN_VAGUE_FOR_FLAG:
            for text, idx in vague_matches:
                line_num = line_index.find_line(text, idx, case_sensitive=False)
                matches.append(
                    Match(
                        line_num=line_num,
                        category="density",
                        pattern=f'vague quantifier: "{text}"',
                        text=clean_lines[idx].strip() if idx < len(clean_lines) else "",
                        weight=config.vague_weight,
                        matched_word=text,
                        group="vague_quantifier",
                    )
                )

        # Content-free paragraph detection
        # Paragraphs with high filler-word ratio and no specifics (numbers, code, paths)
        if word_count >= 150:
            all_vocab = set()
            for group_words in VOCABULARY_RULES.values():
                all_vocab.update(w.lower() for w in group_words)

            paragraphs = _PARAGRAPH_SPLIT_RE.split(clean_text)
            for para in paragraphs:
                para_stripped = para.strip()
                if not para_stripped or para_stripped.startswith("#"):
                    continue
                para_words = para_stripped.split()
                if len(para_words) < 10:
                    continue
                # Check if paragraph has any specifics: numbers, code refs, file extensions, paths
                has_specifics = bool(_SPECIFICS_RE.search(para_stripped))
                if not has_specifics:
                    filler_count = sum(
                        1 for w in para_words if w.lower().rstrip(".,;:!?") in all_vocab
                    )
                    filler_ratio = filler_count / len(para_words)
                    if filler_ratio > 0.15:
                        first_line = para_stripped.split("\n")[0]
                        idx = 0
                        for j, line in enumerate(clean_lines):
                            if first_line[:40] in line:
                                idx = j
                                break
                        line_num = line_index.find_line(first_line[:40], idx)
                        matches.append(
                            Match(
                                line_num=line_num,
                                category="density",
                                pattern=f"low-information paragraph ({filler_ratio:.0%} filler words, no specifics)",
                                text=first_line[:PREVIEW_LENGTH],
                                weight=config.density_paragraph_weight,
                                group="low_info_paragraph",
                            )
                        )

    raw_score = sum(m.weight for m in matches)
    normalized_score = raw_score / (word_count / 100)
    has_hard_fail = any(m.hard_fail for m in matches)

    return FileResult(
        path=path,
        word_count=word_count,
        raw_score=raw_score,
        normalized_score=normalized_score,
        matches=matches,
        has_hard_fail=has_hard_fail,
    )


# ============================================================================
# Writing guide (dynamically generated from actual matches)
# ============================================================================

# Unified hint lookup by group name. Merges all hint dicts + formatting hints.
_GROUP_HINTS: dict[str, str] = {}
_GROUP_HINTS.update(VOCABULARY_HINTS)
_GROUP_HINTS.update(PHRASE_HINTS)
for _name, _rule in FORMATTING_RULES.items():
    if _rule.get("hint"):
        _GROUP_HINTS[_name] = _rule["hint"]
_GROUP_HINTS.update({
    "excessive_bold": STRUCTURAL_HINTS["excessive bold"],
    "monotonous_starts": STRUCTURAL_HINTS["monotonous sentence starts"],
    "too_many_headings": STRUCTURAL_HINTS["too many headings"],
    "tricolon": STRUCTURAL_HINTS["tricolon repetition"],
    "conclusion_section": STRUCTURAL_HINTS["summary/conclusion section"],
    "marketing_adj_pairs": STRUCTURAL_HINTS["marketing adjective pairs"],
    "vague_quantifier": DENSITY_HINTS["vague quantifier"],
    "low_info_paragraph": DENSITY_HINTS["low-information paragraph"],
})

_GUIDE_PREAMBLE = """\
slop-md-lint detected patterns commonly left by LLMs.

BEFORE CHANGING ANYTHING:
1. Read the full document.
2. For each flagged word/phrase, read the surrounding context.
   Ask: is this word doing real work here, or is it filler?
   A word that's precise and meaningful in its context stays,
   even if the linter flagged it.

RULES:
- Fix HARD items unconditionally.
- For SOFT items: judge each match in context. The same word
  can be the right choice in one paragraph and filler in another.
- To reduce repetition, cut redundant sentences or use pronouns
  ("them", "these", "it"). Don't swap precise terms for vaguer ones.
- Keep all technical content, code blocks, links, and examples intact.
- Do not change lines or sections not mentioned below.
- Re-run the linter after changes to verify the score drops.\
"""


def build_guide(result: FileResult, config: Config) -> str:
    """Build a targeted writing guide from the actual matches in a FileResult.

    Groups matches by rule group, deduplicates, separates hard vs soft.
    """
    thresholds = config.guide_thresholds

    # Collect category-level scores to filter by threshold
    cat_scores: dict[str, float] = {}
    cat_has_hard_fail: dict[str, bool] = {}
    for m in result.matches:
        cat_scores[m.category] = cat_scores.get(m.category, 0.0) + m.weight
        if m.hard_fail:
            cat_has_hard_fail[m.category] = True

    # Filter matches by category threshold (hard fails always pass)
    eligible: list[Match] = []
    for m in result.matches:
        score = cat_scores.get(m.category, 0.0)
        threshold = thresholds.get(m.category, 0.0)
        if m.hard_fail or score >= threshold:
            eligible.append(m)

    if not eligible:
        return ""

    # Split into hard and soft
    hard_matches = [m for m in eligible if m.hard_fail]
    soft_matches = [m for m in eligible if not m.hard_fail]

    lines: list[str] = [_GUIDE_PREAMBLE, ""]

    if hard_matches:
        lines.append("HARD (always fix):")
        _emit_grouped_matches(hard_matches, lines)
        lines.append("")

    if soft_matches:
        lines.append("SOFT (fix only if filler, not the document's actual subject):")
        _emit_grouped_matches(soft_matches, lines)
        lines.append("")

    return "\n".join(lines)


def _emit_grouped_matches(matches: list[Match], lines: list[str]) -> None:
    """Group matches by rule group, deduplicate, and emit compact output."""
    # Preserve order of first appearance
    group_order: list[str] = []
    by_group: dict[str, list[Match]] = {}
    for m in matches:
        key = m.group or m.pattern  # fallback for matches without group
        if key not in by_group:
            group_order.append(key)
        by_group.setdefault(key, []).append(m)

    for group_key in group_order:
        group_matches = by_group[group_key]
        hint = _GROUP_HINTS.get(group_key, "")

        # Collect all matched words in this group
        words = [m.matched_word for m in group_matches if m.matched_word]
        unique_words = list(dict.fromkeys(words))  # dedupe, preserve order

        # Build the header: [group] "word" if few unique words, else just [group]
        if len(unique_words) == 0:
            # structural/formatting matches with no matched_word
            header = f"  [{group_key}] ({len(group_matches)}x)"
        elif len(unique_words) <= 3:
            word_list = ", ".join(f'"{w}"' for w in unique_words)
            header = f"  [{group_key}] {word_list} ({len(group_matches)}x)"
        else:
            header = f"  [{group_key}] ({len(group_matches)}x)"

        if hint:
            header += f" \u2192 {hint}"
        lines.append(header)

        # Build compact line references
        if len(unique_words) <= 3:
            # Words already in header: just list line numbers compactly
            line_refs = _compact_line_refs(group_matches)
            lines.append(f"    {line_refs}")
        else:
            # Many distinct words: show word per line
            line_refs = _compact_line_refs_with_words(group_matches)
            lines.append(f"    {line_refs}")


def _compact_line_refs(matches: list[Match]) -> str:
    """Build compact line references like 'L3, L13 (2x), L19 (2x), L35 (3x)'."""
    # Count occurrences per line
    line_counts: dict[int, int] = {}
    line_order: list[int] = []
    for m in matches:
        ln = m.line_num
        if ln not in line_counts:
            line_order.append(ln)
        line_counts[ln] = line_counts.get(ln, 0) + 1

    parts = []
    for ln in line_order:
        count = line_counts[ln]
        ref = f"L{ln}" if ln else "file"
        if count > 1:
            ref += f" ({count}x)"
        parts.append(ref)
    return ", ".join(parts)


def _compact_line_refs_with_words(matches: list[Match]) -> str:
    """Build line refs with words like 'L11: "navigate", L35: "navigation"'."""
    # Dedupe by (line_num, matched_word)
    seen: set[tuple[int, str]] = set()
    parts = []
    for m in matches:
        key = (m.line_num, m.matched_word)
        if key in seen:
            continue
        seen.add(key)
        ref = f"L{m.line_num}" if m.line_num else "file"
        if m.matched_word:
            parts.append(f'{ref}: "{m.matched_word}"')
        else:
            parts.append(ref)
    return ", ".join(parts)


# ============================================================================
# CLI
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect probable AI-generated slop in markdown files.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=f"Normalized score threshold for flagging (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all matches, not just flagged files",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Glob patterns to exclude (e.g. 'reference/**')",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--dump-config",
        action="store_true",
        help="Print the default configuration as TOML and exit",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all rule groups and their patterns, then exit",
    )
    parser.add_argument(
        "--writing-guide",
        action="store_true",
        help="Print the writing guide after flagged output (for LLM fix-up prompts)",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="Show numeric scores in output (hidden by default to avoid optimization pressure)",
    )

    args = parser.parse_args()

    if args.dump_config:
        _print_default_config()
        sys.exit(0)

    if args.list_rules:
        _print_rules()
        sys.exit(0)

    # Load config
    config = Config()
    config_path = args.config
    if config_path is None:
        # Auto-discover config in current directory
        for candidate in [".sloplint.toml", "sloplint.toml", "pyproject.toml"]:
            p = Path(candidate)
            if p.exists():
                if candidate == "pyproject.toml":
                    # Only use pyproject.toml if it has [tool.sloplint]
                    try:
                        if tomllib:
                            with open(p, "rb") as f:
                                data = tomllib.load(f)
                            if "tool" in data and "sloplint" in data["tool"]:
                                config_path = p
                    except Exception:
                        pass
                else:
                    config_path = p
                break

    if config_path and config_path.exists():
        if config_path.name == "pyproject.toml":
            # pyproject.toml nests config under [tool.sloplint]
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            config = Config()
            config._apply_dict(data["tool"]["sloplint"], warn_unknown=True)
        else:
            config = Config.from_toml(config_path)

    # CLI threshold overrides config
    threshold = args.threshold if args.threshold is not None else config.threshold

    if not args.paths:
        parser.error("the following arguments are required: paths")

    # Collect markdown files
    md_files: list[Path] = []
    for p in args.paths:
        path = Path(p)
        if path.is_file() and path.suffix == ".md":
            md_files.append(path)
        elif path.is_dir():
            md_files.extend(sorted(path.rglob("*.md")))

    # Apply excludes
    if args.exclude:

        def is_excluded(f: Path) -> bool:
            return any(
                fnmatch.fnmatch(str(f), pat) or fnmatch.fnmatch(f.name, pat)
                for pat in args.exclude
            )

        md_files = [f for f in md_files if not is_excluded(f)]

    if not md_files:
        print("No markdown files found.", file=sys.stderr)
        sys.exit(1)

    compiled = build_patterns(config)
    results = [scan_file(f, config, compiled) for f in md_files]
    flagged = [r for r in results if r.normalized_score > threshold or r.has_hard_fail]

    if args.json:
        output = [
            {
                "path": str(r.path),
                "word_count": r.word_count,
                "raw_score": r.raw_score,
                "normalized_score": round(r.normalized_score, 2),
                "flagged": r.normalized_score > threshold or r.has_hard_fail,
                "hard_fail": r.has_hard_fail,
                "matches": [
                    {
                        "line": m.line_num,
                        "category": m.category,
                        "pattern": m.pattern,
                        "weight": m.weight,
                        "hard_fail": m.hard_fail,
                    }
                    for m in r.matches
                ],
            }
            for r in results
            if r.normalized_score > threshold or r.has_hard_fail or args.verbose
        ]
        print(json.dumps(output, indent=2))
        if flagged and args.writing_guide:
            for r in flagged:
                guide = build_guide(r, config)
                if guide:
                    print(f"\n--- {r.path} ---", file=sys.stderr)
                    print(guide, file=sys.stderr)
    else:
        for r in sorted(results, key=lambda r: r.normalized_score, reverse=True):
            is_flagged = r.normalized_score > threshold or r.has_hard_fail
            if not is_flagged and not args.verbose:
                continue
            if r.word_count == 0:
                continue

            if r.has_hard_fail:
                status = "HARD FAIL"
            elif r.normalized_score > threshold:
                status = "FLAGGED"
            else:
                status = "ok"
            print(f"\n{'=' * 60}")
            print(f"[{status}] {r.path}")
            if args.score:
                print(
                    f"  words: {r.word_count}  raw: {r.raw_score:.1f}  normalized: {r.normalized_score:.2f}  (threshold: {threshold})"
                )

            if r.matches:
                # Group by category for readability
                by_cat: dict[str, list[Match]] = {}
                for m in r.matches:
                    by_cat.setdefault(m.category, []).append(m)

                for cat in [
                    "vocabulary",
                    "phrase",
                    "formatting",
                    "structural",
                    "density",
                ]:
                    cat_matches = by_cat.get(cat, [])
                    if not cat_matches:
                        continue

                    if cat == "vocabulary":
                        # Show only unique stems and total score, no lines/counts/samples.
                        # The LLM must read the document and judge which uses are
                        # domain terms vs filler.
                        cat_score = sum(m.weight for m in cat_matches)
                        unique_stems = list(dict.fromkeys(
                            m.pattern for m in cat_matches
                        ))
                        stems_str = ", ".join(unique_stems)
                        print(f"\n  [{cat}] +{cat_score:.1f} — {stems_str}")
                        print(f"    Vocabulary words are often domain terms. Don't replace")
                        print(f"    a word that is the topic of the document. Fix phrase and")
                        print(f"    formatting issues first. If the score still exceeds the")
                        print(f"    threshold due to domain vocabulary, that's acceptable.")
                    else:
                        print(f"\n  [{cat}]")
                        for m in cat_matches:
                            loc = f"L{m.line_num}" if m.line_num else "file"
                            print(f"    {loc:>6}  ({m.weight:+.1f}) {m.pattern}")
                            if m.text:
                                preview = m.text[:PREVIEW_LENGTH] + (
                                    "..." if len(m.text) > PREVIEW_LENGTH else ""
                                )
                                print(f"           {preview}")

        # Summary table (only with --score)
        if args.score:
            epsilon = 0.2
            nearby = [
                r
                for r in results
                if r.raw_score > 0 and r.normalized_score > threshold - epsilon
            ]
            if nearby:
                print(f"\n{'=' * 60}")
                print(f"  {'SCORE':>5}  {'RAW':>5}  {'WORDS':>5}  FILE")
                print(f"  {'-----':>5}  {'---':>5}  {'-----':>5}  {'----'}")
                for r in sorted(nearby, key=lambda r: r.normalized_score, reverse=True):
                    marker = " ! " if r.normalized_score > threshold else " ~ "
                    print(
                        f"{marker}{r.normalized_score:5.2f}  {r.raw_score:5.1f}  {r.word_count:5d}  {r.path}"
                    )

        print(f"\n{'=' * 60}")
        print(
            f"Scanned {len(results)} files. {len(flagged)} flagged (threshold: {threshold})."
        )
        if flagged:
            print()
            print("Not every flagged instance needs fixing. Fix hard fails and")
            print("clear filler. Do not modify content the linter didn't flag.")

        if flagged and args.writing_guide:
            for r in flagged:
                guide = build_guide(r, config)
                if guide:
                    print()
                    print("=" * 60)
                    print(f"Writing guide for: {r.path}")
                    print("=" * 60)
                    print(guide)

    sys.exit(1 if flagged else 0)


def _print_default_config() -> None:
    """Print the default TOML config (generated from the actual constants)."""
    print(DEFAULT_TOML, end="")


def _print_rules() -> None:
    """Print all rules in a human-readable format."""
    print("VOCABULARY RULES")
    print("=" * 40)
    for group, words in VOCABULARY_RULES.items():
        print(f"\n  [{group}] ({len(words)} words)")
        for w in words:
            print(f"    - {w}")

    print("\n\nPHRASE RULES")
    print("=" * 40)
    for group, phrases in PHRASE_RULES.items():
        print(f"\n  [{group}] ({len(phrases)} patterns)")
        for p in phrases:
            print(f"    - {p}")

    print("\n\nFORMATTING RULES")
    print("=" * 40)
    for name, rule in FORMATTING_RULES.items():
        hf = " [hard fail]" if rule["hard_fail"] else ""
        mc = f" (min {rule['min_count']}x)" if rule.get("min_count", 1) > 1 else ""
        print(f"  {name}: {rule['description']}{hf}{mc} (weight: {rule['weight']})")

    print("\n\nSTRUCTURAL RULES")
    print("=" * 40)
    print("  - excessive bold usage")
    print("  - sentence opening monotony")
    print("  - heading-to-content ratio")
    print("  - tricolon repetition (X, Y, and Z)")
    print("  - conclusion/summary section detection")
    print("  - marketing adjective pairs")

    print("\n\nINFORMATION DENSITY RULES")
    print("=" * 40)
    print(
        f"  Vague quantifiers ({len(VAGUE_PHRASES)} patterns, min {MIN_VAGUE_FOR_FLAG} to flag):"
    )
    for p in VAGUE_PHRASES:
        print(f"    - {p}")
    print("  - Low-information paragraph detection")


if __name__ == "__main__":
    main()
