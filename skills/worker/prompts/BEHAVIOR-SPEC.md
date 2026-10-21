# Behavior spec — <slug> <unit id>

You are writing the spec for one `behavior` unit of a Robowright Session **before it is
implemented**: the rules, the examples, and the tests that will fail until the unit exists. The
session that implements it may not change what your tests expect, so an expected value you get
wrong is a defect that ships with a green test defending it.

## Inputs

- **Contract**, pasted below by the caller from `<session_dir>/BRIEF.md`: the unit row (id,
  title, kind, acceptance checks), `Goal`, `Settled decisions`, `Decision authority`,
  `Out of scope`, and the `Read first` documents that concern this unit.
- **Worktree**: `<worktree>`, at the predecessor unit's head. Nothing of this unit exists yet.
  Read it for seams and vocabulary. For a bug fix the existing behavior is the **defect**, not
  the oracle: the expected outcome comes from the contract, never from what the code does now.
- **Test conventions**: the test target, the framework the suite uses, and where test files go,
  from the project hook → Tests, pasted by the caller.
- **Outputs**: `<session_dir>/evidence/<unit>-behaviors.md`, and test files under the paths the
  caller lists.

## What to do

`~/.claude/skills/bdd/SKILL.md`, steps 1–3 as far as writing the tests:

1. **Discover** — rules, examples, questions, from the contract alone.
2. **Formulate** — the behavior table. Every row's last column names where its expected value
   came from, quoting the contract. A row you cannot source is a question.
3. **Write the tests** from the table, in the target's framework and naming. Call the API the
   unit *should* have; you are its first caller.

**Questions.** Nobody is here to ask. For each: state the defensible default and mark the row
`Assumed: <default>`. If the answers differ in something the contract's `Decision authority`
puts above the Worker — a product-visible behavior the brief does not settle, a schema or
public-protocol shape — do not default it: that is `BLOCKED`.

## Output

`<session_dir>/evidence/<unit>-behaviors.md`, first line alone: `SPEC` or `BLOCKED`.

```
SPEC

## Rules
R1 — <one sentence, domain words>

## Questions
Q1 — <question> → Assumed: <default>, because <reason> | Settled by: "<contract quote>"

## Behavior table
| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|

## API assumed
Every type, member, and signature the tests call that does not exist at the worktree's head —
the caller builds the skeleton from this list.

## Test files written
<path> — <suite name>, <n> tests
```

`BLOCKED` is followed by the one question that blocks, its options, and which line of
`Decision authority` it falls under. Write no tests for a blocked unit.

## Hard rules

Write only the behaviors file and the listed test files. No production source, no skeleton, no
build, no test run, no commit, no push, no posting. Report only to the caller: the verdict line
and the two paths.
