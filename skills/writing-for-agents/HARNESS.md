# Harness layer — where a document lives in a Claude Code setup

The placement branch of [`writing-for-agents`](SKILL.md). The writing levers are in `SKILL.md`;
this file is which slot a piece of guidance goes in, and how to audit the slots.

## The slots, cheapest context load first

| Slot | Loads | Use it for |
|---|---|---|
| **Hook or lint rule** (`settings.json` hooks, `permissions.deny`, SwiftLint) | Never — it acts | A **mechanical** rule: a fixed command shape, a banned API, a file-location rule. A hook's rejection message is the instruction, delivered at the moment of failure |
| **Reviewer** (a Review Overlay, `comment-pass`, `doc-gate`, the `reviewer-*` agents) | In a fresh context holding only the diff | Standards that are **judgement calls**. The implementing session has the most context pressure and the reviewer the least, so standards are enforced at review |
| **Skill** (`.claude/skills/<name>/`) | Description always; body when it fires | A procedure or reference some sessions need. The description is the context pointer |
| **Path-scoped rule** (`.claude/rules/<name>.md` with `paths:`) | When a matching file is read | Guidance tied to a file type — a language style rule |
| **Project `CLAUDE.md`** (a repo's root) | Inside that repo | Facts about one repo |
| **Always-on rule** (`~/.claude/rules/`, or the always-on rules the profile names) | Every session and every subagent | What nearly every session needs: who the Owner is, how to talk to them, what needs their yes |

An `@import` is organisation only: imported files load at launch
([memory docs](https://code.claude.com/docs/en/memory)). Moving text into an imported file saves
nothing; moving it down this table does.

Pick the lowest slot that still reaches the sessions that need it. A rule that keeps being broken
in prose moves *down* to a hook, and stays out of the always-on file.

## One setup's conventions, as an example

- A configuration repository is the source of truth; its root `CLAUDE.md` says how skills, agents
  and rules are authored and why activation is the Owner's.
- A rule file that also serves another editor keeps that editor's frontmatter on line 1; `paths:` sits beside it in the same block.
- Robowright documents live once, in the clone, and every machine links them from there; there is
  no second copy to update.
- An agent definition pins `model:`.
- History — when a rule was added, what incident caused it, what was measured — goes in the commit
  message and the decision log the profile → Paths names. The document carries the rule and, where it changes
  behaviour, one clause of why.

## Auditing what is loaded

Measure before debating. Byte counts per always-on file give the load. A transcript sweep gives
the hit rate: the share of recent sessions in `~/.claude/projects/*/*.jsonl` whose tool calls
touched the rule's subject (a `.swift` edit, a `simctl` call, a `gh pr` command). A rule with a
low hit rate moves down the table.

Then, per file, in this order — moves before rewrites, since a move keeps the wording:

1. **Placement**: does each section sit in the lowest slot that reaches its sessions?
2. **Mechanical rules** still written as prose → a hook, a deny rule, or a lint rule.
3. **Duplication**: a rule restating a skill, `settings.json`, or another rule. Keep the single
   source of truth and leave a pointer.
4. **Sediment**: history, measurements, incident narration.
5. **No-ops and negation**, last, because they change wording: settle a disputed line by running
   the same task with and without it.
