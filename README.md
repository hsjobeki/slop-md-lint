# slop-md-lint

Style linter for technical markdown. Flags unreviewed LLM-generated docs
by accumulated score across five rule levels (vocabulary, phrases,
formatting, structure, information density). Single Python file, no
dependencies. Not an LLM detector. Scoped to technical docs; blog posts,
essays, and chat messages are out of scope.

> [!IMPORTANT]
> This tool was written by an LLM and reviewed by a human.
>
> - Does not replace human review
> - Gates LLM-generated PRs by flagging obvious slop
> - Feed the results back into your LLM, rebase, submit cleaner PRs

## Why slop-md-lint

| | slop-md-lint | [Vale](https://github.com/errata-ai/vale) | [VectorLint](https://github.com/TRocket-Labs/vectorlint) |
|---|---|---|---|
| **Approach** | Regex + accumulated scoring | Regex + per-match rules | LLM-as-judge |
| **Scope** | LLM slop patterns | General prose style | Whatever the prompt asks |
| **Offline/deterministic** | Yes | Yes | No (API calls, non-deterministic) |
| **Fixup output** | Writing guide with line refs | No | No |

Vale catches bad writing in general. slop-md-lint catches LLM-specific
patterns (accumulation, cross-section analysis, formatting). They complement
each other. VectorLint catches things no regex can but costs money and
varies between runs.

slop-md-lint closes the loop: `--type technical` produces a fixup guide
the LLM can apply directly. LLM writes → tool flags → LLM rewrites →
human reviews the diff.

## How it works

```
normalized_score = raw_score / (word_count / 100)
```

Every match adds weighted points. The total is normalized by document length.
A 500-word doc with 15 raw points scores 3.0. Default threshold is 3.0.
No single pattern fails a file — it's the accumulation that triggers.

Scores are hidden from default output to avoid optimization pressure when
feeding results to an LLM. Use `--score` to show them.

Code blocks and frontmatter are stripped before scanning. Only prose is scored.

## Usage

```bash
nix run github:hsjobeki/slop-md-lint -- docs/                          # scan a directory
nix run github:hsjobeki/slop-md-lint -- docs/ --threshold 5.0          # adjust threshold
nix run github:hsjobeki/slop-md-lint -- docs/ --type technical         # fixup guide
nix run github:hsjobeki/slop-md-lint -- docs/ --json                   # machine-readable output
nix run github:hsjobeki/slop-md-lint -- docs/ --score                  # show numeric scores
nix run github:hsjobeki/slop-md-lint -- --list-rules                   # print all rules
nix run github:hsjobeki/slop-md-lint -- --dump-config                  # print built-in defaults
```

Exit 0 means clean. Exit 1 means flagged files.

## Writing guide and fixup

Three levels of LLM-friendly output, from simple to full:

### `--writing-guide`

Appends a fix-up prompt with grouped findings and line references.
Generated from actual matches, not a static template.

### `--type technical`

Generates a multi-step fixup guide: built-in writing rules + findings.
No config needed.

```bash
nix run github:hsjobeki/slop-md-lint -- docs/ --type technical
```

Output:
```
Step 1: Technical writing rules
────────────────────────────────────────
<built-in style rules>

Step 2: Fix slop-lint findings
────────────────────────────────────────
<specific findings with line references>
```

### `--fixup` + TOML

For project-specific rules, configure `[[fixup]]` in `.sloplint.toml`.
`--type` and `--fixup` can be combined.

```toml
[[fixup]]
label = "Project conventions"
source = "docs/writing-conventions.md"
```

```bash
nix run github:hsjobeki/slop-md-lint -- docs/ --type technical --fixup
```

## CI

```yaml
# GitHub Actions
- name: Check docs for LLM slop
  run: nix run github:hsjobeki/slop-md-lint -- docs/
```

## What it catches

Five detection levels, each targeting a different axis of LLM writing habits.

### Level 1: Vocabulary (65 stems, weight 1.0 each)

Word stems that are fine on their own but accumulate in LLM output. Each stem
matches all inflected forms (e.g. "leverag" catches leverage, leverages,
leveraged, leveraging). Six groups:

| Group | Count | Examples |
|---|---|---|
| `ai_classics` | 22 | delve, elevat\*, empower, harness, navigat\*, realm, landscape, tapestry, myriad, paramount, cornerstone |
| `corporate_marketing` | 16 | streamlin\*, leverag\*, utiliz\*, facilitat\*, seamless, intuitiv\*, performant |
| `overuse` | 4 | ecosystem, robust, optimal, comprehensive |
| `filler_transitions` | 13 | furthermore, moreover, notably, crucially, essentially, additionally, ultimately, fundamentally |
| `self_congratulatory` | 6 | meticulou\*, thoughtful, elegantly, graceful, beautiful, intelligent |
| `overqualifiers` | 4 | overarching, aforementioned, above-mentioned, underscore |

### Level 2: Phrases (112 patterns, weight 2.0 each)

Multi-word patterns that are strong LLM indicators. Thirteen groups:

| Group | Count | What it catches |
|---|---|---|
| `filler_phrases` | 23 | "it's worth noting", "everything you need to know", "don't hesitate to", "at all times" |
| `this_verb_openers` | 7 | "this ensures", "this provides", "this enables", "this allows you to" |
| `meta_intros` | 9 | "this guide explains", "in this document, we will", "by the end of this" |
| `hedging` | 5 | "depending on your requirements", "whether you're X or Y" |
| `marketing_tone` | 11 | "powerful and X", "a wide range of", "not only X but also", "it offers features such as" |
| `filler_gerunds` | 5 | "ensuring X and Y", "enabling X and Y", "making it easy to" |
| `slop_headings` | 7 | "Key Benefits", "Getting Started With", "Conclusion", "Final Thoughts" |
| `filler_transitions` | 10 | "with that in mind", "first and foremost", "let's explore", "by following these" |
| `conclusion_filler` | 10 | "in conclusion", "to summarize", "as we've seen", "we hope this", "on your journey" |
| `todays_world` | 3 | "in today's", "in the ever-evolving", "the rapidly changing" |
| `role_language` | 3 | "plays a crucial role", "serves as a foundation", "paves the way" |
| `rhetorical_questions` | 7 | "but what about", "so how do we", "you might be wondering" |
| `tautologies` | 12 | "completely eliminate", "end result", "basic fundamentals", "very unique" |

### Level 3: Formatting (5 rules, weight 0.75-1.5)

Punctuation and markdown patterns that betray LLM authorship.

| Rule | Weight | Trigger |
|---|---|---|
| `em_dash` | 1.5 | ` — ` in prose |
| `bold_colon_list` | 0.75 | `- **Word:** rest` (2+ to trigger) |
| `numbered_subheading` | 1.5 | `#### 1. Foo` |
| `exclamation_in_prose` | 1.0 | `!` in non-heading text (3+ to trigger) |
| `emoji_in_docs` | 1.0 | emoji characters (3+ to trigger) |

### Level 4: Structural (6 checks, weight 2.0-3.0)

Document-level analysis that catches patterns no single regex can find.

| Check | Trigger |
|---|---|
| Excessive bold | too many `**bold**` phrases relative to word count |
| Sentence monotony | >30% of sentences start with the same word |
| Heading stuffing | too many headings for the content (e.g., 8 headings, 150 words) |
| Tricolon abuse | 3+ instances of "X, Y, and Z" listing pattern |
| Conclusion section | last heading is "Conclusion", "Summary", "Recap", etc. |
| Adjective pairs | 2+ marketing adjective pairs ("robust and scalable", "flexible and efficient") |

Only fires on documents with 150+ words of prose. Short files are not penalized.

### Level 5: Information density (weight 1.0-2.0)

Catches documents that use many words to say nothing specific.

| Check | Trigger |
|---|---|
| Vague quantifiers | 3+ of: "various types", "multiple options", "and more", "etc.", "and so on", "among others" |
| Low-information paragraphs | >15% filler vocabulary and no concrete specifics (no numbers, code refs, paths, or proper nouns) |

## Configuration

All defaults are baked into the tool. No config file needed. If you need to
override specific settings, place a `.sloplint.toml` in your project root.
Only the settings you want to change need to be present. The file is
auto-discovered, or pass `--config path/to/config.toml`. To see the full
defaults, run `--dump-config`.

```toml
threshold = 3.0
min_words_to_score = 50

[weights]
vocabulary = 1.0
phrase = 2.0
vague = 1.0

# Disable groups that cause false positives in your project
[vocabulary.enabled]
self_congratulatory = false

# Add project-specific slop words
[vocabulary]
extra = ["synergize", "incentivize"]
ignore = ["robust"]  # legitimate in your domain

[phrases.enabled]
rhetorical_questions = false

[formatting.enabled]
exclamation_in_prose = false

# Tune structural thresholds
[structural.thresholds]
monotony_ratio = 0.4
tricolon_min_count = 5

# Override hard-fail behavior (none are hard-fail by default)
[hard_fail]
add = ["em_dash", "numbered_subheading"]

# Writing guide: minimum category score to show fix advice
[guide]
vocabulary = 3.0
phrase = 2.0
formatting = 0.0
structural = 2.0
density = 2.0
```

Requires Python 3.11+ for TOML parsing (uses `tomllib`). On older Python,
install `tomli` or skip the config file (defaults work without it).

## Limitations

The tool strips code blocks (`` ``` `` and `~~~`), inline code, and YAML
frontmatter before scanning. Everything else is treated as prose. This is
a deliberate choice to keep the tool simple and dependency-free rather than
pulling in a full markdown parser.

This means it does not strip:

- Indented code blocks (4 spaces / 1 tab)
- HTML comments (`<!-- ... -->`)
- Link URLs (`[text](url)` scans both text and URL)
- Autolinks (`<https://...>`)
- Fenced div markers (`::: warning`)

In practice this rarely matters. The words the tool flags ("delve",
"comprehensive", "this ensures") do not appear in code blocks or URLs.
Even if a stray match leaks from a URL, it contributes 1 point to a
score that needs to hit 3.0 per 100 words. The accumulation model
absorbs occasional noise.

If you have non-standard markdown with heavy use of indented code blocks
or HTML comments containing English prose, you may see false positives.
In that case, raise the threshold or ignore specific words via config.

## Things LLMs do (written by an LLM)

Things learned while building and testing this tool:

- **Scores create bad incentives.** Showing a numeric score to an LLM turns
  editing into an optimization problem. The LLM will drop conjunctions, delete
  content, and break grammar just to push the number down. Scores are hidden
  from default output for this reason (`--score` shows them for humans).

- **Line numbers invite context-free edits.** An LLM shown `L42 (+1.5)` will
  jump to line 42 and mechanically change it without reading the surrounding
  paragraph. The tool still shows line numbers (humans need them), but the
  hints and guardrails try to force the LLM to consider context.

- **"Do not break grammar" must be said explicitly.** LLMs do not assume you
  want grammatically correct output. If the tool says "fix tricolon patterns"
  without saying "do not drop conjunctions," the LLM will remove "and" from
  lists and call it done. Every guardrail against a bad fix must be stated
  as an explicit "do not."

- **LLMs cause collateral damage.** When fixing a flagged pattern on a line,
  an LLM will casually edit nearby unflagged content too — dropping words,
  rewriting phrases, deleting information that wasn't a problem. The default
  output now says "do not modify content the linter didn't flag."

- **LLMs take the shortest path to silence a warning.** The fix that removes
  the most points with the least effort wins, even if it damages the text.
  Dropping "and" from a list is easier than restructuring a sentence, so
  that's what happens.

- **"Not every instance needs fixing" gets ignored under score pressure.**
  You can tell an LLM that soft items are optional, but if it sees a number
  to optimize, it will fix everything anyway. The instruction only works
  when the score is hidden.

- **LLMs don't push back on the tool.** A human editor would read eight
  tricolon patterns and say "these are normal English, the tool is wrong
  here." An LLM treats every flagged item as something to fix, even when
  the correct action is to leave it alone.

- **Hiding scores helps.** After removing scores from default output, Claude
  correctly ignored two flagged files that had emojis in natural context. It
  left the emojis and accepted the tool failure. Removing the optimization
  pressure lets the LLM use judgment instead of chasing a number.

- **This tool was written by an LLM.** It flags patterns that LLMs produce.
  LLMs can detect slop in others' output but can't stop producing it
  themselves.

- **LLMs fix one flagged word by introducing another.** Replacing "leverage"
  with "utilize" because it sounds different. Both are flagged.

- **Like a cat bringing you a dead bird,** an LLM will proudly present its
  "improved" version with half the content missing.

## Tests

```bash
nix build .#checks.tests
```

28 tests across 6 fixture files covering all five detection levels plus
configuration overrides.

## Design

One file. No classes beyond dataclasses. No dependencies beyond Python stdlib.
Deterministic: same input always produces the same score. Suitable for CI
gating, pre-commit hooks, and PR review automation.
