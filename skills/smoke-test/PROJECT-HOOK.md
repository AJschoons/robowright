# Project hook contract

`smoke-test` is repo-agnostic. Everything naming a build command, a device, a deep link, an
account, or a screen convention belongs in a project hook, not in `SKILL.md`.

A hook is either an existing project skill that already covers the ground, or a sibling
skill directory `~/.claude/skills/smoke-test-<project>/` with `user-invocable: false`.
Resolve it at the start of Phase 3 by matching `repo:` frontmatter against
`git remote get-url origin`.

## What a hook must supply

1. **Build and install** — the one command shape for a build of an arbitrary ref, and how
   to get it onto the target environment. Phase 3 needs this **twice** — tip and base —
   whenever the inventory has a `touched` row.
2. **Deterministic device state** — which device to use and how it's arbitrated, how to
   reset it, how to grant permissions, and how to seed data. A smoke pass that
   starts from whatever state the last run left is not repeatable.
3. **Sign-in** — how to get into a test account without putting a password in a
   command string.
4. **Feature flags** — how to read the current state and how to force one, per build or at
   runtime.
5. **Navigation** — deep links or equivalent, so a check jumps to its surface rather than
   tapping through four screens. This is what keeps the agent lane inside its retry budget.
6. **Reading the screen** — the accessibility-tree dump or DOM read, how to write a
   predicate against it, and the known traps (duplicate ids, elements reported twice).
7. **Evidence capture** — screenshot command, log tail, where artifacts land, and the
   naming convention tying them to row ids.
8. **Surface map** — file or module paths to product areas, so Phase 1's blast-radius walk
   has somewhere to land. Without this the walk produces symbol names instead of screens,
   which is the single biggest quality drop in the inventory.
9. **Known-noisy surfaces** — screens that flake, states that are slow, anything that
   produces a false `fail`. Named, so a run doesn't chase them.

## Example: an iOS project

No separate hook file — the project hook and the iOS plugin are the hook:

| Need | Where |
|---|---|
| Build | The project hook → Build, with the iOS plugin §1's verdict shapes |
| Device arbitration | The lease the iOS plugin §4 names — use the leased UDID, never a device name |
| Drive, read the screen, screenshot | `axe` and `xcrun simctl` per the iOS plugin §4, `ui-tree-reader` for a question about the tree; the duplicate-id trap is item 6's, named in the hook |
| Sign-in | The hook's sign-in script, taking a tier flag, never a password in the command string |
| Deep links | `<app-scheme>://screen/...`, listed in the hook → Device |
| Tests, if a row turns out to be unit-testable | `load-bearing-tests` |
| Evidence dir | `<run_dir>/smoke/evidence/`, else `<project>/smoke/<TICKET>/evidence/`, where `<project>/` is the project folder the profile → Paths names |

Surface map and known-noisy screens are not written down anywhere yet — derive them per run
and say so in `INVENTORY.md`.

## No hook available

Run the agent lane against whatever the environment offers, and say plainly in
`AGENT-PASS.md` which of the nine items above were missing and what that cost. Do not
silently skip the agent lane and hand over only the manual doc — a manual pass that absorbs
work the agent should have done is how the time box gets blown.
