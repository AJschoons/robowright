---
paths:
  - "**/*.md"
  - "tests/**"
  - "examples/**"
  - "site/**"
---

# Public content

This repository is public. Anything written here is read by strangers and kept in history.

- **Use invented examples.** Write examples, fixtures and sample output in the repo's `sample`
  vocabulary: the `example-org/sample` repository and its units, as in
  `examples/laptop/projects/sample.md`. If an example needs a product, use a generic app domain
  (a notes app, a todo list, a store), never one you work on.
- **Never write real values.** That rules out:
  - measurements, durations, costs or token counts taken from a real run;
  - ids of any kind: session ids, UUIDs, commit SHAs from another repository, ticket keys;
    the one exception is a dated test record written before publication, which may cite commit
    ids from the project's history before it was published; a new record must not;
  - device identifiers;
  - home-directory paths with a real user name;
  - time zones and offsets taken from a real machine;
  - the names of an employer, a colleague, a client or a private repository.

  Make up a value that looks right, and keep it obviously made up.
- **Never copy from a real project's records.** Ledgers, briefs, reviews, transcripts, decision
  logs and change descriptions from a real project stay out, even trimmed or renamed. Write the
  example from scratch.
- **The scrub gate is a tripwire, not a review.** `tools/scrub-gate.sh` matches only the patterns
  in each contributor's private denylist. Passing it says nothing about anything this rule covers.
