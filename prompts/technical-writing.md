# Technical Writing Rules

Rules for clear, accurate technical documentation. Apply these when
rewriting flagged content. Every rule has a reason — don't follow
blindly when the context demands otherwise.

## Voice

- **Active voice.** "The server rejects the request" not "the request
  is rejected by the server." Exception: passive is fine when the actor
  is unknown or irrelevant ("the file is created automatically").
- **Second person.** Address the reader as "you." Not "one," "the user,"
  or "we."
- **Present tense.** "This method returns a list" not "this method will
  return a list." Future tense only for things that literally happen later
  in a sequence.
- **Confident.** State facts directly. "This deletes the file" not "this
  should delete the file" or "this will typically delete the file."

## Sentences

- **Short.** If a sentence exceeds 25 words, split it. If it has a
  semicolon and two dependent clauses, it definitely needs splitting.
- **One idea per paragraph.** Two related but distinct ideas get two
  paragraphs.
- **No filler intros.** Start with the content. Cut "it's worth noting
  that," "in order to," "it's important to understand that."
- **No meta-commentary.** Don't describe what the document does ("this
  guide explains"). Just explain the thing.

## Word Choice

- **Plain words.** "Use" not "utilize." "Start" not "initiate." "End"
  not "terminate." "Help" not "facilitate." "Send" not "transmit."
  Technical precision for technical terms; plain language for everything
  else.
- **Consistent terminology.** One term per concept, everywhere. If the
  UI calls it a "workspace," the docs call it a "workspace." Never
  alternate between synonyms for the same thing.
- **No vague quantifiers.** Name the things. "Supports PostgreSQL,
  MySQL, and SQLite" not "supports various databases."
- **No marketing adjectives.** Drop "powerful," "robust," "seamless,"
  "cutting-edge" unless you immediately back them with a specific claim.

## Structure

- **Sentence case for headings.** "Configure the database" not
  "Configure The Database."
- **Headings describe content.** A reader scanning only headings should
  understand the page. "Set up authentication" not "Getting Started."
- **Numbered lists for sequences.** Bulleted lists for non-sequential
  items. Don't number things that have no order.
- **Parallel list items.** If the first item starts with a verb, all
  items start with a verb. If items are complete sentences, end with
  periods.
- **Minimal callouts.** Two to three per page maximum. If everything is
  a warning, nothing is.

## Code and Examples

- **Show, don't tell.** A code example often replaces an entire
  paragraph of description. When both exist, the example comes first.
- **Examples must work.** Include imports, initialization, and error
  handling when necessary for the code to run. Use realistic values
  (`user@example.com`, not `foo`).
- **Code font for code.** File paths, commands, parameter names, and
  variable names go in backticks. UI elements go in bold.

## What Not to Do

- Don't swap one problem word for another ("leverage" → "utilize").
- Don't delete content to satisfy a lint rule. Rewrite to be specific.
- Don't remove bold from terms that serve as definitions or labels.
- Don't drop conjunctions or break grammar to shorten sentences.
- Don't add enthusiasm. No exclamation marks in technical prose.

## Sources

Distilled from:

- [Google Developer Documentation Style Guide](https://developers.google.com/style) (CC BY 4.0)
- [Microsoft Writing Style Guide](https://learn.microsoft.com/en-us/style-guide/)
- [Diataxis](https://diataxis.fr/) (CC BY-SA 4.0)
- [developer-docs-framework](https://github.com/anivar/developer-docs-framework) (MIT)
